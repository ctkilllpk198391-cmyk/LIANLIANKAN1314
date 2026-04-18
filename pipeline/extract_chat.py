"""聊天记录提取 · WeChatMsg sqlite 解析 + 配对 + 去敏 + 过滤。"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

PAIR_WINDOW_SEC = 300
MIN_REPLY_LEN = 10
MAX_REPLY_LEN = 300

DESENSITIZE_PATTERNS = [
    (re.compile(r"https?://\S+"), "[链接]"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[邮箱]"),
    (re.compile(r"(?<!\d)\d{17}[\dxX](?!\d)"), "[身份证]"),
    (re.compile(r"(?<!\d)\d{15,19}(?!\d)"), "[卡号]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机]"),
]

NOISE_PHRASES = {"哈哈", "呵呵", "嗯嗯", "好的", "知道了", "ok", "okay", "嗯", "好"}
EMOJI_ONLY_RE = re.compile(r"^[\U0001F300-\U0001FAFF\u2600-\u27BF\s]+$")
PUNCT_ONLY_RE = re.compile(r"^[\W_]+$", re.UNICODE)


@dataclass
class RawMsg:
    """从 sqlite 读出来的原始消息。"""

    talker: str
    is_sender: int
    msg_type: int
    content: str
    create_time: int


@dataclass
class TrainingPair:
    """训练样本对。"""

    customer_msg: str
    boss_reply: str
    chat_name: str
    timestamp: int
    raw_context: list[str] = field(default_factory=list)


def desensitize(text: str) -> str:
    out = text
    for pat, repl in DESENSITIZE_PATTERNS:
        out = pat.sub(repl, out)
    return out


def is_noise_reply(text: str) -> bool:
    s = text.strip()
    if not s:
        return True
    if len(s) < MIN_REPLY_LEN:
        return True
    if len(s) > MAX_REPLY_LEN:
        return True
    if s in NOISE_PHRASES:
        return True
    if EMOJI_ONLY_RE.match(s):
        return True
    if PUNCT_ONLY_RE.match(s):
        return True
    return False


def pair_messages(rows: Iterable[RawMsg]) -> list[TrainingPair]:
    """按时间顺序遍历 · (客户多条 → 老板回复) 配对 · 5min 滑窗。"""
    pairs: list[TrainingPair] = []
    pending: list[str] = []
    last_customer_ts = 0
    talker_for_pair: Optional[str] = None

    for row in sorted(rows, key=lambda r: r.create_time):
        if row.msg_type != 1:
            continue
        if row.is_sender == 0:  # 客户
            if pending and row.create_time - last_customer_ts > PAIR_WINDOW_SEC:
                pending = []
            pending.append(row.content)
            last_customer_ts = row.create_time
            talker_for_pair = row.talker
        else:  # 老板回复
            if not pending or talker_for_pair is None:
                continue
            pairs.append(
                TrainingPair(
                    customer_msg="\n".join(pending),
                    boss_reply=row.content,
                    chat_name=talker_for_pair,
                    timestamp=row.create_time,
                    raw_context=pending.copy(),
                )
            )
            pending = []
            talker_for_pair = None

    return pairs


def clean_pairs(pairs: Iterable[TrainingPair]) -> list[TrainingPair]:
    """去敏 + 噪音过滤。"""
    out: list[TrainingPair] = []
    for p in pairs:
        if is_noise_reply(p.boss_reply):
            continue
        out.append(
            TrainingPair(
                customer_msg=desensitize(p.customer_msg),
                boss_reply=desensitize(p.boss_reply),
                chat_name=p.chat_name,
                timestamp=p.timestamp,
                raw_context=[desensitize(s) for s in p.raw_context],
            )
        )
    return out


def parse_wechatmsg_sqlite(db_path: Path) -> list[RawMsg]:
    """从 WeChatMsg 导出的 MSG.db 解析。

    schema 参考: https://github.com/LC044/WeChatMsg
    """
    if not db_path.exists():
        raise FileNotFoundError(f"WeChatMsg db not found: {db_path}")

    rows: list[RawMsg] = []
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT talker, isSender, type, content, createTime FROM MSG ORDER BY createTime ASC"
        )
        for talker, is_sender, msg_type, content, create_time in cur:
            rows.append(
                RawMsg(
                    talker=talker or "",
                    is_sender=int(is_sender or 0),
                    msg_type=int(msg_type or 0),
                    content=content or "",
                    create_time=int(create_time or 0),
                )
            )
    except sqlite3.Error as e:
        logger.error("sqlite parse failed: %s", e)
        raise
    finally:
        conn.close()

    logger.info("parsed %d raw msgs from %s", len(rows), db_path)
    return rows


class ChatExtractor:
    """完整流水线：sqlite → 配对 → 清洗 → jsonl。"""

    def __init__(self, tenant_id: str, output_dir: Path):
        self.tenant_id = tenant_id
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_from_wechatmsg(self, sqlite_path: Path) -> list[TrainingPair]:
        rows = parse_wechatmsg_sqlite(sqlite_path)
        raw_pairs = pair_messages(rows)
        cleaned = clean_pairs(raw_pairs)
        logger.info(
            "extracted %d clean pairs (raw=%d, dropped=%d)",
            len(cleaned),
            len(raw_pairs),
            len(raw_pairs) - len(cleaned),
        )
        return cleaned

    def write_jsonl(
        self, pairs: Iterable[TrainingPair], filename: str = "train.jsonl"
    ) -> Path:
        out = self.output_dir / filename
        n = 0
        with out.open("w", encoding="utf-8") as f:
            for p in pairs:
                f.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
                n += 1
        logger.info("wrote %d training pairs → %s", n, out)
        return out

    def write_chatml_jsonl(
        self, pairs: Iterable[TrainingPair], filename: str = "train_chatml.jsonl"
    ) -> Path:
        out = self.output_dir / filename
        n = 0
        with out.open("w", encoding="utf-8") as f:
            for p in pairs:
                payload = {
                    "messages": [
                        {"role": "user", "content": p.customer_msg},
                        {"role": "assistant", "content": p.boss_reply},
                    ]
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                n += 1
        logger.info("wrote %d ChatML pairs → %s", n, out)
        return out

    @staticmethod
    def to_chatml_format(pair: TrainingPair) -> dict:
        return {
            "messages": [
                {"role": "user", "content": pair.customer_msg},
                {"role": "assistant", "content": pair.boss_reply},
            ]
        }
