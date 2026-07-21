"""structlog 配置 — 全局 JSON 日志,带 task_id / user_id。

铁律:禁止 print / logging.info,统一用 structlog。

脱敏分两层:
  1. 字段级(structlog processor):识别敏感 key、把 phone 改 1xx****xxxx
     —— 在结构化字段上工作,精度高、最优先。
  2. 字符串级(`RedactingFormatter` + `_redact_full_event` processor):
     把 `app.utils.redact` 的 30+ 厂商 API key / JWT / DB 连接串 / Bearer
     等正则全打过去,作为最后一道兜底,捕获 value 中嵌入的密钥。
"""

import logging
import re
import sys

import structlog

from app.config import settings
from app.utils.redact import RedactingFormatter, redact_sensitive_text

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


def _redact_full_event(
    _: structlog.types.Processor,
    __: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """兜底层 — 把 30+ 厂商 API key / JWT / DB 连接串等正则打过整个 value。

    放在 `_scrub_sensitive_values` 之后,只处理依然是字符串的字段;长度阈值
    放宽到 8 以兼容 ``sk-xxxx``(前缀 3 + tail 5 即可触发某些短 token 规则)。

    `force=True` 让该 processor 即便部署关闭了 ``YOULE_REDACT_SECRETS`` 也
    保持工作 —— 日志是安全边界,绝不允许漏密钥。
    """
    for k, v in list(event_dict.items()):
        if not isinstance(v, str) or len(v) < 8:
            continue
        v2 = redact_sensitive_text(v, force=True)
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
        _redact_full_event,
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

    # stdlib logging 也走 RedactingFormatter — 第三方库(uvicorn / httpx /
    # alembic 等)直接 logging.info 时,密钥不会漏到 stdout/Sentry。
    root_handler = logging.StreamHandler(stream=sys.stdout)
    root_handler.setFormatter(RedactingFormatter("%(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(root_handler)
    root.setLevel(log_level)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
