"""全局限流(slowapi) — 与 main 中 Limiter state 绑定。"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# 默认全局限流;敏感接口在路由上再叠加更严的 limit
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    enabled=True,
)
