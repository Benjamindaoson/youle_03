"""Upload BGM files to OSS/MinIO and upsert bgm_library rows.

Examples:
  python scripts/seed-bgm-library.py --file ./assets/warning_60s.mp3 --mood warning --duration 60
  python scripts/seed-bgm-library.py --dir ./local_materials/music --mood auto
  python scripts/seed-bgm-library.py --csv infrastructure/seeds/bgm.csv

CSV columns:
  path,title,mood,duration,bpm,license
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(ROOT / ".env")
os.environ["DEBUG"] = "false"
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")

from app.db import SessionLocal, engine  # noqa: E402


def _s3_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("OSS_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("OSS_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("OSS_SECRET_KEY", "minioadmin"),
        region_name=os.getenv("OSS_REGION", "cn-hangzhou"),
        config=Config(signature_version="s3v4"),
    )


def _rows_from_args(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.dir:
        base = Path(args.dir).expanduser().resolve()
        if not base.exists():
            raise FileNotFoundError(base)
        audio_exts = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
        rows = []
        for path in sorted(p for p in base.iterdir() if p.suffix.lower() in audio_exts):
            rows.append(
                {
                    "path": str(path),
                    "title": path.stem,
                    "mood": _infer_mood(path.stem, args.mood),
                    "duration": args.duration,
                    "bpm": args.bpm,
                    "license": args.license,
                }
            )
        return rows

    if args.csv:
        csv_path = Path(args.csv)
        base = csv_path.parent
        rows: list[dict[str, Any]] = []
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for raw in csv.DictReader(fh):
                item = dict(raw)
                path = Path(item["path"])
                item["path"] = str(path if path.is_absolute() else base / path)
                rows.append(item)
        return rows

    if not args.file:
        raise SystemExit("missing --file, --dir or --csv")
    return [
        {
            "path": args.file,
            "title": args.title or Path(args.file).stem,
            "mood": args.mood,
            "duration": args.duration,
            "bpm": args.bpm,
            "license": args.license,
        }
    ]


def _infer_mood(name: str, default: str) -> str:
    if default and default != "auto":
        return default
    lowered = name.lower()
    if any(token in lowered for token in ("warning", "警示", "紧张", "悬疑", "危机")):
        return "warning"
    if any(token in lowered for token in ("激情", "燃", "快节奏", "energetic", "passion")):
        return "energetic"
    if any(token in lowered for token in ("惬意", "舒缓", "calm", "relax", "warm")):
        return "calm"
    return "neutral"


async def _upsert_row(row: dict[str, Any]) -> str:
    path = Path(str(row["path"])).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    mood = str(row.get("mood") or "warning")
    duration = int(row.get("duration") or 60)
    title = str(row.get("title") or path.stem)
    bpm = int(row["bpm"]) if row.get("bpm") not in (None, "") else None
    license_name = str(row.get("license") or "internal")

    bucket = os.getenv("OSS_BUCKET", "haole-dev")
    key = f"bgm/{mood}/{path.name}"
    content_type = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
    body = path.read_bytes()
    _s3_client().put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    oss_ref = f"oss://{bucket}/{key}"

    async with SessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO bgm_library (title, mood, duration, bpm, oss_ref, license, usage_count, is_active)
                VALUES (:title, :mood, :duration, :bpm, :oss_ref, :license, 0, TRUE)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "title": title,
                "mood": mood,
                "duration": duration,
                "bpm": bpm,
                "oss_ref": oss_ref,
                "license": license_name,
            },
        )
        await session.commit()
    return oss_ref


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="CSV file with path,title,mood,duration,bpm,license")
    parser.add_argument("--file", help="Single audio file to upload")
    parser.add_argument("--dir", help="Directory of local audio files to upload")
    parser.add_argument("--title")
    parser.add_argument("--mood", default="warning", help="BGM mood, or auto when used with --dir")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--bpm", type=int)
    parser.add_argument("--license", default="internal")
    args = parser.parse_args()

    refs = []
    for row in _rows_from_args(args):
        refs.append(await _upsert_row(row))
    await engine.dispose()
    for ref in refs:
        print(ref)


if __name__ == "__main__":
    asyncio.run(main())
