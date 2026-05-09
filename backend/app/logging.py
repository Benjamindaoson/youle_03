"""structlog 配置 — 全局 JSON 日志,带 task_id / user_id。

铁律:禁止 print / logging.info,统一用 structlog。
"""

import logging
import re
import sys

import structlog

from app.config import settings


_SENSITIVE_KEY_RE = re.compile(r"(password|secret|token|authorization|credential|jwt|sms_code)", re.I)
_SENSITIVE_EXACT_KEYS = frozenset(
    {"phone", "code", "access_token", "refresh_token"}
)

# M-8: Value 级 PII 扫描 — 中国手机号(11位1开头)和 Bearer token 格式
_PHONE_VALUE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_BEARER_VALUE_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}", re.I)
_LONG_TOKEN_VALUE_RE = re.compile(r"[A-Za-z0-9._\-]{60,}")


def _scrub_sensitive_keys(
    _: structlog.types.Processor,
    __: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """结构化日志中对短信码、token、完整手机号等做字段级脱敏。"""
    for k in list(event_dict.keys()):
        lk = str(k).lower()
        if lk in _SENSITIVE_EXACT_KEYS or _SENSITIVE_KEY_RE.search(lk):
            val = event_dict[k]
            if isinstance(val, str) and lk == "phone" and len(val) >= 11:
                event_dict[k] = f"...{val[-4:]}"
            else:
                event_dict[k] = "[REDACTED]"
    return event_dict


def _scrub_sensitive_values(
    _: structlog.types.Processor,
    __: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """对字段 Value 中的 PII 做正则脱敏(手机号 / Bearer token)。

    仅处理字符串类型 value,不递归嵌套 dict(避免误伤合法 JSON 日志字段)。
    """
    for k, v in list(event_dict.items()):
        if not isinstance(v, str) or len(v) < 10:
            continue
        # 手机号脱敏:替换为 1xx****xxxx
        v2 = _PHONE_VALUE_RE.sub(lambda m: m.group()[:3] + "****" + m.group()[-4:], v)
        # Bearer token 脱敏
        v2 = _BEARER_VALUE_RE.sub("[BEARER_REDACTED]", v2)
        if v2 != v:
            event_dict[k] = v2
    return event_dict


def configure_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _scrub_sensitive_keys,
        _scrub_sensitive_values,
    ]

    if settings.is_dev:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=log_level, stream=sys.stdout, format="%(message)s")


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
