"""Feishu client abstraction — Mock + Real (Open API).

Consumer only sees ``send_message`` / ``upload_file``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import requests

from aivoice_studio.notifier.config import FeishuConfig, load_feishu_config

LOG = logging.getLogger("aivoice.notifier.feishu")


def resolve_receive_id_type(receive_id: str, *, default: str = "chat_id") -> str:
    """Map Feishu id prefix to Open API ``receive_id_type``."""
    rid = str(receive_id or "").strip()
    if rid.startswith("oc_"):
        return "chat_id"
    if rid.startswith("ou_"):
        return "open_id"
    return default or "chat_id"


class FeishuClientError(RuntimeError):
    """Base Feishu client error (safe message, no secrets)."""


class FeishuAuthError(FeishuClientError):
    """Token / credentials failure."""


class FeishuSendError(FeishuClientError):
    """Text message send failure."""


class FeishuUploadError(FeishuClientError):
    """File upload or file-message send failure."""


class FeishuClient(Protocol):
    def send_message(self, chat_id: str, text: str) -> None: ...

    def upload_file(self, chat_id: str, file_path: str | Path) -> None: ...


@dataclass
class MockSendRecord:
    chat_id: str
    text: str | None = None
    file_path: str | None = None
    kind: str = "message"  # message | file


@dataclass
class MockFeishuClient:
    """Records calls; never touches the network."""

    calls: list[MockSendRecord] = field(default_factory=list)

    def send_message(self, chat_id: str, text: str) -> None:
        self.calls.append(MockSendRecord(chat_id=chat_id, text=text, kind="message"))

    def upload_file(self, chat_id: str, file_path: str | Path) -> None:
        path = str(file_path)
        self.calls.append(MockSendRecord(chat_id=chat_id, file_path=path, kind="file"))

    @property
    def message_called(self) -> bool:
        return any(c.kind == "message" for c in self.calls)

    @property
    def upload_called(self) -> bool:
        return any(c.kind == "file" for c in self.calls)

    def reset(self) -> None:
        self.calls.clear()

    def as_dict(self) -> dict[str, Any]:
        return {
            "message_called": self.message_called,
            "upload_called": self.upload_called,
            "calls": [
                {
                    "kind": c.kind,
                    "chat_id": c.chat_id,
                    "text": c.text,
                    "file_path": c.file_path,
                }
                for c in self.calls
            ],
        }


@dataclass
class RealFeishuClient:
    """Open API client: tenant token + text + file message.

    Credentials from :class:`FeishuConfig` / env only. Token cached in-memory.
    """

    config: FeishuConfig
    session: Any = field(default_factory=requests.Session)
    _token: str | None = field(default=None, init=False, repr=False)
    _token_expire_at: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.config.ok:
            raise FeishuAuthError("missing_feishu_credentials")

    @classmethod
    def from_env(cls) -> RealFeishuClient:
        return cls(config=load_feishu_config())

    def _api(self, path: str) -> str:
        return f"{self.config.base_url}{path}"

    def _get_tenant_token(self, *, force: bool = False) -> str:
        now = time.time()
        if (
            not force
            and self._token
            and now < self._token_expire_at - 60
        ):
            return self._token

        try:
            resp = self.session.post(
                self._api("/open-apis/auth/v3/tenant_access_token/internal"),
                json={
                    "app_id": self.config.app_id,
                    "app_secret": self.config.app_secret,
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            raise FeishuAuthError(f"token_request_failed: {exc}") from exc

        try:
            body = resp.json()
        except Exception as exc:
            raise FeishuAuthError(f"token_invalid_json: http={resp.status_code}") from exc

        code = body.get("code", 0)
        token = body.get("tenant_access_token") or ""
        if resp.status_code >= 400 or code not in (0, None) or not token:
            msg = body.get("msg") or body.get("error") or f"http={resp.status_code}"
            raise FeishuAuthError(f"token_failed: {msg}")

        expire = int(body.get("expire") or 7200)
        self._token = str(token)
        self._token_expire_at = now + max(60, expire)
        return self._token

    def _auth_headers(self) -> dict[str, str]:
        token = self._get_tenant_token()
        return {"Authorization": f"Bearer {token}"}

    def send_message(self, chat_id: str, text: str) -> None:
        if not str(chat_id or "").strip():
            raise FeishuSendError("empty_chat_id")
        receive_id = str(chat_id).strip()
        id_type = resolve_receive_id_type(
            receive_id, default=self.config.receive_id_type
        )
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": str(text)}, ensure_ascii=False),
        }
        try:
            resp = self.session.post(
                self._api("/open-apis/im/v1/messages"),
                params={"receive_id_type": id_type},
                headers={**self._auth_headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise FeishuSendError(f"send_request_failed: {exc}") from exc

        if resp.status_code == 401:
            self._token = None
            try:
                resp = self.session.post(
                    self._api("/open-apis/im/v1/messages"),
                    params={"receive_id_type": id_type},
                    headers={**self._auth_headers(), "Content-Type": "application/json"},
                    json=payload,
                    timeout=20,
                )
            except requests.RequestException as exc:
                raise FeishuSendError(f"send_request_failed: {exc}") from exc

        try:
            body = resp.json()
        except Exception as exc:
            raise FeishuSendError(f"send_invalid_json: http={resp.status_code}") from exc

        code = body.get("code", -1)
        if resp.status_code >= 400 or code != 0:
            raise FeishuSendError(f"send_failed: {body.get('msg') or body}")

    def upload_file(self, chat_id: str, file_path: str | Path) -> None:
        if not str(chat_id or "").strip():
            raise FeishuUploadError("empty_chat_id")
        path = Path(file_path)
        if not path.is_file():
            raise FeishuUploadError(f"missing_file: {path}")

        file_key = self._upload_get_file_key(path)
        self._send_file_message(str(chat_id).strip(), file_key)

    def _upload_get_file_key(self, path: Path) -> str:
        # Feishu im/v1/files: mp3 is not a valid file_type enum — use stream.
        try:
            with path.open("rb") as fh:
                resp = self.session.post(
                    self._api("/open-apis/im/v1/files"),
                    headers=self._auth_headers(),
                    files={"file": (path.name, fh, "application/octet-stream")},
                    data={"file_type": "stream", "file_name": path.name},
                    timeout=60,
                )
        except requests.RequestException as exc:
            raise FeishuUploadError(f"upload_request_failed: {exc}") from exc

        try:
            body = resp.json()
        except Exception as exc:
            raise FeishuUploadError(f"upload_invalid_json: http={resp.status_code}") from exc

        code = body.get("code", -1)
        file_key = (body.get("data") or {}).get("file_key") or ""
        if resp.status_code >= 400 or code != 0 or not file_key:
            raise FeishuUploadError(f"upload_failed: {body.get('msg') or body}")
        return str(file_key)

    def _send_file_message(self, chat_id: str, file_key: str) -> None:
        id_type = resolve_receive_id_type(
            chat_id, default=self.config.receive_id_type
        )
        payload = {
            "receive_id": chat_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
        }
        try:
            resp = self.session.post(
                self._api("/open-apis/im/v1/messages"),
                params={"receive_id_type": id_type},
                headers={**self._auth_headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise FeishuUploadError(f"file_message_request_failed: {exc}") from exc

        try:
            body = resp.json()
        except Exception as exc:
            raise FeishuUploadError(
                f"file_message_invalid_json: http={resp.status_code}"
            ) from exc

        code = body.get("code", -1)
        if resp.status_code >= 400 or code != 0:
            raise FeishuUploadError(f"file_message_failed: {body.get('msg') or body}")


def build_feishu_client(*, mode: str = "mock") -> FeishuClient:
    """Factory: ``mock`` (default) or ``real``."""
    if str(mode).lower() in ("real", "live", "prod"):
        return RealFeishuClient.from_env()
    return MockFeishuClient()
