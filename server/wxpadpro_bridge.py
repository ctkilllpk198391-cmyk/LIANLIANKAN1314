"""Wave 13 · WeChatPadPro bridge (server 侧).

替代 Wave 12 wcferry_bridge. 号托管 ECS WxPadPro Docker · 出口 IP 走客户家 frp socks5.

路由:
  POST /v1/wxpad/callback         — WxPadPro webhook · 收消息
  POST /v1/wxpad/login/qr         — 拉登录二维码 (alloc frp 端口 + 生成 auth_key + 绑 socks5)
  GET  /v1/wxpad/login/check      — 轮询扫码状态
  POST /v1/wxpad/host_my_wechat   — 客户 Dashboard 点"托管" · 返代理 zip url + qr
  GET  /v1/wxpad/accounts/{tenant_id}/status — 账号列表 + 隧道状态
  GET  /v1/wxpad/proxy_zip/{account_id} — 下载客户专属 frpc 代理 zip

WxPadPro API 流:
  1. Admin: POST /admin/GenAuthKey1?key=<ADMIN_KEY> body {"Count":1,"Days":365}
     → Data: ["<auth_key>"]
  2. 用户: POST /login/GetLoginQrCodeNew?key=<auth_key> body {"Proxy":"socks5://...","Check":false}
     → Data.QrCodeUrl(可扫) + Data.Key(= auth_key)
  3. POST /login/CheckLoginStatus?key=<auth_key>  → 轮询登录状态
  4. POST /message/SendTextMessage?key=<auth_key> body {"ToWxid":...,"Content":...,"MsgType":1}
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

import aiohttp
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from server.db import session_scope
from server.models import Tenant, WxAccount

logger = logging.getLogger("wechat_agent.wxpadpro_bridge")

router = APIRouter(prefix="/v1/wxpad", tags=["wxpadpro"])


# 消息同步 task 管理
import asyncio as _asyncio
import random as _random
_sync_tasks: dict = {}     # account_id → asyncio.Task

WXPADPRO_BASE_URL = os.getenv("WXPADPRO_BASE_URL", "http://127.0.0.1:8059")
WXPADPRO_ADMIN_KEY = os.getenv("WXPADPRO_ADMIN_KEY", "")


def _compute_reply_latency() -> float:
    """拟真回复延迟 · 指数分布 λ=1/1.5 · clip [2,4] 秒 · 体验优先 + 最低拟真保护."""
    t = _random.expovariate(1 / 1.5)
    return max(2.0, min(4.0, t))


async def _dispatch_reply(account_id: str, from_wxid: str, inbound) -> None:
    """独立 coroutine: AI 生成 → 拟真 sleep → 发送. 不阻塞 sync loop polling."""
    try:
        from server.main import inbound as _handler   # late import 防循环
        suggestion = await _handler(inbound)
        if not suggestion or not getattr(suggestion, "text", ""):
            return
        reply = suggestion.text
        latency = _compute_reply_latency()
        logger.warning("⏳ wait %.1fs before reply to=%s", latency, from_wxid)
        await _asyncio.sleep(latency)
        ok = await wxpad_send_text(account_id, from_wxid, reply)
        logger.warning("✉️ auto reply to=%s ok=%s lat=%.1fs text=%s", from_wxid, ok, latency, reply[:80])
    except Exception as e:
        logger.exception("dispatch reply err: %s", e)


# ─── Pydantic ────────────────────────────────────────────────────────────────

class WxPadCallback(BaseModel):
    TypeName: str = ""
    FromUserName: dict = {}
    ToUserName: dict = {}
    Content: dict = {}
    MsgType: int = 1
    MsgId: int = 0
    PushContent: str = ""
    Appname: str = ""


class HostMyWeChatRequest(BaseModel):
    tenant_id: str


# ─── WxPadPro HTTP 客户端(可指定每次调用的 key) ──────────────────────────────

async def _wxpad_api(
    method: str,
    path: str,
    payload: Optional[dict] = None,
    key: Optional[str] = None,
    timeout: float = 15.0,
) -> Optional[dict]:
    """调 WxPadPro HTTP API.

    key: 传 WxPadPro 的 auth_key 或 ADMIN_KEY. 未传用 WXPADPRO_ADMIN_KEY.
    认证以 ?key=<KEY> query param 传.
    """
    url = f"{WXPADPRO_BASE_URL}{path}"
    params = {"key": key or WXPADPRO_ADMIN_KEY} if (key or WXPADPRO_ADMIN_KEY) else {}
    headers = {"Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            if method.upper() == "GET":
                q = {**params, **(payload or {})}
                async with session.get(url, headers=headers, params=q) as r:
                    return await r.json() if r.status == 200 else None
            async with session.post(url, headers=headers, params=params, json=payload or {}) as r:
                return await r.json() if r.status == 200 else None
    except Exception as e:
        logger.warning("wxpad api %s %s failed: %s", method, path, e)
        return None


async def _gen_auth_key(days: int = 365) -> Optional[str]:
    """Admin 调 /admin/GenAuthKey1 生成一个 auth_key."""
    resp = await _wxpad_api("POST", "/admin/GenAuthKey1", {"Count": 1, "Days": days})
    if resp and resp.get("Code") == 200:
        keys = resp.get("Data") or []
        return keys[0] if keys else None
    logger.warning("gen_auth_key failed: %s", resp)
    return None


# ─── 入站消息 webhook ────────────────────────────────────────────────────────

@router.post("/callback")
async def wxpad_callback(event: WxPadCallback) -> dict:
    """WxPadPro 推送消息."""
    from_wxid = (event.FromUserName or {}).get("string", "")
    content = (event.Content or {}).get("string", "")
    app_id = event.Appname
    msg_type = event.MsgType

    logger.info("wxpad callback type=%s from=%s msg_type=%d", event.TypeName, from_wxid, msg_type)

    if event.TypeName != "AddMsg" or msg_type not in (1, 3, 34, 43):
        return {"ok": True, "skipped": True}

    async with session_scope() as session:
        acc = (await session.execute(
            select(WxAccount).where(WxAccount.app_id == app_id)
        )).scalar_one_or_none()

    if not acc:
        logger.warning("wxpad callback · 未知 app_id=%s", app_id)
        return {"ok": True, "error": "unknown_account"}

    mt_map = {1: "text", 3: "image", 34: "voice", 43: "video"}
    from shared.proto import InboundMsg
    inbound = InboundMsg(
        tenant_id=acc.tenant_id,
        chat_id=from_wxid,
        sender_id=from_wxid,
        sender_name="",
        text=content if msg_type == 1 else "",
        msg_type=mt_map.get(msg_type, "other"),
        timestamp=int(time.time()),
        raw_metadata={
            "wxpad_msg_id": event.MsgId,
            "wxpad_type": msg_type,
            "app_id": app_id,
            "account_id": acc.account_id,
        },
    )

    from server.main import inbound as inbound_handler
    try:
        await inbound_handler(inbound)
    except Exception as e:
        logger.exception("inbound handler failed: %s", e)

    return {"ok": True}


# ─── 步骤 1 · 准备 · 分配端口 + 建账号(不调 WxPadPro) ─────────────────────────

@router.post("/prepare")
async def wxpad_prepare(req: HostMyWeChatRequest) -> dict:
    """一步到位:分配 frp 端口 + 建账号 + 生成 zip URL. 不调 WxPadPro.

    客户拿 zip → 解压 → 双击启动 → frpc 连上 · 此时再调 /v1/wxpad/qr 拉 QR.
    """
    tenant_id = req.tenant_id

    async with session_scope() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail=f"tenant {tenant_id} not found")

    from server.proxy_tunnel_manager import get_tunnel_manager
    tm = get_tunnel_manager()
    account_id = f"wx_{tenant_id[-8:]}_{uuid.uuid4().hex[:6]}"
    frp_port = await tm.allocate_port(tenant_id, account_id)
    frp_token = tm.issue_token(account_id)

    async with session_scope() as session:
        session.add(WxAccount(
            account_id=account_id,
            tenant_id=tenant_id,
            app_id=account_id,
            wxid="",
            status="pending_proxy",
            frp_port=frp_port,
            frp_token=frp_token,
            created_at=int(time.time()),
        ))

    return {
        "account_id": account_id,
        "frp_port": frp_port,
        "frp_token": frp_token,
        "proxy_uri": f"socks5://127.0.0.1:{frp_port}",
        "zip_url": f"/v1/wxpad/proxy_zip/{account_id}",
        "next_step": f"下载 zip · 启动 · 再调 POST /v1/wxpad/qr/{account_id}",
    }


# ─── 步骤 2 · 客户启动代理后 · 拉 QR (走客户家 IP) ───────────────────────────

@router.post("/qr/{account_id}")
async def wxpad_qr(account_id: str) -> dict:
    """客户已启动 proxy.zip · frp 隧道 alive 后调用.

    WxPadPro 用 socks5://127.0.0.1:<frp_port> 出口 · IP 走客户家.
    """
    from server.proxy_tunnel_manager import get_tunnel_manager
    tm = get_tunnel_manager()

    async with session_scope() as session:
        acc = (await session.execute(
            select(WxAccount).where(WxAccount.account_id == account_id)
        )).scalar_one_or_none()
        if not acc:
            raise HTTPException(status_code=404, detail="account not found")

    if not acc.frp_port:
        raise HTTPException(status_code=400, detail="no frp port allocated")

    # 检查 frp 隧道活着
    alive = await tm.is_tunnel_alive(acc.frp_port)
    if not alive:
        raise HTTPException(
            status_code=428,
            detail=f"tunnel 未连 · 请先双击 启动.bat/command · frp_port={acc.frp_port}",
        )

    # 生成 auth_key(首次)
    auth_key = acc.auth_key
    if not auth_key:
        auth_key = await _gen_auth_key()
        if not auth_key:
            raise HTTPException(status_code=502, detail="GenAuthKey 失败")
        async with session_scope() as session:
            row = (await session.execute(
                select(WxAccount).where(WxAccount.account_id == account_id)
            )).scalar_one_or_none()
            if row:
                row.auth_key = auth_key

    # 走客户家 socks5 拉 QR
    proxy_uri = f"socks5://127.0.0.1:{acc.frp_port}"
    resp = await _wxpad_api(
        "POST",
        "/login/GetLoginQrCodeNew",
        {"Proxy": proxy_uri, "Check": True},   # Check=True · WxPadPro 预检代理
        key=auth_key,
    )
    if not resp or resp.get("Code") != 200:
        raise HTTPException(status_code=502, detail=f"GetLoginQrCode 失败: {resp}")

    data = resp.get("Data") or {}
    qr_url = data.get("QrCodeUrl", "")

    async with session_scope() as session:
        row = (await session.execute(
            select(WxAccount).where(WxAccount.account_id == account_id)
        )).scalar_one_or_none()
        if row:
            row.status = "pending_qr"

    return {
        "account_id": account_id,
        "qr_url": qr_url,
        "auth_key": auth_key,
        "proxy_uri": proxy_uri,
    }


# ─── 向后兼容:旧 login/qr 自动 prepare + qr (仅限 tunnel_alive 时) ───────────

@router.post("/login/qr")
async def wxpad_login_qr_legacy(req: HostMyWeChatRequest) -> dict:
    """兼容旧 Dashboard · 自动跑 prepare + qr. 若无代理直接失败."""
    prep = await wxpad_prepare(req)
    account_id = prep["account_id"]
    try:
        qr = await wxpad_qr(account_id)
        return {**prep, **qr}
    except HTTPException as e:
        return {**prep, "qr_error": e.detail}


# ─── 扫码状态轮询 ────────────────────────────────────────────────────────────

@router.get("/login/check")
async def wxpad_login_check(account_id: str) -> dict:
    async with session_scope() as session:
        acc = (await session.execute(
            select(WxAccount).where(WxAccount.account_id == account_id)
        )).scalar_one_or_none()
        if not acc:
            raise HTTPException(status_code=404, detail="account not found")

    # 先试 GetLoginStatus (已登号用) · 若在线直接返
    status_resp = await _wxpad_api("GET", "/login/GetLoginStatus", key=acc.auth_key)
    if status_resp and status_resp.get("Code") == 200:
        sd = status_resp.get("Data") or {}
        if sd.get("loginState") == 1:
            # 已在线 · 确保 db status=online · 再 start sync loop
            async with session_scope() as session:
                row = (await session.execute(
                    select(WxAccount).where(WxAccount.account_id == account_id)
                )).scalar_one_or_none()
                if row:
                    row.status = "online"
                    row.last_heartbeat = int(time.time())
                    if not row.online_since:
                        row.online_since = int(time.time())
            start_sync_loop(account_id)
            return {
                "status": "online",
                "wxid": acc.wxid or "",
                "nickname": acc.nickname or "",
                "online_time": sd.get("onlineTime", ""),
            }

    # 否则扫码阶段 · 查 CheckLoginStatus
    resp = await _wxpad_api("GET", "/login/CheckLoginStatus", key=acc.auth_key)
    if not resp:
        return {"status": "error"}

    data = resp.get("Data") or {}
    login_state = data.get("state", data.get("loginState", 0))
    wxid = data.get("wxid", data.get("userName", ""))
    nickname = data.get("nick_name", data.get("nickName", ""))

    status_map = {0: "pending", 1: "scanned", 2: "online", -1: "expired"}
    status_str = status_map.get(login_state, "pending")

    if status_str == "online" or (wxid and wxid != ""):
        status_str = "online"
        async with session_scope() as session:
            row = (await session.execute(
                select(WxAccount).where(WxAccount.account_id == account_id)
            )).scalar_one_or_none()
            if row:
                row.wxid = wxid
                row.nickname = nickname
                row.status = "online"
                row.online_since = int(time.time())
                row.last_heartbeat = int(time.time())

        # 首次 online · 启动消息同步循环
        start_sync_loop(account_id)

    return {"status": status_str, "wxid": wxid, "nickname": nickname}


# ─── 消息同步循环 ────────────────────────────────────────────────────────────

def start_sync_loop(account_id: str) -> None:
    """启动 account 的消息轮询 task. 幂等."""
    if account_id in _sync_tasks and not _sync_tasks[account_id].done():
        return
    try:
        task = _asyncio.create_task(_sync_loop(account_id))
    except RuntimeError as e:
        logger.warning("start_sync_loop · no running loop: %s", e)
        return
    _sync_tasks[account_id] = task
    logger.warning("🔄 start_sync_loop account=%s", account_id)


async def _sync_loop(account_id: str):
    """每 3s 直连 Redis `<auth_key>_syncMsg` · LRANGE 新包 · 去重.

    WxPadPro 的 HTTP API (HttpSyncMsg/GetRedisSyncMsg) 行为不一致 · 直读 Redis 最稳.
    """
    import json as _json
    from shared.proto import InboundMsg
    from server.main import inbound as inbound_handler

    # Redis 连接 · 用 redis.asyncio
    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.error("redis lib 缺 · pip install redis")
        return

    r = aioredis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "1")),
        password=os.getenv("REDIS_PASSWORD", ""),
        decode_responses=True,
    )

    consecutive_errors = 0
    while True:
        try:
            async with session_scope() as session:
                acc = (await session.execute(
                    select(WxAccount).where(WxAccount.account_id == account_id)
                )).scalar_one_or_none()
            if not acc or acc.status != "online" or not acc.auth_key:
                logger.info("sync loop exit · account=%s not online", account_id)
                break

            # 直连 Redis 读 `<auth_key>_syncMsg` list 最新 20 包
            redis_key = f"{acc.auth_key}_syncMsg"
            raw_pkts = await r.lrange(redis_key, 0, 20)
            if not raw_pkts:
                await _asyncio.sleep(3)
                continue

            # 把所有包的 AddMsgs 合并 · 按 new_msg_id 排序
            msgs = []
            for raw in raw_pkts:
                try:
                    pkt = _json.loads(raw)
                    pkt_msgs = pkt.get("AddMsgs") or []
                    msgs.extend(pkt_msgs)
                except Exception:
                    continue

            # 水位线用 create_time (Unix 秒 · 严格单调) · 不用 new_msg_id(各 msg_type 独立 ID 池 · 不单调)
            last_ct = int(acc.last_msg_id or 0)
            new_max_ct = last_ct

            for m in msgs:
                create_time = int(m.get("create_time") or 0)
                if create_time <= last_ct:
                    continue

                msg_type = m.get("msg_type", 0)
                from_wxid = (m.get("from_user_name") or {}).get("str", "")
                to_wxid = (m.get("to_user_name") or {}).get("str", "")
                content = (m.get("content") or {}).get("str", "")

                # 过滤:自己发的 / 群消息(@chatroom) / 非文字
                if from_wxid == acc.wxid:
                    new_max_ct = max(new_max_ct, create_time)
                    continue
                if "@chatroom" in from_wxid:
                    new_max_ct = max(new_max_ct, create_time)
                    continue
                if msg_type != 1:
                    new_max_ct = max(new_max_ct, create_time)
                    continue
                if not content:
                    new_max_ct = max(new_max_ct, create_time)
                    continue

                new_max_ct = max(new_max_ct, create_time)
                new_msg_id = int(m.get("new_msg_id", 0))
                inbound = InboundMsg(
                    tenant_id=acc.tenant_id,
                    chat_id=from_wxid,
                    sender_id=from_wxid,
                    sender_name="",
                    text=content,
                    msg_type="text",
                    timestamp=create_time or int(time.time()),
                    raw_metadata={
                        "wxpad_new_msg_id": str(new_msg_id),
                        "wxpad_msg_id": m.get("msg_id", 0),
                        "account_id": account_id,
                        "to_wxid": to_wxid,
                    },
                )

                logger.warning("📨 inbound from=%s text=%s ct=%s", from_wxid, content[:60], create_time)
                # 派独立 coroutine · sleep 不阻塞下条消息 polling
                _asyncio.create_task(_dispatch_reply(account_id, from_wxid, inbound))

            if new_max_ct > last_ct:
                async with session_scope() as session:
                    row = (await session.execute(
                        select(WxAccount).where(WxAccount.account_id == account_id)
                    )).scalar_one_or_none()
                    if row:
                        row.last_msg_id = str(new_max_ct)
                        row.last_heartbeat = int(time.time())

        except Exception as e:
            logger.exception("sync loop unexpected: %s", e)
            await _asyncio.sleep(5)

        await _asyncio.sleep(1)

    _sync_tasks.pop(account_id, None)


# 启动时扫已 online 的号 · 恢复 sync loop
async def resume_sync_loops_on_startup():
    """server 启动时 · 查所有 online account · 恢复 sync loop."""
    async with session_scope() as session:
        rows = (await session.execute(
            select(WxAccount).where(WxAccount.status == "online")
        )).scalars().all()
    for r in rows:
        start_sync_loop(r.account_id)
    logger.info("resume_sync_loops · restored %d accounts", len(rows))


# ─── 一键托管入口 ────────────────────────────────────────────────────────────

@router.post("/host_my_wechat")
async def host_my_wechat(req: HostMyWeChatRequest) -> dict:
    return {
        "step_1_zip_url_base": "/v1/wxpad/proxy_zip",
        "step_2_qr_url": "/v1/wxpad/login/qr",
        "instructions": "1. 调 /v1/wxpad/login/qr 获 account_id + qr\n2. 用 account_id 下载 /v1/wxpad/proxy_zip/{account_id}\n3. 解压 · 双击启动.bat · 代理连上\n4. 扫 qr_url 登号",
    }


# ─── 发消息 ──────────────────────────────────────────────────────────────────

async def wxpad_send_text(account_id: str, to_wxid: str, text: str) -> bool:
    async with session_scope() as session:
        acc = (await session.execute(
            select(WxAccount).where(WxAccount.account_id == account_id)
        )).scalar_one_or_none()
        if not acc or not acc.auth_key:
            return False

    # 实测: WxPadPro SendTextMessage body 结构 · MsgItem 数组 · ToUserName + TextContent + MsgType
    resp = await _wxpad_api(
        "POST",
        "/message/SendTextMessage",
        {"MsgItem": [{"ToUserName": to_wxid, "TextContent": text, "MsgType": 1}]},
        key=acc.auth_key,
    )
    ok = False
    if resp and resp.get("Code") == 200:
        items = resp.get("Data") or []
        ok = any(it.get("isSendSuccess") for it in items) if isinstance(items, list) else False
    logger.info("wxpad send text account=%s to=%s ok=%s", account_id, to_wxid, ok)
    return ok


# ─── 代理 zip 下载 ───────────────────────────────────────────────────────────

@router.get("/proxy_zip/{account_id}")
async def download_proxy_zip(account_id: str, os: str = "win"):
    """下载客户代理 zip. os: win (默认 · Win 单 exe ~4.5MB) / mac / all."""
    from fastapi.responses import FileResponse
    async with session_scope() as session:
        acc = (await session.execute(
            select(WxAccount).where(WxAccount.account_id == account_id)
        )).scalar_one_or_none()
        if not acc or not acc.frp_port:
            raise HTTPException(status_code=404, detail="account not found or no frp port")

    from installer.pack_proxy_zip import pack_for_account
    os_target = os if os in ("win", "mac", "all") else "win"
    zip_path = pack_for_account(
        tenant_id=acc.tenant_id,
        account_id=account_id,
        frp_port=acc.frp_port,
        token=acc.frp_token or "",
        os_target=os_target,
    )
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )


# ─── 账号状态列表 ────────────────────────────────────────────────────────────

@router.get("/accounts/{tenant_id}/status")
async def accounts_status(tenant_id: str) -> dict:
    now = int(time.time())
    from server.proxy_tunnel_manager import get_tunnel_manager
    tm = get_tunnel_manager()

    async with session_scope() as session:
        rows = (await session.execute(
            select(WxAccount).where(WxAccount.tenant_id == tenant_id)
        )).scalars().all()

    accounts = []
    for r in rows:
        tunnel_alive = await tm.is_tunnel_alive(r.frp_port) if r.frp_port else False
        accounts.append({
            "account_id": r.account_id,
            "wxid": r.wxid or "",
            "nickname": r.nickname or "",
            "status": r.status,
            "frp_port": r.frp_port,
            "tunnel_alive": tunnel_alive,
            "online_since": r.online_since,
            "last_heartbeat": r.last_heartbeat,
        })

    return {"tenant_id": tenant_id, "accounts": accounts, "server_ts": now}
