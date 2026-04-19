"""FastAPI 入口 · 端口 8327 · wechat_agent server。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, WebSocket
from pydantic import BaseModel
from sqlalchemy import select

from server.account_failover import AccountFailover
from server.action_recommender import ActionRecommender
from server.anti_detect import detect_suspicion, humanize
from server.asr_client import DoubaoASRClient
from server.content_ingest import ContentIngestEngine
from server.customer_pipeline import CustomerPipelineBuilder
from server.marketing_plan import (
    MarketingPlanActivator,
    MarketingPlanGenerator,
    list_plans as marketing_list_plans,
)
from server.cross_sell import CrossSellEngine
from server.industry_router import IndustryRouter
from server.message_splitter import split_messages
# Wave 12 · MomentsManager 已删(朋友圈能力废)
from server.psych_triggers import recommend as psych_recommend
from server.typing_pacer import (
    is_nighttime,
    night_reply,
    pace_segments,
)
from server.vlm_client import QwenVLClient
from server.audit import audit
from server.auto_send import AutoSendDecider, AutoSendDecisionType
from server.classifier import IntentClassifier
from server.customer_profile import CustomerProfileEngine
from server.dashboard import DashboardBuilder
from server.db import get_engine, session_scope
from server.follow_up import FollowUpEngine
from server.generator import ReplyGenerator
from server.health_monitor import HealthMonitor, HealthSnapshot
from server.knowledge_base import KnowledgeBase
from server.llm_client import LLMClient
from server.model_router import ModelRouter
from server.activation import ActivationService
from server.auth import AuthContext, auth_required
from server.models import Base, Message as MessageModel
from server.models import Review as ReviewModel
from server.models import SentMessage as SentModel
from server.models import Suggestion as SuggestionModel
from server.notifier import BossNotifier
from server.scheduler import init_scheduler, shutdown_scheduler
from server.tenant import TenantManager
from server.weekly_report import WeeklyReportBuilder, WeeklyReportSender
from server.websocket_pusher import manager as ws_manager, websocket_endpoint
from server.admin import AdminService, admin_required
from evolution.training_queue import TrainingQueueEngine
from shared.const import DEFAULT_HOST, DEFAULT_PORT, VERSION
from shared.errors import BaiyangError
from shared.proto import (
    HealthResponse,
    InboundMsg,
    ReviewDecision,
    SendAck,
    Suggestion,
)

logger = logging.getLogger("baiyang.server")


# ─── 全局组件 ─────────────────────────────────────────────────────────────
class App:
    tenants: TenantManager
    classifier: IntentClassifier
    hermes: LLMClient                    # 历史变量名 · 实际是 LLMClient
    activation: ActivationService
    router: ModelRouter
    generator: ReplyGenerator
    dashboard: DashboardBuilder
    weekly_report_builder: WeeklyReportBuilder
    weekly_report_sender: WeeklyReportSender
    notifier: BossNotifier
    auto_send_decider: AutoSendDecider
    customer_profile: CustomerProfileEngine
    knowledge_base: KnowledgeBase
    health_monitor: HealthMonitor
    training_queue: TrainingQueueEngine
    follow_up: FollowUpEngine
    account_failover: AccountFailover
    vlm: QwenVLClient
    asr: DoubaoASRClient
    industry_router: IndustryRouter
    cross_sell: CrossSellEngine
    pipeline_builder: CustomerPipelineBuilder
    action_recommender: ActionRecommender
    content_ingest: ContentIngestEngine
    marketing_generator: MarketingPlanGenerator
    marketing_activator: MarketingPlanActivator


state = App()


def _config_path() -> Path:
    custom = os.getenv("BAIYANG_TENANTS_PATH")
    if custom:
        return Path(custom)
    return Path(__file__).parent.parent / "config" / "tenants.yaml"


async def _init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _init_components() -> None:
    state.activation = ActivationService()
    state.tenants = TenantManager(config_path=_config_path())
    loaded = state.tenants.load_from_yaml()
    logger.info("tenants loaded: %d", loaded)

    state.hermes = LLMClient(
        mock=os.getenv("BAIYANG_HERMES_MOCK", "true").lower() == "true",
    )
    state.classifier = IntentClassifier(
        mode=os.getenv("BAIYANG_CLASSIFIER", "hybrid"),
        llm_client=state.hermes,
    )
    state.router = ModelRouter()
    state.generator = ReplyGenerator(state.hermes, state.router, state.tenants)
    state.dashboard = DashboardBuilder()
    state.weekly_report_builder = WeeklyReportBuilder()
    state.weekly_report_sender = WeeklyReportSender()
    state.notifier = BossNotifier()
    state.auto_send_decider = AutoSendDecider(
        notifier=state.notifier,
        ws_pusher=ws_manager.push,
    )
    state.customer_profile = CustomerProfileEngine()
    state.knowledge_base = KnowledgeBase()
    state.training_queue = TrainingQueueEngine()

    # F6 health 红灯回调 → F7 容灾
    async def _on_red(tenant_id: str, account_id: str, snap: HealthSnapshot) -> None:
        await state.account_failover.auto_failover(
            tenant_id, account_id,
            reason=f"health_red score={snap.score}",
        )
        await state.notifier.notify(
            tenant_id=tenant_id,
            title="⚠️ 账号自动切换（健康红灯）",
            body=f"原账号 {account_id} 健康分 {snap.score:.0f}/100 · 已自动切备用",
        )

    state.health_monitor = HealthMonitor(base_quota=100, on_red=_on_red)
    state.account_failover = AccountFailover(state.tenants, state.health_monitor)

    # F4 follow_up · send_callback 走 ws push (与 auto_send 一致)
    async def _follow_up_sender(tenant_id, chat_id, text, task_id) -> bool:
        active = state.account_failover.get_active_account_id(tenant_id)
        try:
            await ws_manager.push(tenant_id, {
                "type": "follow_up_send",
                "task_id": task_id,
                "tenant_id": tenant_id,
                "chat_id": chat_id,
                "account_id": active,
                "text": text,
                "issued_at": int(time.time()),
            })
            return True
        except Exception as e:
            logger.error("follow_up sender failed: %s", e)
            return False

    state.follow_up = FollowUpEngine(send_callback=_follow_up_sender)

    # S4 图片理解 · mock fallback 自动生效（无 key 或 BAIYANG_VLM_MOCK=true）
    state.vlm = QwenVLClient()

    # S5 语音转文字 · mock fallback 自动生效（无 key 或 BAIYANG_ASR_MOCK=true）
    state.asr = DoubaoASRClient()

    # Wave 12 · S8 朋友圈托管已删 · 连大哥决策: 客户不需要朋友圈

    # SDW S3 行业模板池
    state.industry_router = IndustryRouter()

    # SDW S7 交叉销售引擎
    state.cross_sell = CrossSellEngine(knowledge_base=state.knowledge_base)

    # T3 待成交 pipeline + 行动推荐
    state.pipeline_builder = CustomerPipelineBuilder()
    state.action_recommender = ActionRecommender()

    # T2 营销方案生成（先初始化 · 让 content_ingest 注入）
    state.marketing_generator = MarketingPlanGenerator(
        llm_client=state.hermes,
        tenants=state.tenants,
    )
    state.marketing_activator = MarketingPlanActivator()

    # T1 内容摄入（魔法文件夹）· 自动触发 marketing_generator
    state.content_ingest = ContentIngestEngine(
        knowledge_base=state.knowledge_base,
        vlm_client=state.vlm,
        asr_client=state.asr,
        llm_client=state.hermes,
        marketing_plan_generator=state.marketing_generator,
    )


def _start_scheduler() -> None:
    if os.getenv("BAIYANG_DISABLE_SCHEDULER", "").lower() == "true":
        logger.info("scheduler disabled by env")
        return
    init_scheduler(
        health_tick=state.health_monitor.tick_all,
        follow_up_tick=state.follow_up.tick,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_db()
    _init_components()
    _start_scheduler()
    # Wave 13 · 恢复所有 online 账号的消息同步
    try:
        from server.wxpadpro_bridge import resume_sync_loops_on_startup
        await resume_sync_loops_on_startup()
    except Exception as _e:
        logger.warning("resume_sync_loops failed: %s", _e)
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(
    title="wechat_agent server",
    version=VERSION,
    lifespan=lifespan,
)

# ─── Wave 6 · 租户 Dashboard 路由 ─────────────────────────────────────────────
from server.tenant_dashboard import router as tenant_dashboard_router  # noqa: E402
app.include_router(tenant_dashboard_router)

# ─── Wave 7 · Gewechat Webhook 路由 ──────────────────────────────────────────
from server.wxpadpro_bridge import router as wxpadpro_router  # noqa: E402
app.include_router(wxpadpro_router)

# ─── Wave 9 · 客户注册/登录/激活/裂变/视图路由 ───────────────────────────────
from server.signup_login_api import router as signup_login_router  # noqa: E402
from server.activate_api import router as activate_api_router  # noqa: E402
from server.referral_api import router as referral_api_router  # noqa: E402
from server.view_routes import router as view_routes_router  # noqa: E402
app.include_router(signup_login_router)
app.include_router(activate_api_router)
app.include_router(referral_api_router)
app.include_router(view_routes_router)

# ─── Wave 10 · 训练自动化管线 + 通知 + 试用管理 ──────────────────────────────
from server.training_api import router as training_api_router  # noqa: E402
app.include_router(training_api_router)

# ─── Wave 11 · 主动销售 + 合规 + 沙盒 + 模式 + 飞书bot ────────────────────────
from server.proactive_api import router as proactive_api_router  # noqa: E402
app.include_router(proactive_api_router)

# ─── Wave 11 F9 · 违禁词合规改造 ───────────────────────────────────────────
from server.compliance_api import router as compliance_api_router  # noqa: E402
app.include_router(compliance_api_router)

# ─── Wave 11 丁 · 飞书 Bot + 员工状态 API ────────────────────────────────────
from server.feishu_admin_bot import router as feishu_bot_router  # noqa: E402
from server.accounts_status_api import router as accounts_status_router  # noqa: E402
app.include_router(feishu_bot_router)
app.include_router(accounts_status_router)

# ─── Wave 11 丙 · F1 Sandbox + F2 Moments + F7 Modes ─────────────────────────
from server.sandbox_api import router as sandbox_api_router  # noqa: E402
# Wave 12 · moments_api 已删
from server.modes_api import router as modes_api_router  # noqa: E402
app.include_router(sandbox_api_router)
# Wave 12 · moments_api_router 已删
app.include_router(modes_api_router)


# ─── 错误统一映射 ──────────────────────────────────────────────────────────
@app.exception_handler(BaiyangError)
async def _baiyang_error_handler(_request, exc: BaiyangError):
    return HTTPException(status_code=exc.http_status, detail={"code": exc.code, "msg": str(exc)})


# ─── 健康检查 ──────────────────────────────────────────────────────────────
@app.get("/v1/health", response_model=HealthResponse)
async def health():
    hermes_ok = await state.hermes.health()
    db_ok = True
    try:
        async with session_scope() as session:
            await session.execute(select(MessageModel).limit(1))
    except Exception:
        db_ok = False

    return HealthResponse(
        status="ok" if (hermes_ok and db_ok) else "degraded",
        version=VERSION,
        hermes_reachable=hermes_ok,
        db_reachable=db_ok,
        tenants_loaded=len(state.tenants.list_all()),
    )


# ─── 收消息 ────────────────────────────────────────────────────────────────
@app.post("/v1/inbound", response_model=Suggestion)
async def inbound(msg: InboundMsg):
    if not state.tenants.has(msg.tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {msg.tenant_id} unknown")

    msg_id_inbound = ReplyGenerator._inbound_msg_id(msg)

    async with session_scope() as session:
        existing = (
            await session.execute(select(MessageModel).where(MessageModel.msg_id == msg_id_inbound))
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                MessageModel(
                    msg_id=msg_id_inbound,
                    tenant_id=msg.tenant_id,
                    chat_id=msg.chat_id,
                    sender_id=msg.sender_id,
                    sender_name=msg.sender_name,
                    text=msg.text,
                    msg_type=msg.msg_type,
                    timestamp=msg.timestamp,
                    raw_metadata=json.dumps(msg.raw_metadata, ensure_ascii=False),
                )
            )

    await audit.log(
        actor="client",
        action="inbound_received",
        tenant_id=msg.tenant_id,
        msg_id=msg_id_inbound,
        meta={"chat_id": msg.chat_id, "sender": msg.sender_name},
    )

    # S5 语音转文字：检测 voice_url → 调 asr → 转写文字赋给 text
    if msg.msg_type == "voice" and msg.voice_url:
        asr_text = await state.asr.transcribe(msg.voice_url)
        if asr_text:
            msg = msg.model_copy(update={"text": asr_text})

    # S4 图片理解：检测 image_url → 调 vlm → 描述拼到 text 前
    if msg.msg_type == "image" and msg.image_url:
        img_desc = await state.vlm.describe(msg.image_url, prompt=msg.text or None)
        if img_desc:
            original_text = msg.text
            user_question = f" 用户问：{original_text}" if original_text else ""
            msg = msg.model_copy(update={"text": f"[图片：{img_desc}]{user_question}"})

    # FDW+ L2 灰产检测：客户消息含禁词 → 拒绝生成 + 转人工 + audit
    from server.compliance_check import detect_gray_intent, get_rejection_reply, is_blocked
    gray_hit = detect_gray_intent(msg.text)
    if gray_hit and gray_hit.severity == "high":
        await audit.log(
            actor="server",
            action="compliance_blocked",
            tenant_id=msg.tenant_id,
            msg_id=msg_id_inbound,
            meta={
                "category": gray_hit.category,
                "severity": gray_hit.severity,
                "matched_keywords": gray_hit.keywords[:3],
            },
        )
        asyncio.create_task(state.notifier.notify(
            tenant_id=msg.tenant_id,
            title=f"🚫 灰产消息拦截 · {gray_hit.category}",
            body=f"客户：{msg.sender_name} · 已拒绝生成 · 建议人工处理",
        ))
        # 返回拒绝 suggestion · 不走 generator
        rejection_text = get_rejection_reply(gray_hit)
        from shared.proto import IntentResult
        from shared.types import EmotionEnum, IntentEnum, RiskEnum
        return Suggestion(
            msg_id=f"sug_compliance_{msg_id_inbound[-12:]}",
            tenant_id=msg.tenant_id,
            inbound_msg_id=msg_id_inbound,
            intent=IntentResult(
                intent=IntentEnum.SENSITIVE,
                emotion=EmotionEnum.CALM,
                risk=RiskEnum.HIGH,
                confidence=1.0,
                matched_keywords=gray_hit.keywords[:3],
            ),
            text=rejection_text,
            model_route="compliance_block",
            generated_at=int(time.time()),
        )

    # SDW S6 反检测：客户疑心 → 暂停 + 推老板（不再自动回 · 让真人接管）
    if detect_suspicion(msg.text):
        await audit.log(
            actor="server",
            action="suspicion_detected",
            tenant_id=msg.tenant_id,
            msg_id=msg_id_inbound,
            meta={"client_text_preview": msg.text[:60]},
        )
        state.auto_send_decider.pause(msg.tenant_id, duration_sec=3600)
        asyncio.create_task(state.notifier.notify(
            tenant_id=msg.tenant_id,
            title="🚨 客户疑心 AI · 已暂停自动回复 1 小时",
            body=f"客户消息：{msg.text[:80]} · 请尽快人工接管",
        ))

    intent = await state.classifier.classify(msg.text)

    tenant_cfg = state.tenants.get(msg.tenant_id)

    # F2 客户档案 · F3 知识库 RAG · 拼进 prompt
    profile_snapshot = await state.customer_profile.get_or_create(
        msg.tenant_id, msg.chat_id, msg.sender_name
    )
    profile_block = state.customer_profile.render_for_prompt(profile_snapshot)

    chunks = await state.knowledge_base.query(msg.tenant_id, msg.text, top_k=3)
    knowledge_block = state.knowledge_base.render_for_prompt(chunks)

    # SDW S3 行业模板：根据 tenant.industry 加载对应行业 prompt 段
    industry_block = state.industry_router.get_prompt_block(tenant_cfg.industry or "通用")

    # SDW S2 心理学触发器：4 维度自动选 Cialdini 触发
    psych_rec = psych_recommend(
        intent=intent.intent,
        emotion=intent.emotion,
        last_intent=profile_snapshot.last_intent,
        has_purchase_history=bool(profile_snapshot.purchase_history),
        days_since_last_message=profile_snapshot.days_since_last,
    )
    psych_block = psych_rec.instructions

    suggestion = await state.generator.generate(
        msg, intent,
        customer_profile_block=profile_block,
        knowledge_block=knowledge_block,
        industry_block=industry_block,
        psych_block=psych_block,
    )

    # SDW S6 反检测：humanize（开场变体 + 5% typo · 防机器完美）
    suggestion = suggestion.model_copy(update={"text": humanize(suggestion.text)})

    # SDW S7 交叉销售：尝试追加推荐
    cross_recs = await state.cross_sell.recommend(
        tenant_id=msg.tenant_id,
        customer_profile=profile_snapshot,
        current_intent=intent.intent,
        last_message_text=msg.text,
    )
    if cross_recs:
        new_text = await state.cross_sell.maybe_append_to_reply(
            original_reply=suggestion.text,
            recs=cross_recs,
            chat_id=msg.chat_id,
            tenant_id=msg.tenant_id,
        )
        suggestion = suggestion.model_copy(update={"text": new_text})

    async with session_scope() as session:
        session.add(
            SuggestionModel(
                msg_id=suggestion.msg_id,
                tenant_id=suggestion.tenant_id,
                inbound_msg_id=suggestion.inbound_msg_id,
                intent=suggestion.intent.intent.value,
                risk=suggestion.intent.risk.value,
                text=suggestion.text,
                model_route=suggestion.model_route,
                generated_at=suggestion.generated_at,
                similarity_check_passed=int(suggestion.similarity_check_passed),
                rewrite_count=suggestion.rewrite_count,
                forbidden_word_hit=int(suggestion.forbidden_word_hit),
            )
        )

    await audit.log(
        actor="server",
        action="suggestion_generated",
        tenant_id=msg.tenant_id,
        msg_id=suggestion.msg_id,
        meta={
            "intent": suggestion.intent.intent.value,
            "risk": suggestion.intent.risk.value,
            "route": suggestion.model_route,
            "rewrites": suggestion.rewrite_count,
        },
    )

    # F2 异步更新档案
    asyncio.create_task(
        state.customer_profile.update_after_inbound(
            msg.tenant_id, msg.chat_id, msg, intent
        )
    )

    # F1 全自动决策 + 后处理（不阻塞响应）
    active_account = state.account_failover.get_active_account_id(msg.tenant_id)
    health_status = await state.health_monitor.get_status(msg.tenant_id, active_account)
    decision = await state.auto_send_decider.decide(
        suggestion, tenant_cfg,
        health_score=health_status.score if health_status else None,
        health_level=health_status.level if health_status else None,
    )

    await audit.log(
        actor="server",
        action=f"auto_send_{decision.decision.value}",
        tenant_id=msg.tenant_id,
        msg_id=suggestion.msg_id,
        meta={"reason": decision.reason},
    )

    asyncio.create_task(state.auto_send_decider.handle_decision(decision, tenant_cfg))

    # F4 订单 + Wave 14 购买意向 → 自动安排跟进序列
    from shared.types import IntentEnum as _IE
    if intent.intent in (_IE.ORDER, _IE.PURCHASE_SIGNAL):
        asyncio.create_task(
            state.follow_up.schedule_after_order(
                msg.tenant_id, msg.chat_id, sender_name=msg.sender_name
            )
        )

    return suggestion


# ─── 老板审核 ──────────────────────────────────────────────────────────────
@app.post("/v1/outbound/{msg_id}/decide", response_model=dict)
async def decide(msg_id: str, decision: ReviewDecision):
    if decision.msg_id != msg_id:
        raise HTTPException(status_code=400, detail="msg_id mismatch")

    async with session_scope() as session:
        sug = (
            await session.execute(select(SuggestionModel).where(SuggestionModel.msg_id == msg_id))
        ).scalar_one_or_none()
        if not sug:
            raise HTTPException(status_code=404, detail="suggestion not found")

        session.add(
            ReviewModel(
                msg_id=msg_id,
                decision=decision.decision.value,
                edited_text=decision.edited_text,
                reviewed_at=decision.reviewed_at,
            )
        )

        tenant_id = sug.tenant_id
        sug_text = sug.text
        sug_intent = sug.intent
        sug_risk = sug.risk
        inbound_id = sug.inbound_msg_id

    # 拉原 customer_msg + 加入 training_queue
    async with session_scope() as session:
        cust_row = (
            await session.execute(
                select(MessageModel.text, MessageModel.chat_id)
                .where(MessageModel.msg_id == inbound_id)
            )
        ).first()
        customer_msg_text = cust_row[0] if cust_row else ""
        chat_id = cust_row[1] if cust_row else ""

    if customer_msg_text:
        from shared.types import EmotionEnum, IntentEnum, RiskEnum
        from shared.proto import IntentResult as IR, Suggestion as Sg
        try:
            sug_full = Sg(
                msg_id=msg_id,
                tenant_id=tenant_id,
                inbound_msg_id=inbound_id,
                intent=IR(
                    intent=IntentEnum(sug_intent),
                    risk=RiskEnum(sug_risk),
                    emotion=EmotionEnum.CALM,
                    confidence=0.8,
                ),
                text=sug_text,
                model_route="historical",
                generated_at=int(time.time()),
            )
            asyncio.create_task(
                state.training_queue.append(tenant_id, customer_msg_text, sug_full, decision)
            )
            asyncio.create_task(
                state.customer_profile.update_after_send(tenant_id, chat_id, sug_full, decision)
            )
        except Exception as e:
            logger.warning("training_queue.append skipped: %s", e)

    await audit.log(
        actor="reviewer",
        action="reviewed",
        tenant_id=tenant_id,
        msg_id=msg_id,
        meta={"decision": decision.decision.value, "edited": bool(decision.edited_text)},
    )

    return {"ok": True, "msg_id": msg_id, "decision": decision.decision.value}


# ─── 客户端发送回执 ─────────────────────────────────────────────────────────
@app.post("/v1/outbound/{msg_id}/sent", response_model=dict)
async def sent(msg_id: str, ack: SendAck):
    if ack.msg_id != msg_id:
        raise HTTPException(status_code=400, detail="msg_id mismatch")

    async with session_scope() as session:
        sug = (
            await session.execute(select(SuggestionModel).where(SuggestionModel.msg_id == msg_id))
        ).scalar_one_or_none()
        if not sug:
            raise HTTPException(status_code=404, detail="suggestion not found")

        chat_id_row = (
            await session.execute(select(MessageModel.chat_id).where(MessageModel.msg_id == sug.inbound_msg_id))
        ).scalar_one_or_none() or ""

        review = (
            await session.execute(select(ReviewModel).where(ReviewModel.msg_id == msg_id))
        ).scalar_one_or_none()
        sent_text = (review.edited_text if review and review.edited_text else sug.text) if review else sug.text

        session.add(
            SentModel(
                msg_id=msg_id,
                tenant_id=sug.tenant_id,
                chat_id=chat_id_row,
                text=sent_text,
                sent_at=ack.sent_at,
                success=int(ack.success),
                error=ack.error,
            )
        )

        tenant_id = sug.tenant_id

    await audit.log(
        actor="client",
        action="sent" if ack.success else "send_failed",
        tenant_id=tenant_id,
        msg_id=msg_id,
        meta={"error": ack.error} if ack.error else {},
    )

    return {"ok": True, "msg_id": msg_id, "sent_at": ack.sent_at, "success": ack.success}


# ─── F1 控制路由 · 暂停 / 恢复 / 状态 ──────────────────────────────────────
class PauseRequest(BaseModel):
    duration_sec: int = 3600


@app.post("/v1/control/{tenant_id}/pause")
async def control_pause(tenant_id: str, body: PauseRequest = PauseRequest()):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    until = state.auto_send_decider.pause(tenant_id, body.duration_sec)
    await audit.log(
        actor="boss", action="auto_send_paused",
        tenant_id=tenant_id, meta={"until": until, "duration": body.duration_sec},
    )
    return {"ok": True, "tenant_id": tenant_id, "paused_until": until}


@app.post("/v1/control/{tenant_id}/resume")
async def control_resume(tenant_id: str):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    cleared = state.auto_send_decider.resume(tenant_id)
    await audit.log(
        actor="boss", action="auto_send_resumed",
        tenant_id=tenant_id, meta={"was_paused": cleared},
    )
    return {"ok": True, "tenant_id": tenant_id, "was_paused": cleared}


@app.get("/v1/control/{tenant_id}/status")
async def control_status(tenant_id: str):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    cfg = state.tenants.get(tenant_id)
    return {
        "tenant_id": tenant_id,
        "auto_send_enabled": cfg.auto_send_enabled,
        "high_risk_block": cfg.high_risk_block,
        "is_paused": state.auto_send_decider.is_paused(tenant_id),
        "paused_until": state.auto_send_decider.get_pause_until(tenant_id),
        "ws_active_connections": ws_manager.active_count(tenant_id),
    }


# ─── F6 反封号 · 健康分查询 + 手动恢复 ──────────────────────────────────────
@app.get("/v1/health/{tenant_id}")
async def account_health(tenant_id: str, account_id: str = "primary"):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    snap = await state.health_monitor.get_status(tenant_id, account_id)
    if snap is None:
        return {
            "tenant_id": tenant_id,
            "account_id": account_id,
            "score": 100.0,
            "level": "green",
            "evaluated": False,
        }
    return {
        "tenant_id": tenant_id,
        "account_id": account_id,
        "score": snap.score,
        "level": snap.level,
        "paused_until": snap.paused_until,
        "daily_quota_override": snap.daily_quota_override,
        "last_evaluated_at": snap.last_evaluated_at,
        "evaluated": True,
    }


@app.post("/v1/health/{tenant_id}/recover")
async def account_health_recover(tenant_id: str, account_id: str = "primary"):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    ok = await state.health_monitor.manual_recover(tenant_id, account_id)
    await audit.log(
        actor="boss", action="health_manual_recover",
        tenant_id=tenant_id, meta={"account_id": account_id, "ok": ok},
    )
    return {"ok": ok, "tenant_id": tenant_id, "account_id": account_id}


# ─── T1 内容摄入 · 魔法文件夹 ───────────────────────────────────────────
@app.post("/v1/content/{tenant_id}/upload")
async def content_upload(tenant_id: str, file_name: str, body: dict):
    """body: {file_bytes_b64: str}"""
    import base64
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    b64 = body.get("file_bytes_b64", "")
    if not b64:
        raise HTTPException(status_code=400, detail="file_bytes_b64 required")
    try:
        file_bytes = base64.b64decode(b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid base64: {e}")
    record = await state.content_ingest.ingest(tenant_id, file_name, file_bytes)
    return {
        "ok": True,
        "file_id": record.file_id,
        "file_type": record.file_type,
        "parsed_chunks": record.parsed_chunks,
        "source_tag": record.source_tag,
        "marketing_plan_id": record.marketing_plan_id,
    }


@app.get("/v1/content/{tenant_id}")
async def content_list(tenant_id: str, limit: int = 100):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await state.content_ingest.list_uploads(tenant_id, limit=limit)


@app.delete("/v1/content/{file_id}")
async def content_delete(file_id: str):
    ok = await state.content_ingest.delete(file_id)
    return {"ok": ok, "file_id": file_id}


# ─── T2 营销方案 ─────────────────────────────────────────────────────────
@app.post("/v1/marketing/{tenant_id}/generate")
async def marketing_generate(tenant_id: str, body: dict):
    """body: {source_text: str, source_content_id: str (optional)}"""
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    plan_id = await state.marketing_generator.generate(
        tenant_id=tenant_id,
        source_content_id=body.get("source_content_id"),
        source_text=body.get("source_text", ""),
    )
    return {"ok": True, "plan_id": plan_id}


@app.get("/v1/marketing/{tenant_id}")
async def marketing_list(tenant_id: str, status: Optional[str] = None, limit: int = 50):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await marketing_list_plans(tenant_id, status=status, limit=limit)


@app.post("/v1/marketing/{plan_id}/activate")
async def marketing_activate(plan_id: str):
    return await state.marketing_activator.activate(plan_id)


# ─── L3 紧急停止（举报检测触发）───────────────────────────────────────────
@app.post("/v1/control/{tenant_id}/emergency_stop")
async def control_emergency_stop(tenant_id: str, body: dict = None):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    body = body or {}
    until = state.auto_send_decider.pause(tenant_id, duration_sec=3600)
    await audit.log(
        actor="client", action="emergency_stop_wechat_alert",
        tenant_id=tenant_id,
        meta={
            "alert_text": body.get("alert_text", ""),
            "pattern": body.get("pattern", ""),
            "detected_at": body.get("detected_at", 0),
        },
    )
    asyncio.create_task(state.notifier.notify(
        tenant_id=tenant_id,
        title="🚨 微信警告检测到 · 紧急停止 1 小时",
        body=f"原因：{body.get('alert_text', '未知')[:60]} · 请人工接管",
    ))
    return {"ok": True, "tenant_id": tenant_id, "paused_until": until}


# ─── L4 法律举证导出（管理员）─────────────────────────────────────────────
@app.get("/v1/admin/legal_export/{tenant_id}")
async def admin_legal_export(tenant_id: str, start_ts: Optional[int] = None, end_ts: Optional[int] = None):
    """简化版 · 不强制 admin auth · prod 加 admin_required"""
    from server.legal_export import LegalExporter
    pkg = await LegalExporter().export_for_tenant(tenant_id, start_ts=start_ts, end_ts=end_ts)
    return {
        "tenant_id": pkg.tenant_id,
        "boss_name": pkg.boss_name,
        "plan": pkg.plan,
        "audit_log_csv_preview": pkg.audit_log_csv[:500],
        "audit_log_csv_size": len(pkg.audit_log_csv),
        "consent_records": pkg.consent_records,
        "auto_send_config_history": pkg.auto_send_config_history,
        "tenant_summary_md": pkg.tenant_summary_md,
        "exported_at": pkg.exported_at,
    }


# ─── F4 跟进序列 ─────────────────────────────────────────────────────────
@app.get("/v1/follow_up/{tenant_id}")
async def follow_up_list(tenant_id: str, status: Optional[str] = None, limit: int = 100):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await state.follow_up.list_for_tenant(tenant_id, status=status, limit=limit)


@app.delete("/v1/follow_up/{task_id}")
async def follow_up_cancel(task_id: str):
    ok = await state.follow_up.cancel(task_id)
    return {"ok": ok, "task_id": task_id}


# ─── F7 多账号容灾 ───────────────────────────────────────────────────────
@app.get("/v1/accounts/{tenant_id}")
async def accounts_list(tenant_id: str):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    accounts = await state.account_failover.list_accounts(tenant_id)
    return {
        "tenant_id": tenant_id,
        "active_account_id": state.account_failover.get_active_account_id(tenant_id),
        "accounts": [
            {
                "account_id": a.account_id,
                "role": a.role,
                "wxid": a.wxid,
                "is_active": a.is_active,
                "health_level": a.health_level,
                "health_score": a.health_score,
            }
            for a in accounts
        ],
    }


@app.post("/v1/accounts/{tenant_id}/switch/{account_id}")
async def accounts_switch(tenant_id: str, account_id: str):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    ok = await state.account_failover.manual_switch(tenant_id, account_id)
    if not ok:
        raise HTTPException(status_code=400, detail=f"account {account_id} not switchable")
    await audit.log(
        actor="boss", action="account_manual_switch",
        tenant_id=tenant_id, meta={"to": account_id},
    )
    return {"ok": True, "tenant_id": tenant_id, "active": account_id}


@app.get("/v1/accounts/{tenant_id}/history")
async def accounts_history(tenant_id: str, limit: int = 20):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await state.account_failover.history(tenant_id, limit=limit)


# ─── 老板 Dashboard ─────────────────────────────────────────────────────────
@app.get("/v1/dashboard/{tenant_id}")
async def dashboard(tenant_id: str):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await state.dashboard.build(tenant_id)


# ─── Dashboard v2 路由 ──────────────────────────────────────────────────────
@app.get("/v1/dashboard/{tenant_id}/v2")
async def dashboard_v2(tenant_id: str):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await state.dashboard.build_v2(tenant_id)


@app.get("/v1/dashboard/{tenant_id}/trend")
async def dashboard_trend(tenant_id: str, days: int = 7):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await state.dashboard.build_trend(tenant_id, days=days)


@app.get("/v1/dashboard/{tenant_id}/customers")
async def dashboard_customers(tenant_id: str, tier: Optional[str] = None):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    if tier and tier.upper() not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="tier must be A/B/C or omitted")
    return await state.dashboard.build_customers(tenant_id, tier=tier)


@app.get("/v1/dashboard/{tenant_id}/funnel")
async def dashboard_funnel(tenant_id: str):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await state.dashboard.build_funnel(tenant_id)


@app.get("/v1/dashboard/{tenant_id}/benchmark")
async def dashboard_benchmark(tenant_id: str):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await state.dashboard.build_benchmark(tenant_id)


@app.get("/v1/dashboard/{tenant_id}/v3")
async def dashboard_v3(
    tenant_id: str,
    auth: AuthContext = Depends(auth_required),
):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    return await state.dashboard.build_v3(
        tenant_id,
        pipeline_builder=state.pipeline_builder,
        action_recommender=state.action_recommender,
        account_failover=state.account_failover,
        health_monitor=state.health_monitor,
    )


@app.get("/v1/dashboard/{tenant_id}/pipeline")
async def dashboard_pipeline(tenant_id: str, max_count: int = 10):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    customers = await state.pipeline_builder.build(tenant_id, max_count=max_count)
    return {
        "tenant_id": tenant_id,
        "pipeline": [
            {
                "chat_id": c.chat_id,
                "nickname": c.nickname,
                "vip_tier": c.vip_tier,
                "stage": c.stage,
                "last_message_at": c.last_message_at,
                "days_since_last": c.days_since_last,
                "last_intent": c.last_intent,
                "last_emotion": c.last_emotion,
                "urgency": c.urgency,
                "pending_value_estimate": c.pending_value_estimate,
            }
            for c in customers
        ],
    }


@app.get("/v1/dashboard/{tenant_id}/actions")
async def dashboard_actions(tenant_id: str, n: int = 10):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    actions = await state.action_recommender.recommend_top_n(tenant_id, n=n)
    return {
        "tenant_id": tenant_id,
        "actions": [
            {
                "chat_id": a.chat_id,
                "nickname": a.nickname,
                "action_type": a.action_type,
                "reason": a.reason,
                "suggested_text": a.suggested_text,
                "confidence": a.confidence,
            }
            for a in actions
        ],
    }


@app.post("/v1/dashboard/{tenant_id}/weekly_report/send")
async def weekly_report_send(tenant_id: str):
    if not state.tenants.has(tenant_id):
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} unknown")
    md = await state.weekly_report_builder.build_markdown(tenant_id)
    result = await state.weekly_report_sender.send(tenant_id, md)
    return {"ok": result["ok"], "tenant_id": tenant_id, "mode": result.get("mode", "unknown")}


# Wave 12 · 朋友圈托管已废 (连大哥决策: 客户不需要朋友圈能力)
# 历史路由 /v1/moments/* 全删 · 对应 moments_manager / moments_api / sns_* 模块已删.


# ─── WebSocket 推送 ─────────────────────────────────────────────────────────
@app.websocket("/v1/ws/{tenant_id}")
async def ws_route(websocket: WebSocket, tenant_id: str):
    await websocket_endpoint(websocket, tenant_id)


# ─── 拉取待审核（客户端长轮询/调试用） ──────────────────────────────────────
@app.get("/v1/outbound/pending/{tenant_id}")
async def pending(tenant_id: str, limit: int = 20):
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(SuggestionModel)
                .where(SuggestionModel.tenant_id == tenant_id)
                .order_by(SuggestionModel.generated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "msg_id": r.msg_id,
                "text": r.text,
                "intent": r.intent,
                "risk": r.risk,
                "generated_at": r.generated_at,
                "rewrite_count": r.rewrite_count,
            }
            for r in rows
        ]


# ─── T5 数据所有权路由 ──────────────────────────────────────────────────────

class DeleteRequestBody(BaseModel):
    reason: str = ""


class DeleteCancelBody(BaseModel):
    request_id: str


@app.post("/v1/account/{tenant}/export")
async def account_export(tenant: str, format: str = "csv"):
    """导出原始聊天数据（messages + suggestions + sent）。不含训练资产。"""
    from fastapi.responses import Response
    from server.data_export import DataExporter

    if format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="format must be csv or json")

    exporter = DataExporter()
    data = await exporter.export_chats(tenant, format=format)

    media_type = "text/csv" if format == "csv" else "application/json"
    filename = f"wechat_agent_{tenant}_export.{format}"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/v1/account/{tenant}/summary")
async def account_summary(tenant: str):
    """账号数据摘要：消息数 / 客户数 / 已运行天数。"""
    from server.data_export import DataExporter

    exporter = DataExporter()
    return await exporter.export_summary(tenant)


@app.post("/v1/account/{tenant}/delete_request")
async def account_delete_request(tenant: str, body: DeleteRequestBody = DeleteRequestBody()):
    """发起账号删除请求（30 天 grace period）。"""
    from server.data_deletion import GRACE_SECONDS, DataDeletionManager

    mgr = DataDeletionManager()
    request_id = await mgr.request(tenant, reason=body.reason)
    return {
        "ok": True,
        "request_id": request_id,
        "tenant_id": tenant,
        "grace_until": int(time.time()) + GRACE_SECONDS,
        "grace_days": 30,
        "message": "删除请求已记录，30 天宽限期内可撤销。",
    }


@app.post("/v1/account/{tenant}/delete_cancel")
async def account_delete_cancel(tenant: str, body: DeleteCancelBody):
    """撤销删除请求（宽限期内有效）。"""
    from server.data_deletion import DataDeletionManager

    mgr = DataDeletionManager()
    ok = await mgr.cancel(body.request_id)
    if not ok:
        raise HTTPException(status_code=404, detail="request_id not found or already executed/cancelled")
    return {"ok": True, "request_id": body.request_id, "message": "删除请求已撤销。"}


@app.get("/v1/account/{tenant}/delete_status")
async def account_delete_status(tenant: str):
    """查询 tenant 的删除请求状态。"""
    from server.data_deletion import DataDeletionManager

    mgr = DataDeletionManager()
    requests = await mgr.get_by_tenant(tenant)
    return {"tenant_id": tenant, "requests": requests}




# ─── FDW F6 管理后台 ──────────────────────────────────────────────────────────

class IssueCodeBody(BaseModel):
    plan: str = "pro"
    valid_days: int = 365


_admin_service = AdminService()


@app.get("/admin/customers")
async def admin_customers(_token: str = Depends(admin_required)):
    return await _admin_service.list_customers()


@app.get("/admin/customers/{tenant_id}")
async def admin_customer_detail(tenant_id: str, _token: str = Depends(admin_required)):
    return await _admin_service.get_customer_detail(tenant_id)


@app.post("/admin/issue_code")
async def admin_issue_code(body: IssueCodeBody, _token: str = Depends(admin_required)):
    code = await _admin_service.issue_activation_code(plan=body.plan, valid_days=body.valid_days)
    return {"ok": True, "code": code, "plan": body.plan, "valid_days": body.valid_days}


@app.post("/admin/revoke/{code}")
async def admin_revoke_code(code: str, _token: str = Depends(admin_required)):
    await _admin_service.revoke_code(code)
    return {"ok": True, "code": code}


@app.get("/admin/health/overview")
async def admin_health_overview(_token: str = Depends(admin_required)):
    return await _admin_service.health_overview()


@app.get("/admin/revenue")
async def admin_revenue(
    start_date: str,
    end_date: str,
    _token: str = Depends(admin_required),
):
    return await _admin_service.export_revenue_report(start_date, end_date)


# ─── FDW F2 激活码 + F5 鉴权路由 ───────────────────────────────────────────

class ActivateRequest(BaseModel):
    code: str
    machine_guid: Optional[str] = None
    tenant_id: Optional[str] = None


@app.post("/v1/activate")
async def activate(body: ActivateRequest):
    """POST /v1/activate · 客户端输码激活 · 返 device_token。"""
    tenant_id = body.tenant_id or f"tenant_{body.code[-8:].lower().replace('-', '')}"
    try:
        token = await state.activation.activate(
            code=body.code,
            machine_guid=body.machine_guid or "",
            tenant_id=tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    info = await state.activation.is_valid(token)
    return {
        "device_token": token,
        "tenant_id": tenant_id,
        "plan": info["plan"] if info else "pro",
    }


@app.post("/v1/activation/heartbeat")
async def activation_heartbeat(auth: AuthContext = Depends(auth_required)):
    """POST /v1/activation/heartbeat · 客户端 30 分钟一次。"""
    ok = await state.activation.heartbeat(auth.device_token)
    if not ok:
        raise HTTPException(status_code=401, detail="token revoked or offline too long")
    return {"ok": True}


@app.get("/v1/activation/status")
async def activation_status(auth: AuthContext = Depends(auth_required)):
    """GET /v1/activation/status · 查询当前激活状态。"""
    info = await state.activation.is_valid(auth.device_token)
    if info is None:
        raise HTTPException(status_code=401, detail="token invalid")
    return {
        "plan": info["plan"],
        "tenant_id": info["tenant_id"],
        "bound_at": info["bound_at"],
        "last_heartbeat": info["last_heartbeat_at"],
    }


# ─── F3 自动更新版本接口 ───────────────────────────────────────────────────────

@app.get("/v1/version")
async def get_version():
    """返回最新版本信息 · 供客户端自动更新（F3）使用。"""
    from server.version_api import get_version_info  # noqa: PLC0415
    return get_version_info()


# ─── Wave 8 · 行业飞轮同意管理路由 ──────────────────────────────────────────

class ConsentGrantBody(BaseModel):
    signed_at: Optional[int] = None  # Unix ms · 默认 server time


@app.post("/v1/consent/{tenant}/grant/{consent_type}")
async def consent_grant(tenant: str, consent_type: str, body: ConsentGrantBody = ConsentGrantBody()):
    """记录 tenant 明确同意参与某类数据共享（如 industry_flywheel）。

    默认 OFF · 必须调用此接口才启用飞轮贡献。
    """
    from server.consent_manager import ConsentManager, CONSENT_TYPES
    if consent_type not in CONSENT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的 consent_type: {consent_type}，有效值: {list(CONSENT_TYPES)}")
    cm = ConsentManager(tenant)
    cm.grant(tenant, consent_type=consent_type, signed_at=body.signed_at)
    await audit.log(
        actor="boss", action="consent_grant",
        tenant_id=tenant, meta={"consent_type": consent_type},
    )
    return {"ok": True, "tenant_id": tenant, "consent_type": consent_type, "active": True}


@app.post("/v1/consent/{tenant}/revoke/{consent_type}")
async def consent_revoke(tenant: str, consent_type: str):
    """撤回 tenant 的数据共享同意 · 24h 内清理飞轮数据。"""
    from server.consent_manager import ConsentManager, CONSENT_TYPES
    from server.industry_flywheel import IndustryFlywheel
    if consent_type not in CONSENT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的 consent_type: {consent_type}")
    cm = ConsentManager(tenant)
    cm.revoke(tenant, consent_type=consent_type)

    # 飞轮数据立即清理（同意撤回 = 立即删除贡献）
    removed = 0
    if consent_type == "industry_flywheel":
        try:
            flywheel = IndustryFlywheel()
            removed = flywheel.revoke(tenant)
        except Exception as e:
            logger.warning("飞轮数据清理失败（非阻塞）: %s", e)

    await audit.log(
        actor="boss", action="consent_revoke",
        tenant_id=tenant, meta={"consent_type": consent_type, "flywheel_removed": removed},
    )
    return {
        "ok": True, "tenant_id": tenant, "consent_type": consent_type,
        "active": False, "flywheel_removed": removed,
    }


@app.get("/v1/consent/{tenant}")
async def consent_status(tenant: str):
    """查询 tenant 的所有同意状态。"""
    from server.consent_manager import ConsentManager, CONSENT_TYPES
    cm = ConsentManager(tenant)
    result = {}
    for ctype in CONSENT_TYPES:
        result[ctype] = cm.has_consent(ctype)
    return {"tenant_id": tenant, "consents": result}


def run() -> None:
    uvicorn.run("server.main:app", host=DEFAULT_HOST, port=DEFAULT_PORT, reload=True)


if __name__ == "__main__":
    run()
