#!/usr/bin/env python3
"""Sprint 6 acceptance:反诈视频 10 次 + 电商详情图 5 次,全绿才算上线达标。

用法:
    BASE_URL=https://staging.youle.example.com \
    JWT_TOKEN=eyJ... \
    python scripts/smoke-prod.py [--anti-fraud N] [--detail M]

每次任务:
  1. POST /api/conversations 创建 hero 群
  2. POST /api/messages 发起任务(skill_id 锁定)
  3. 轮询 /api/tasks/<id>(< timeout)直到 completed/failed
  4. HITL gate 自动 approve(走 Auto 模式 happy path)

输出:成功率 + 平均耗时 + p95 + 任意失败详情。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from typing import Any

import httpx


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
JWT = os.getenv("JWT_TOKEN", "")
TIMEOUT_S = int(os.getenv("SMOKE_TIMEOUT", "600"))


def auth_headers() -> dict[str, str]:
    if not JWT:
        return {}
    return {"Authorization": f"Bearer {JWT}"}


async def _create_conversation(client: httpx.AsyncClient, *, kind: str, title: str) -> str:
    r = await client.post(
        "/api/conversations",
        headers=auth_headers(),
        json={"kind": kind, "title": title, "work_mode": "auto"},
    )
    r.raise_for_status()
    return r.json()["id"]


async def _start_task(
    client: httpx.AsyncClient,
    *,
    conversation_id: str,
    skill_id: str,
    fields: dict[str, Any],
) -> str:
    r = await client.post(
        "/api/tasks/start",
        headers=auth_headers(),
        json={
            "conversation_id": conversation_id,
            "skill_id": skill_id,
            "collected_fields": fields,
        },
    )
    r.raise_for_status()
    return r.json()["task_id"]


async def _approve_pending_gates(
    client: httpx.AsyncClient, task_id: str
) -> int:
    """轮一遍未关闭的 HITL gate,全部 approve。"""
    r = await client.get(f"/api/tasks/{task_id}/hitl_gates", headers=auth_headers())
    if r.status_code != 200:
        return 0
    n = 0
    for gate in r.json():
        if gate.get("closed_at"):
            continue
        gid = gate["id"]
        await client.post(
            f"/api/tasks/{task_id}/hitl_gates/{gid}/resolve",
            headers=auth_headers(),
            json={"resolution": "approved"},
        )
        n += 1
    return n


async def _wait_done(
    client: httpx.AsyncClient, task_id: str, timeout_s: int
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = await client.get(f"/api/tasks/{task_id}", headers=auth_headers())
        if r.status_code == 200:
            data = r.json()
            if data["status"] in ("completed", "failed", "cancelled"):
                return data
            # 有 HITL gate 开着 → 自动 approve(smoke 跑 happy path)
            await _approve_pending_gates(client, task_id)
        await asyncio.sleep(2.0)
    return {"status": "timeout", "task_id": task_id}


async def run_one(
    client: httpx.AsyncClient,
    *,
    skill_id: str,
    fields: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        conv_id = await _create_conversation(client, kind="hero", title=label)
        task_id = await _start_task(
            client, conversation_id=conv_id, skill_id=skill_id, fields=fields
        )
        result = await _wait_done(client, task_id, TIMEOUT_S)
        result["_duration_s"] = time.monotonic() - t0
        result["_label"] = label
        return result
    except Exception as e:
        return {"status": "exception", "_error": str(e), "_label": label,
                "_duration_s": time.monotonic() - t0}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anti-fraud", type=int, default=10)
    parser.add_argument("--detail", type=int, default=5)
    args = parser.parse_args()

    if not JWT:
        print("⚠ JWT_TOKEN 未设;请先登录获取 token", file=sys.stderr)
        return 2

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # 反诈视频 N 次
        af_tasks = [
            run_one(
                client,
                skill_id="anti_fraud_video",
                fields={
                    "年份": 2026,
                    "骗局类型": "电信诈骗",
                    "受众": "60 岁以上长者",
                },
                label=f"反诈-{i+1}",
            )
            for i in range(args.anti_fraud)
        ]
        af_results = await asyncio.gather(*af_tasks)

        # 电商详情图 M 次
        ec_tasks = [
            run_one(
                client,
                skill_id="ecommerce_detail_image",
                fields={"品类": "保温杯", "风格": "极简白底"},
                label=f"详情图-{i+1}",
            )
            for i in range(args.detail)
        ]
        ec_results = await asyncio.gather(*ec_tasks)

    all_results = af_results + ec_results
    success = [r for r in all_results if r.get("status") == "completed"]
    failures = [r for r in all_results if r.get("status") not in ("completed",)]
    durations = [r["_duration_s"] for r in success]

    print("\n═══════════════════════════════════════════")
    print(f"  Smoke 结果({len(all_results)} 次)")
    print("═══════════════════════════════════════════")
    print(f"成功: {len(success)} / {len(all_results)}({len(success)/max(1,len(all_results)):.0%})")
    if durations:
        print(
            f"耗时(成功): mean={statistics.mean(durations):.1f}s  "
            f"p50={statistics.median(durations):.1f}s  "
            f"p95={statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else max(durations):.1f}s"
        )

    if failures:
        print("\n失败明细:")
        for r in failures:
            print(f"  [{r['_label']}] status={r.get('status')} err={r.get('_error') or r.get('error_detail', '')}")

    # acceptance:成功率 100%
    return 0 if len(success) == len(all_results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
