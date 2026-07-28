# Chat ID + On-demand Worker — Verification Report

> Date: 2026-07-28  
> Scope: `feishu_chat_id` wiring + Worker `--drain` + `kick_cover_pipeline`  
> Sample job: **`dbc73be29b29`**

## Verdict: **PASS** (local pipeline) / real Feishu send **blocked by chat membership**

Automatic enqueue → on-demand Worker → outbox with `oc_…` chat_id → mock Notifier **works**.  
Real Feishu API was reached; send failed because the test chat_id was not a chat the **old** bot belongs to (V2-era `oc_ddc760…`).

---

## What shipped

| Item | Status |
|---|---|
| `--feishu-chat-id` + `resolve_feishu_chat_id` (`oc_` only fallback) | ✅ |
| SKILL.md requires `oc_…` on search/pick/cover | ✅ |
| Worker `--drain` (empty queue exits) | ✅ |
| `scripts/kick_cover_pipeline.py` + `.ps1` | ✅ |
| Skill enqueue fire-and-forget kick | ✅ |
| Kick skips when `worker.lock` held | ✅ (fixed Windows unreadable-lock case) |

---

## Acceptance evidence

### A — chat_id

- `resolve_feishu_chat_id(session_id='ou_…')` → `None`
- `resolve_feishu_chat_id(session_id='oc_…')` → that id
- Job `dbc73be29b29`: `feishu_chat_id=oc_ddc76021b6e61a6e2fef964f0c58fea0`, `notify_status=pending` at enqueue
- Outbox `jobs/outbox/dbc73be29b29.notify.json` carried the same chat_id

### B — on-demand Worker

- Skill stderr: `kick_started script=kick_cover_pipeline.py`
- Job claimed/executed under drain (~30s, UVR cache hit) → `completed`
- Output: `<repo-root>\outputs\dbc73be29b29\cover.mp3`
- Concurrent kick while lock held: `kick=skip reason=worker_lock_held` (exit 0)

### Notifier

| Mode | Result |
|---|---|
| mock `--once` | **sent** (text + file recorded) |
| real `--once` | Feishu API responded: `Bot/User can NOT be out of the chat.` (credentials OK; wrong/stale chat for current bot) |

Kick loads `FEISHU_APP_ID` / `FEISHU_APP_SECRET` from `%LOCALAPPDATA%\hermes\.env` when unset.

---

## How to use (ops)

1. Keep Hermes Gateway running (`hermes gateway run`) with **old** bot credentials.  
2. Do **not** leave a resident Worker running.  
3. Hermes Skill must pass **`--feishu-chat-id <current oc_…>`** (from the Feishu inbound chat, not `ou_…`).  
4. After enqueue, Skill kicks `scripts/kick_cover_pipeline.py` → `worker --drain` → `notifier --once --real`.

---

## Follow-ups (not this slice)

- End-to-end real mp3 in Feishu DM: re-test with the **old bot’s** live private `oc_…` (from `gateway.log` inbound).  
- Optional: park/clear leftover failed outbox retries for `dbc73be29b29`.  
- Gateway still manual start (no Windows auto-start in this slice).
