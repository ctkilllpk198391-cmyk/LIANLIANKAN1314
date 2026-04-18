"""AuditLogger · 合规核心 · 每条消息全链 5 节点。"""

from __future__ import annotations

import json
import time
from typing import Optional

from server.db import session_scope
from server.models import AuditLog


class AuditLogger:
    """所有重要动作必须经过这里。"""

    @staticmethod
    async def log(
        actor: str,
        action: str,
        tenant_id: str,
        msg_id: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> int:
        async with session_scope() as session:
            entry = AuditLog(
                actor=actor,
                action=action,
                tenant_id=tenant_id,
                msg_id=msg_id,
                meta=json.dumps(meta or {}, ensure_ascii=False),
                timestamp=int(time.time()),
            )
            session.add(entry)
            await session.flush()
            return entry.id


# 便捷别名
audit = AuditLogger()
