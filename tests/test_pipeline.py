"""pipeline 测试 · 提取/去敏/配对/训练配置/judge。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.extract_chat import (
    ChatExtractor,
    RawMsg,
    TrainingPair,
    clean_pairs,
    desensitize,
    is_noise_reply,
    pair_messages,
    parse_wechatmsg_sqlite,
)
from pipeline.judge import JudgeLLM, JudgeScore, render_eval_report
from pipeline.train_lora import (
    LoRAConfig,
    TrainingLauncher,
    estimate_training_time,
    make_oom_fallback,
    render_llama_factory_yaml,
    write_training_config,
)


# ─── desensitize ──────────────────────────────────────────────────────
def test_desensitize_phone():
    assert desensitize("我电话13812345678给你") == "我电话[手机]给你"


def test_desensitize_email():
    out = desensitize("发到 a.b+c@example.cn 哦")
    assert "[邮箱]" in out and "@" not in out


def test_desensitize_link():
    assert "[链接]" in desensitize("看 https://example.com/path 这个")


def test_desensitize_id_card():
    assert "[身份证]" in desensitize("身份证 11010119901010123X")


def test_desensitize_bank_card():
    assert "[卡号]" in desensitize("打卡 6225889911234567")


def test_desensitize_combined():
    src = "电话13812345678 邮箱x@y.com 链接http://a.b"
    out = desensitize(src)
    assert "13812345678" not in out
    assert "x@y.com" not in out
    assert "http" not in out


# ─── noise filter ──────────────────────────────────────────────────────
def test_noise_short():
    assert is_noise_reply("好的") is True


def test_noise_long():
    assert is_noise_reply("a" * 400) is True


def test_noise_emoji():
    assert is_noise_reply("😀😀😀😀😀😀😀😀😀😀😀😀") is True


def test_noise_punct():
    assert is_noise_reply("...!!!....!!!.....") is True


def test_legit_reply():
    assert is_noise_reply("您好，欢迎光临，这款面膜适合干性肌肤，您可以先试用装") is False


# ─── pair_messages ─────────────────────────────────────────────────────
def test_pair_messages_basic():
    rows = [
        RawMsg(talker="wx_a", is_sender=0, msg_type=1, content="多少钱", create_time=100),
        RawMsg(talker="wx_a", is_sender=1, msg_type=1, content="您好这款199", create_time=120),
    ]
    pairs = pair_messages(rows)
    assert len(pairs) == 1
    assert pairs[0].customer_msg == "多少钱"
    assert pairs[0].boss_reply == "您好这款199"


def test_pair_messages_merge_customer():
    rows = [
        RawMsg(talker="wx_b", is_sender=0, msg_type=1, content="在么", create_time=100),
        RawMsg(talker="wx_b", is_sender=0, msg_type=1, content="问下价格", create_time=150),
        RawMsg(talker="wx_b", is_sender=1, msg_type=1, content="您好这款199", create_time=200),
    ]
    pairs = pair_messages(rows)
    assert len(pairs) == 1
    assert "在么" in pairs[0].customer_msg
    assert "问下价格" in pairs[0].customer_msg


def test_pair_messages_window_resets():
    rows = [
        RawMsg(talker="wx_c", is_sender=0, msg_type=1, content="你好", create_time=100),
        # 5 分钟外
        RawMsg(talker="wx_c", is_sender=0, msg_type=1, content="价格?", create_time=500),
        RawMsg(talker="wx_c", is_sender=1, msg_type=1, content="199", create_time=520),
    ]
    pairs = pair_messages(rows)
    assert len(pairs) == 1
    assert "你好" not in pairs[0].customer_msg
    assert pairs[0].customer_msg == "价格?"


def test_pair_skip_image_type():
    rows = [
        RawMsg(talker="wx_d", is_sender=0, msg_type=3, content="[图片]", create_time=100),
        RawMsg(talker="wx_d", is_sender=0, msg_type=1, content="多少", create_time=110),
        RawMsg(talker="wx_d", is_sender=1, msg_type=1, content="199", create_time=120),
    ]
    pairs = pair_messages(rows)
    assert len(pairs) == 1
    assert "[图片]" not in pairs[0].customer_msg


def test_pair_no_orphan_boss_reply():
    rows = [
        RawMsg(talker="wx_e", is_sender=1, msg_type=1, content="主动消息", create_time=100),
    ]
    assert pair_messages(rows) == []


# ─── clean_pairs ───────────────────────────────────────────────────────
def test_clean_drops_noise_reply():
    pairs = [
        TrainingPair(
            customer_msg="价格", boss_reply="好的", chat_name="x", timestamp=0
        ),
    ]
    assert clean_pairs(pairs) == []


def test_clean_desensitizes():
    pairs = [
        TrainingPair(
            customer_msg="电话13812345678", boss_reply="您好这款面膜199元包邮哦", chat_name="x", timestamp=0
        ),
    ]
    out = clean_pairs(pairs)
    assert len(out) == 1
    assert "13812345678" not in out[0].customer_msg


# ─── parse_wechatmsg_sqlite ────────────────────────────────────────────
def test_parse_sqlite(tmp_path):
    db_path = tmp_path / "MSG.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE MSG (
            localId INTEGER PRIMARY KEY,
            talker TEXT,
            isSender INTEGER,
            type INTEGER,
            content TEXT,
            createTime INTEGER
        );
        INSERT INTO MSG VALUES (1, 'wx_a', 0, 1, '多少钱', 100);
        INSERT INTO MSG VALUES (2, 'wx_a', 1, 1, '您好这款199元包邮', 120);
        """
    )
    conn.commit()
    conn.close()

    rows = parse_wechatmsg_sqlite(db_path)
    assert len(rows) == 2
    assert rows[0].talker == "wx_a"
    assert rows[1].is_sender == 1


