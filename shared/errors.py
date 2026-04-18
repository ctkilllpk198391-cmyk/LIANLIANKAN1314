"""错误层级 · 所有自定义异常的基类。"""

from __future__ import annotations


class BaiyangError(Exception):
    """所有 wechat_agent 业务错误的基类。"""

    code = "baiyang_error"
    http_status = 500


class CrossTenantError(BaiyangError):
    """检测到跨 tenant 数据访问 · 红线。"""

    code = "cross_tenant_violation"
    http_status = 403


class ForbiddenWordError(BaiyangError):
    """生成内容命中禁用词。"""

    code = "forbidden_word"
    http_status = 422


class QuotaExceededError(BaiyangError):
    """日配额超限。"""

    code = "quota_exceeded"
    http_status = 429


class DuplicateMessageError(BaiyangError):
    """7 天滑窗内相似消息。"""

    code = "duplicate_message"
    http_status = 422


class WorkhourViolationError(BaiyangError):
    """工作时间外尝试发送。"""

    code = "workhour_violation"
    http_status = 425


class TenantNotFoundError(BaiyangError):
    code = "tenant_not_found"
    http_status = 404


class HermesUnreachableError(BaiyangError):
    code = "hermes_unreachable"
    http_status = 503
