"""Feishu (Lark) bot handler — receive audio, return covers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request

from aivoice_studio.core.context import JobContext
from aivoice_studio.factory import build_pipeline
from aivoice_studio.ui.model_config_map import ModelConfigMap
from aivoice_studio.utils.config import ConfigLoader
from aivoice_studio.utils.paths import project_root, resolve_path

feishu = Blueprint("feishu", __name__)

# ── config (set via env vars) ────────────────────────────
APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
VERIFY_TOKEN = os.environ.get("FEISHU_VERIFY_TOKEN", "")

cfg = ConfigLoader().load()
svc_cfg = cfg.get("svc", {})
MODEL_MAP = ModelConfigMap(svc_cfg.get("models_dir", "models"))

UPLOAD_DIR = project_root() / "feishu_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# user session state
_sessions: dict[str, dict] = {}


def _get_tenant_token() -> str:
    """Get Feishu tenant access token."""
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=10,
    )
    return resp.json().get("tenant_access_token", "")


def _download_file(message_id: str, file_key: str, token: str) -> bytes:
    """Download a file from Feishu."""
    resp = requests.get(
        f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}",
        params={"type": "file"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


def _reply_text(token: str, msg_id: str, text: str) -> None:
    """Send a text reply."""
    requests.post(
        f"https://open.feishu.cn/open-apis/im/v1/messages/{msg_id}/reply",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": json.dumps({"text": text}), "msg_type": "text"},
        timeout=10,
    )


def _reply_file(token: str, msg_id: str, file_path: str, file_name: str) -> None:
    """Upload and send a file reply."""
    # upload
    with open(file_path, "rb") as f:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/files",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (file_name, f, "audio/mpeg")},
            data={"file_type": "mp3", "file_name": file_name},
            timeout=30,
        )
    file_key = resp.json().get("data", {}).get("file_key", "")
    if not file_key:
        _reply_text(token, msg_id, "文件上传失败，请重试")
        return

    # send
    content = json.dumps({"file_key": file_key})
    requests.post(
        f"https://open.feishu.cn/open-apis/im/v1/messages/{msg_id}/reply",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": content, "msg_type": "file"},
        timeout=10,
    )


def _process_cover(audio_path: Path, model: str, pitch: int, reverb: str) -> tuple[bool, str, str]:
    """Run pipeline. Returns (ok, mp3_path_or_error, output_dir)."""
    try:
        pipeline, config = build_pipeline()
        rt = config.get("runtime", {})
        result = pipeline.run(JobContext(
            input_audio=audio_path,
            model_name=model,
            pitch=pitch,
            f0_method="rmvpe",
            workdir=resolve_path(rt.get("workdir", "workdir")),
            output_dir=resolve_path(rt.get("output_dir", "outputs")),
            export_mp3=True,
            reverb=reverb,
        ))
        if result.success:
            out_dir = str(Path(result.mp3_path).parent) if result.mp3_path else ""
            return True, str(result.mp3_path), out_dir
        return False, result.error or "未知错误", ""
    except Exception as e:
        return False, str(e), ""


# ── routes ─────────────────────────────────────────────────

@feishu.route("/feishu/callback", methods=["POST"])
def callback():
    """Receive Feishu event callbacks."""
    body = request.get_json(force=True, silent=True) or {}

    # URL verification — raw JSON with proper escaping
    if body.get("type") == "url_verification":
        token = body.get("token", "")
        challenge = body.get("challenge", "")
        if VERIFY_TOKEN and token != VERIFY_TOKEN:
            return '{"error":"invalid token"}', 403, {"Content-Type": "application/json"}
        import json as _json
        import flask
        resp = flask.make_response(_json.dumps({"challenge": challenge}))
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
        return resp

    # event
    event = body.get("event", {})
    msg_type = event.get("message_type", "")
    msg_id = event.get("message_id", "")
    sender_id = event.get("sender", {}).get("sender_id", "unknown")
    text = event.get("text", "")

    # user session
    session = _sessions.setdefault(sender_id, {
        "model": "G_16000", "pitch": 0, "reverb": "关闭",
    })

    token = _get_tenant_token()
    if not token:
        return jsonify({}), 500

    # ── text commands ──
    if msg_type == "text":
        content = json.loads(text).get("text", "") if text else ""

        if content.startswith("/模型"):
            parts = content.split()
            if len(parts) > 1:
                session["model"] = parts[1]
                _reply_text(token, msg_id, f"✓ 已切换到模型: {parts[1]}")
            else:
                models = MODEL_MAP.list_models()
                _reply_text(token, msg_id, f"可用模型: {', '.join(models)}")

        elif content.startswith("/音高"):
            parts = content.split()
            if len(parts) > 1:
                try:
                    v = int(parts[1])
                    session["pitch"] = max(-12, min(12, v))
                    _reply_text(token, msg_id, f"✓ 音高设为: {session['pitch']:+d}")
                except ValueError:
                    _reply_text(token, msg_id, "格式: /音高 +2")

        elif content.startswith("/混响"):
            parts = content.split(" ", 1)
            if len(parts) > 1:
                session["reverb"] = parts[1]
                _reply_text(token, msg_id, f"✓ 混响设为: {parts[1]}")
            else:
                _reply_text(token, msg_id, "可选: 关闭 / 录音棚 / 现场 / 大教堂")

        elif content == "/状态":
            s = session
            _reply_text(
                token, msg_id,
                f"当前设置\n模型: {s['model']}\n音高: {s['pitch']:+d}\n混响: {s['reverb']}",
            )

        elif content == "/帮助":
            _reply_text(
                token, msg_id,
                "发送音频文件即可翻唱\n"
                "/模型 G_16000 — 切换模型\n"
                "/音高 +2 — 调整音高(-12~+12)\n"
                "/混响 录音棚 — 设置混响\n"
                "/状态 — 查看当前设置\n"
                "/帮助 — 显示此消息",
            )
        else:
            _reply_text(token, msg_id, "发送音频文件即可翻唱。输入 /帮助 查看更多指令")

    # ── file upload ──
    elif msg_type == "file":
        file_key = event.get("file_key", "")
        file_name = event.get("file_name", "audio.mp3")

        if not file_key:
            _reply_text(token, msg_id, "无法获取文件，请重试")
            return jsonify({}), 200

        _reply_text(token, msg_id, f"收到 {file_name}，开始翻唱…\n模型: {session['model']}\n音高: {session['pitch']:+d}")

        try:
            data = _download_file(msg_id, file_key, token)
        except Exception:
            _reply_text(token, msg_id, "文件下载失败，请重试")
            return jsonify({}), 200

        local_path = UPLOAD_DIR / file_name
        local_path.write_bytes(data)

        ok, result, out_dir = _process_cover(
            local_path, session["model"], session["pitch"], session["reverb"]
        )

        if ok and result:
            cover_name = Path(file_name).stem + "_cover.mp3"
            _reply_file(token, msg_id, result, cover_name)
        else:
            _reply_text(token, msg_id, f"翻唱失败: {result}")

        # cleanup
        try:
            local_path.unlink()
        except OSError:
            pass

    return jsonify({}), 200