def test_parse_sqlite_missing_raises():
    with pytest.raises(FileNotFoundError):
        parse_wechatmsg_sqlite(Path("/nonexistent/db.sqlite"))


# ─── ChatExtractor end-to-end ──────────────────────────────────────────
def test_chat_extractor_e2e(tmp_path):
    db_path = tmp_path / "MSG.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE MSG (
            localId INTEGER PRIMARY KEY,
            talker TEXT, isSender INTEGER, type INTEGER, content TEXT, createTime INTEGER
        );
        INSERT INTO MSG VALUES (1,'wx_x',0,1,'在么 老板',100);
        INSERT INTO MSG VALUES (2,'wx_x',1,1,'您好欢迎咨询任何问题',120);
        INSERT INTO MSG VALUES (3,'wx_x',0,1,'电话13812345678',200);
        INSERT INTO MSG VALUES (4,'wx_x',1,1,'稍等我看看您的订单详情',220);
        INSERT INTO MSG VALUES (5,'wx_x',0,1,'好的',300);
        INSERT INTO MSG VALUES (6,'wx_x',1,1,'好的',320);
        """
    )
    conn.commit()
    conn.close()

    out_dir = tmp_path / "out"
    extractor = ChatExtractor("tenant_test", out_dir)
    pairs = extractor.extract_from_wechatmsg(db_path)
    assert len(pairs) == 2  # 第3对老板回复"好的"被噪音过滤
    assert "[手机]" in pairs[1].customer_msg

    train_path = extractor.write_jsonl(pairs)
    assert train_path.exists()
    lines = train_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2

    chatml_path = extractor.write_chatml_jsonl(pairs)
    obj = json.loads(chatml_path.read_text(encoding="utf-8").splitlines()[0])
    assert obj["messages"][0]["role"] == "user"
    assert obj["messages"][1]["role"] == "assistant"


# ─── train_lora ────────────────────────────────────────────────────────
def test_lora_config_defaults():
    cfg = LoRAConfig(tenant_id="t1")
    assert cfg.lora_rank == 16
    assert cfg.quantization == "4bit"


def test_render_yaml():
    cfg = LoRAConfig(tenant_id="tenant_xyz")
    payload = render_llama_factory_yaml(cfg)
    assert payload["finetuning_type"] == "lora"
    assert payload["quantization_bit"] == 4
    assert "tenant_xyz" in payload["dataset"]
    assert "tenant_xyz" in payload["output_dir"]
    assert payload["use_unsloth"] is True


def test_write_yaml_file(tmp_path):
    cfg = LoRAConfig(tenant_id="t2")
    out = tmp_path / "config" / "train.yaml"
    written = write_training_config(cfg, out)
    assert written.exists()
    text = written.read_text()
    assert "lora_rank: 16" in text or "lora_rank:16" in text


def test_oom_fallback():
    cfg = LoRAConfig(tenant_id="t3", batch_size=8, grad_accum=2, max_seq_length=2048)
    fb = make_oom_fallback(cfg)
    assert fb.batch_size == 4
    assert fb.grad_accum == 4
    assert fb.max_seq_length == 1024


def test_estimate_time():
    secs = estimate_training_time(num_samples=1500, num_epochs=3)
    assert secs > 0


@pytest.mark.asyncio
async def test_launcher_mock_when_cmd_missing():
    launcher = TrainingLauncher(llama_factory_cmd="this_cmd_does_not_exist_zzz")
    assert launcher.is_available() is False
    state = await launcher.launch(Path("/tmp/dummy.yaml"))
    assert state.return_code == 0
    assert state.last_loss is not None


# ─── judge ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_judge_parses_valid_json():
    from server.hermes_bridge import HermesBridge

    class FakeBridge(HermesBridge):
        async def respond(self, prompt, tenant_id, model_route, max_tokens=300, style_hints=None):
            return '{"style_match": 0.7, "naturalness": 0.8, "on_topic": 0.9, "comment": "good"}'

    judge = JudgeLLM(hermes=FakeBridge(mock=True))
    score = await judge.judge("客户问", "老板答", "AI 生成的回答")
    assert score.style_match == 0.7
    assert score.naturalness == 0.8
    assert 0.7 <= score.overall <= 0.9


@pytest.mark.asyncio
async def test_judge_handles_garbage():
    from server.hermes_bridge import HermesBridge

    class GarbageBridge(HermesBridge):
        async def respond(self, prompt, tenant_id, model_route, max_tokens=300, style_hints=None):
            return "I'm sorry I can't comply"

    judge = JudgeLLM(hermes=GarbageBridge(mock=True))
    score = await judge.judge("a", "b", "c")
    assert score.comment == "judge_parse_failed"
    assert score.style_match == 0.5  # 兜底


def test_judge_score_overall():
    s = JudgeScore(style_match=1.0, naturalness=1.0, on_topic=1.0, comment="")
    assert abs(s.overall - 1.0) < 1e-6


def test_render_eval_report():
    rows = [
        # 用 JudgeLLM 测试中的 import
    ]
    from pipeline.judge import EvalReportRow

    rows = [
        EvalReportRow(
            customer_msg="价格?",
            boss_real="199 包邮",
            ai_generated="您好 199 包邮哦",
            score=JudgeScore(style_match=0.8, naturalness=0.9, on_topic=1.0, comment="ok"),
        ),
    ]
    md = render_eval_report("tenant_x", rows, forbidden_word_rate=0.0, over_length_rate=0.0)
    assert "tenant_x" in md
    assert "✅" in md
    assert "199 包邮" in md
