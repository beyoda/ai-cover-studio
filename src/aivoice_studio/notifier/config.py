"""Notifier Feishu config — env only, never written to jobs/outbox."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_BASE_URL = "https://open.feishu.cn"


@dataclass(frozen=True)
class FeishuConfig:
    app_id: str
    app_secret: str
    base_url: str = DEFAULT_BASE_URL
    receive_id_type: str = "chat_id"

    @property
    def ok(self) -> bool:
        return bool(self.app_id.strip() and self.app_secret.strip())


def load_feishu_config() -> FeishuConfig:
    return FeishuConfig(
        app_id=str(os.environ.get("FEISHU_APP_ID") or "").strip(),
        app_secret=str(os.environ.get("FEISHU_APP_SECRET") or "").strip(),
        base_url=str(os.environ.get("FEISHU_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        receive_id_type=str(os.environ.get("FEISHU_RECEIVE_ID_TYPE") or "chat_id").strip()
        or "chat_id",
    )


def resolve_feishu_mode(*, real_flag: bool = False) -> str:
    """Return ``mock`` (default) or ``real``.

    Precedence: ``--real`` flag > ``FEISHU_MODE`` env > mock.
    """
    if real_flag:
        return "real"
    mode = str(os.environ.get("FEISHU_MODE") or "mock").strip().lower()
    if mode in ("real", "live", "prod"):
        return "real"
    return "mock"
