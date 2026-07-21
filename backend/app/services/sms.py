"""Aliyun SMS delivery adapter used only outside development mode."""

from __future__ import annotations

import asyncio
import json

from app.config import settings
from app.exceptions import SmsError


async def send_sms_code(phone: str, code: str) -> None:
    required = (
        settings.ALIYUN_ACCESS_KEY,
        settings.ALIYUN_SECRET_KEY,
        settings.ALIYUN_SMS_SIGN_NAME,
        settings.ALIYUN_SMS_TEMPLATE_CODE,
    )
    if not all(required):
        raise SmsError("短信服务未配置")

    def _send() -> None:
        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_dysmsapi20170525.models import SendSmsRequest
        from alibabacloud_tea_openapi.models import Config

        client = Client(
            Config(
                access_key_id=settings.ALIYUN_ACCESS_KEY,
                access_key_secret=settings.ALIYUN_SECRET_KEY,
                endpoint="dysmsapi.aliyuncs.com",
            )
        )
        response = client.send_sms(
            SendSmsRequest(
                phone_numbers=phone,
                sign_name=settings.ALIYUN_SMS_SIGN_NAME,
                template_code=settings.ALIYUN_SMS_TEMPLATE_CODE,
                template_param=json.dumps({"code": code}),
            )
        )
        if response.body is None or response.body.code != "OK":
            raise SmsError("短信发送失败")

    try:
        await asyncio.to_thread(_send)
    except SmsError:
        raise
    except Exception as exc:
        raise SmsError("短信发送失败") from exc
