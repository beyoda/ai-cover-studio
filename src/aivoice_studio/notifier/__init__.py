"""AIVOICE outbox Notifier — independent of Worker / Skill / Pipeline."""

from aivoice_studio.notifier.feishu_client import (
    FeishuAuthError,
    FeishuClient,
    FeishuClientError,
    FeishuSendError,
    FeishuUploadError,
    MockFeishuClient,
    RealFeishuClient,
    build_feishu_client,
)
from aivoice_studio.notifier.outbox_consumer import OutboxConsumer, consume_once

__all__ = [
    "FeishuAuthError",
    "FeishuClient",
    "FeishuClientError",
    "FeishuSendError",
    "FeishuUploadError",
    "MockFeishuClient",
    "OutboxConsumer",
    "RealFeishuClient",
    "build_feishu_client",
    "consume_once",
]
