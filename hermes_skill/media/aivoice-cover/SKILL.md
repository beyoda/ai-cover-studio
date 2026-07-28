---
name: aivoice-cover
description: "Use when the user wants a local AI vocal cover / 翻唱 / 换声, or asks which voices are available (有哪些声音). Resolve voice_id via Registry and music via MusicSource (local path, direct URL, or GD音乐台 search+pick); enqueue a FS job via aivoice_cover.py (status=queued). Always pass --session-id (Feishu oc_ chat or ou_ user id). Do not invent voice lists. Do not wait for completed or send mp3 in the same turn."
version: 1.3.0.4.2-ondemand
author: AIVOICE
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [aivoice, cover, svc, vocal, 翻唱, 换声, 示例歌手, example_voice, example_voice_b, 音色, 声音列表]
    category: media
    related_skills: []
    requires_toolsets: [terminal]
---

# AIVOICE Cover — Hermes Skill (v1.3 enqueue + on-demand)

## Overview

```text
Hermes / Skill 负责：
  --search / --pick / --list-voices / --json-file
  → session state（选歌确认）
  → MusicSource（准备本地音频）
  → FileJobQueue.enqueue_job → status=queued ACK → 本轮结束
  → 后台 kick：Worker --drain → Notifier（自动推 mp3）

Worker 负责（按需拉起，非本 Skill 同步等待）：
  UVR → SVC → Mix → Export → outputs/{job_id}/cover.mp3

完成通知：
  outbox + Notifier 用 feishu_chat_id（oc_…）投递文案与 mp3
  本轮 Skill 不发最终 mp3
```

Never hardcode checkpoints. Never call UVR/SVC CLIs. Never grep the repo for covers.  
**ExampleVoiceB 可用，禁止警告 768/256，禁止劝换 example_voice。**

Attribution: **GD音乐台 (music.gdstudio.xyz)**.

Python（务必 unset PYTHONPATH）：

```text
bash -lc "unset PYTHONPATH; exec <repo-root>/.venv/Scripts/python.exe <repo-root>/hermes_skill/media/aivoice-cover/scripts/aivoice_cover.py ..."
```

### Session / 投递目标（必读）

| 参数 | 用途 |
|---|---|
| `--session-id` | **必传**。用当前飞书会话的稳定 id：私聊常见 `ou_…`（用户 open_id）或 `oc_…`（chat_id） |
| `--feishu-chat-id` | 可选。有明确 `oc_…` 时可再传；不传时脚本会自动用 `--session-id`（若已是 `oc_`/`ou_`）写入 job |

Notifier 会按前缀发送：`oc_` → chat_id，`ou_` → open_id。  
**只要 Hermes 照常传 `--session-id`，用户不必也不应手填 chat_id。**

---

## Hard rules

1. **只跑本 Skill**。禁止搜代码 / 乱 find / 传播旧 MEMORY。
2. **只有歌名 → `--search`，禁止要路径/直链。** 禁止说「曲库不支持按歌名」。
3. **用户回数字 → `--pick N --session-id ...`**，不要靠 LLM 猜 track_id。
4. 把脚本输出的 `pretty` / `user_message` **原样发给用户**。
5. 同一时间只跑一单 cover（业务上）；真正串行由 Worker 保证。
6. 错误只转发 `user_message`，不要贴 Python traceback。
7. **翻唱 enqueue 成功后（`status=queued`），本轮立即结束。**
8. **禁止**再次调用 Skill「等待 completed」。
9. **禁止**为了获取 `output_path` 轮询 job / 循环跑脚本。
10. **禁止**假设当前 tool 调用可以发送最终 mp3。
11. **`queued` 是成功状态，不是失败。** 向用户说明已入队即可；成品稍后自动推送。
12. **每次调用都带同一 `--session-id`**（飞书 `ou_…` 或 `oc_…`），以便自动推送成品。

---

## Flow A — 搜歌选曲翻唱

用户：「用 example_voice_b 翻唱示例歌手的示例曲目」

```text
.../aivoice_cover.py --session-id <SID> --voice-id example_voice_b --search 示例歌手的示例曲目
```

exit 2 + `pretty` → **原样发出，停住等用户选序号**。

用户：「1」

```text
.../aivoice_cover.py --session-id <SID> --pick 1
```

脚本会：确认选择 → 准备音频 → **enqueue** → 返回 `status=queued` + `job_id` → 后台 kick Worker。  
把 `user_message` / `pretty` **原样发给用户**，然后 **结束本轮**。  
**不要**等待制作完成，**不要**本轮发送 `cover.mp3`。

可选 dry-run（只生成 request，不入队）：

```text
.../aivoice_cover.py --session-id <SID> --pick 1 --dry-run
```

---

## Flow B — 本地 / 直链

```json
{ "input": "示例歌手 - 示例曲目.mp3", "voice_id": "example_voice" }
```

```json
{ "source": "https://....mp3", "voice_id": "example_voice_b" }
```

```text
.../aivoice_cover.py --session-id <SID> --json-file request.json
```

成功同样是 `status=queued`；本轮结束，不发 mp3。

---

## Flow C — 有哪些声音

```text
.../aivoice_cover.py --list-voices
```

把 `pretty` 原样发出（来自 Voice Registry，禁止手写列表）。

---

## NL 解析（可选）

```text
.../aivoice_cover.py --session-id <SID> --parse "用example_voice_b翻唱示例歌手的示例曲目"
```

返回 `params.action=search|pick|cover` 等。pitch：「升两个key」→ 2。

---

## 用户可见文案（Skill 侧）

入队成功时，脚本会给出「已选择 / 已进入制作队列」类 ACK。  
**不要**伪造 Worker 执行阶段（人声分离 / 音色转换 / 混音导出）。  
那些阶段属于 Worker 日志，不是本轮 Hermes 话术。  
可告知用户：入队后会自动制作，完成后把成品推到本会话。

---

## Success JSON（入队成功）

```json
{
  "status": "queued",
  "job_id": "a55442027dba",
  "song": "示例曲目",
  "voice": "ExampleVoiceB",
  "pitch": 0,
  "output_path": null,
  "feishu_chat_id": "ou_or_oc_from_session",
  "error": null,
  "user_message": "已收到，翻唱已进入制作队列。完成后会通知你。"
}
```

说明：

- `status=queued` = **成功**
- `job_id` 是后续查询与通知的唯一标识
- `output_path` 在本轮为 `null`（成品由 Worker 写出，Notifier 再投递）
- `feishu_chat_id` 通常由 `--session-id` 自动填入（`ou_…` / `oc_…`）
