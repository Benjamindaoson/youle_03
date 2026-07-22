"""Celery 应用 — 长任务(视频合成等)异步执行。"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "haole",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
)

# Celery worker 启动时自动 import 任务
celery_app.autodiscover_tasks(["agents.av_agent.celery_tasks"], force=True)
