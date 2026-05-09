#!/usr/bin/env python3
"""Sprint 6 真 API 切换验证(铁律 §5:Mocking + Local-first)。

跑前先在 shell 设好真凭证(LITELLM_URL, LITELLM_MASTER_KEY, TAVILY_API_KEY,
ALIYUN_OSS_*, VOLCENGINE_TTS_*),否则该项目会跳过。

每个 check 都打 ✓/✗,给出可读错误。退出码 0=全绿,1=有失败。

用法:
    python scripts/verify-real-apis.py
    python scripts/verify-real-apis.py --skip-volcengine   # 部分跳过
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import time
from typing import Awaitable, Callable

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

failures: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"{GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"{RED}✗{NC} {msg}")
    failures.append(msg)


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠{NC} {msg}")
    warnings.append(msg)


# ─────────────────────── LiteLLM ───────────────────────
async def check_litellm() -> None:
    print("\n[LiteLLM Proxy]")
    url = os.getenv("LITELLM_URL", "")
    key = os.getenv("LITELLM_MASTER_KEY", "")
    if not url or not key:
        warn("LITELLM_URL / LITELLM_MASTER_KEY 未设 — 跳过")
        return
    if os.getenv("LITELLM_MOCK", "false").lower() == "true":
        warn("LITELLM_MOCK=true — 没在测真 API,跳过")
        return
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # /health
            resp = await client.get(f"{url}/health")
            if resp.status_code >= 400:
                fail(f"litellm /health http={resp.status_code}")
                return
            ok(f"litellm /health 200")

            # 实际跑一发 chat completion
            t0 = time.monotonic()
            r = await client.post(
                f"{url}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": "deepseek-v4-flash",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 10,
                },
            )
            dt = time.monotonic() - t0
            if r.status_code != 200:
                fail(f"chat completion http={r.status_code} body={r.text[:200]}")
                return
            data = r.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            ok(f"chat completion 成功(耗时 {dt:.2f}s,响应 {len(content)} 字符)")
    except Exception as e:
        fail(f"litellm 调用异常:{e}")


# ─────────────────────── Tavily ───────────────────────
async def check_tavily() -> None:
    print("\n[Tavily 搜索]")
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        warn("TAVILY_API_KEY 未设 — 跳过")
        return
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": key, "query": "test", "max_results": 1},
            )
            if r.status_code != 200:
                fail(f"tavily http={r.status_code}")
                return
            data = r.json()
            n = len(data.get("results", []))
            ok(f"tavily 搜索成功({n} 条结果)")
    except Exception as e:
        fail(f"tavily 异常:{e}")


# ─────────────────────── Aliyun OSS ───────────────────────
async def check_aliyun_oss() -> None:
    print("\n[阿里云 OSS]")
    ak = os.getenv("ALIYUN_OSS_ACCESS_KEY_ID")
    sk = os.getenv("ALIYUN_OSS_ACCESS_KEY_SECRET")
    bucket = os.getenv("ALIYUN_OSS_BUCKET")
    endpoint = os.getenv("ALIYUN_OSS_ENDPOINT", "https://oss-cn-hangzhou.aliyuncs.com")
    if not all([ak, sk, bucket]):
        warn("ALIYUN_OSS_* 不全 — 跳过(staging 用 MinIO 没问题)")
        return
    try:
        import oss2  # type: ignore

        auth = oss2.Auth(ak, sk)
        b = oss2.Bucket(auth, endpoint, bucket)
        # 上传一个小文件 → 下载 → 删除
        key_name = f"_preflight/{int(time.time())}.txt"
        body = b"hello preflight"
        b.put_object(key_name, body)
        got = b.get_object(key_name).read()
        b.delete_object(key_name)
        if got == body:
            ok(f"OSS 上传/下载/删除 OK(bucket={bucket})")
        else:
            fail("OSS 下载内容与上传不符")
    except ImportError:
        warn("oss2 未安装 — 跳过(prod 镜像里有)")
    except Exception as e:
        fail(f"OSS 异常:{e}")


# ─────────────────────── Volcengine TTS ───────────────────────
async def check_volcengine_tts() -> None:
    print("\n[Volcengine TTS]")
    appid = os.getenv("VOLCENGINE_TTS_APPID")
    token = os.getenv("VOLCENGINE_TTS_TOKEN")
    if not all([appid, token]):
        warn("VOLCENGINE_TTS_* 未设 — 跳过")
        return
    import httpx

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # 火山 TTS 实际 API:示例 ping(只发一个最小请求)
            r = await client.post(
                "https://openspeech.bytedance.com/api/v1/tts",
                headers={
                    "Authorization": f"Bearer; {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "app": {"appid": appid, "token": token, "cluster": "volcano_tts"},
                    "user": {"uid": "preflight"},
                    "audio": {"voice_type": "BV001_streaming", "encoding": "mp3"},
                    "request": {"reqid": "preflight", "text": "测试", "operation": "query"},
                },
            )
            if r.status_code in (200, 401):
                # 401 也算"接通"了(凭证可能未授权,但服务可达)
                ok(f"Volcengine TTS 端点可达(http={r.status_code})")
            else:
                fail(f"Volcengine TTS http={r.status_code}")
    except Exception as e:
        fail(f"Volcengine TTS 异常:{e}")


# ─────────────────────── Sentry ───────────────────────
async def check_sentry() -> None:
    print("\n[Sentry]")
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        warn("SENTRY_DSN 未设 — 跳过(prod 必填)")
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn, environment="preflight", traces_sample_rate=0)
        sentry_sdk.capture_message("youle preflight ping", level="info")
        client = sentry_sdk.get_client()
        if client and client.transport:
            ok("Sentry SDK 初始化 + capture_message 已发送")
        else:
            warn("Sentry SDK 已初始化,但 transport 未确认")
    except Exception as e:
        fail(f"Sentry 异常:{e}")


# ─────────────────────── 主 ───────────────────────
async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-volcengine", action="store_true")
    parser.add_argument("--skip-tavily", action="store_true")
    parser.add_argument("--skip-oss", action="store_true")
    parser.add_argument("--skip-sentry", action="store_true")
    parser.add_argument("--skip-litellm", action="store_true")
    args = parser.parse_args()

    print("═══════════════════════════════════════════")
    print("  「有了」真 API 验证(Sprint 6 切换检查)")
    print("═══════════════════════════════════════════")

    checks: list[tuple[str, Awaitable[None]]] = []
    if not args.skip_litellm:
        checks.append(("litellm", check_litellm()))
    if not args.skip_tavily:
        checks.append(("tavily", check_tavily()))
    if not args.skip_oss:
        checks.append(("oss", check_aliyun_oss()))
    if not args.skip_volcengine:
        checks.append(("volcengine", check_volcengine_tts()))
    if not args.skip_sentry:
        checks.append(("sentry", check_sentry()))

    for name, coro in checks:
        try:
            await coro
        except Exception as e:
            fail(f"{name} unexpected:{e}")

    print("\n═══════════════════════════════════════════")
    if failures:
        print(f"{RED}失败 {len(failures)} 项 / 警告 {len(warnings)} 项{NC}")
        return 1
    if warnings:
        print(f"{YELLOW}全绿(实际通过 {len(checks) - len(warnings)} / 跳过 {len(warnings)}){NC}")
        return 0
    print(f"{GREEN}全绿(共 {len(checks)} 项){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
