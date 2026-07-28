"""RealFeishuClient unit tests — mocked HTTP only (no real Feishu)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aivoice_studio.notifier.config import FeishuConfig, resolve_feishu_mode
from aivoice_studio.notifier.feishu_client import (
    FeishuAuthError,
    FeishuSendError,
    FeishuUploadError,
    RealFeishuClient,
    build_feishu_client,
)


def _cfg(**kwargs) -> FeishuConfig:
    base = {
        "app_id": "cli_test",
        "app_secret": "secret_test",
        "base_url": "https://open.feishu.cn",
        "receive_id_type": "chat_id",
    }
    base.update(kwargs)
    return FeishuConfig(**base)


def _json_resp(payload: dict, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r


def test_missing_credentials_raises():
    with pytest.raises(FeishuAuthError) as ei:
        RealFeishuClient(config=_cfg(app_id="", app_secret=""))
    assert "missing_feishu_credentials" in str(ei.value)


def test_build_real_without_env_fails(monkeypatch):
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    with pytest.raises(FeishuAuthError) as ei:
        build_feishu_client(mode="real")
    assert "missing_feishu_credentials" in str(ei.value)


def test_resolve_mode_default_mock(monkeypatch):
    monkeypatch.delenv("FEISHU_MODE", raising=False)
    assert resolve_feishu_mode() == "mock"
    assert resolve_feishu_mode(real_flag=True) == "real"
    monkeypatch.setenv("FEISHU_MODE", "real")
    assert resolve_feishu_mode() == "real"


def test_token_success_and_cache():
    session = MagicMock()
    session.post.side_effect = [
        _json_resp({"code": 0, "tenant_access_token": "t-abc", "expire": 7200}),
        _json_resp({"code": 0, "data": {"message_id": "m1"}}),
    ]
    client = RealFeishuClient(config=_cfg(), session=session)
    client.send_message("oc_chat", "hello")
    # token + send
    assert session.post.call_count == 2
    token_call = session.post.call_args_list[0]
    assert "tenant_access_token" in token_call.args[0]
    assert token_call.kwargs["json"]["app_id"] == "cli_test"
    # second send should reuse cached token (only one more post)
    session.post.side_effect = [_json_resp({"code": 0, "data": {"message_id": "m2"}})]
    client.send_message("oc_chat", "again")
    assert session.post.call_count == 3


def test_token_failure():
    session = MagicMock()
    session.post.return_value = _json_resp(
        {"code": 10014, "msg": "app secret invalid"}, status=200
    )
    client = RealFeishuClient(config=_cfg(), session=session)
    with pytest.raises(FeishuAuthError) as ei:
        client.send_message("oc_chat", "x")
    assert "token_failed" in str(ei.value)


def test_send_message_params():
    session = MagicMock()
    session.post.side_effect = [
        _json_resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200}),
        _json_resp({"code": 0, "data": {}}),
    ]
    client = RealFeishuClient(config=_cfg(), session=session)
    client.send_message("oc_xyz", "翻唱完成")
    send_call = session.post.call_args_list[1]
    assert send_call.args[0].endswith("/open-apis/im/v1/messages")
    assert send_call.kwargs["params"]["receive_id_type"] == "chat_id"
    body = send_call.kwargs["json"]
    assert body["receive_id"] == "oc_xyz"
    assert body["msg_type"] == "text"
    assert json.loads(body["content"])["text"] == "翻唱完成"
    assert "Bearer t-1" in send_call.kwargs["headers"]["Authorization"]


def test_send_message_open_id_params():
    session = MagicMock()
    session.post.side_effect = [
        _json_resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200}),
        _json_resp({"code": 0, "data": {}}),
    ]
    client = RealFeishuClient(config=_cfg(), session=session)
    client.send_message("ou_user123", "hi")
    send_call = session.post.call_args_list[1]
    assert send_call.kwargs["params"]["receive_id_type"] == "open_id"
    assert send_call.kwargs["json"]["receive_id"] == "ou_user123"


def test_send_message_api_error():
    session = MagicMock()
    session.post.side_effect = [
        _json_resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200}),
        _json_resp({"code": 230002, "msg": "chat not found"}),
    ]
    client = RealFeishuClient(config=_cfg(), session=session)
    with pytest.raises(FeishuSendError):
        client.send_message("bad", "x")


def test_upload_file_params(tmp_path: Path):
    mp3 = tmp_path / "cover.mp3"
    mp3.write_bytes(b"ID3data")
    session = MagicMock()
    session.post.side_effect = [
        _json_resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200}),
        _json_resp({"code": 0, "data": {"file_key": "file_abc"}}),
        _json_resp({"code": 0, "data": {"message_id": "mf"}}),
    ]
    client = RealFeishuClient(config=_cfg(), session=session)
    client.upload_file("oc_chat", mp3)
    # token + upload + file message
    assert session.post.call_count == 3
    upload_call = session.post.call_args_list[1]
    assert upload_call.args[0].endswith("/open-apis/im/v1/files")
    assert upload_call.kwargs["data"]["file_type"] == "stream"
    assert "file" in upload_call.kwargs["files"]
    file_msg = session.post.call_args_list[2]
    body = file_msg.kwargs["json"]
    assert body["msg_type"] == "file"
    assert json.loads(body["content"])["file_key"] == "file_abc"
    assert body["receive_id"] == "oc_chat"


def test_upload_missing_file(tmp_path: Path):
    session = MagicMock()
    session.post.return_value = _json_resp(
        {"code": 0, "tenant_access_token": "t-1", "expire": 7200}
    )
    client = RealFeishuClient(config=_cfg(), session=session)
    with pytest.raises(FeishuUploadError) as ei:
        client.upload_file("oc_chat", tmp_path / "nope.mp3")
    assert "missing_file" in str(ei.value)
