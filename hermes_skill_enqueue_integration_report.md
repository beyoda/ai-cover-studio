# AIVOICE v1.3-0.4.1-d — Hermes Skill Enqueue Integration Report

> 日期：2026-07-27  
> 阶段：Skill enqueue → Worker 全链路验收  
> 性质：**验证 only**（未改产品代码）  
> 前置：0.4.1-a/b/c-1 + Worker E2E Smoke PASS

---

## Environment

| 项 | 值 |
|---|---|
| audio | `<repo-root>\workdir\_gpu_smoke\clip30.mp3` |
| voice_id | `example_voice_b` |
| jobs_root | `<repo-root>\jobs` |
| Skill | `hermes_skill/media/aivoice-cover/scripts/aivoice_cover.py` |
| Worker | `python -m aivoice_studio.worker --once -v` |
| mock CoverService | **false** |

说明：验收前将历史残留 `queued/*.json` 临时移至 `jobs/_validation_parked/`，确保 `--once` 消费本次 Skill 入队单（非产品代码修改）。

---

## Skill enqueue

| 项 | 值 |
|---|---|
| job_id | `709cf4b8f094` |
| 耗时 | **0.25 s**（未阻塞等翻唱） |
| exit | 0 |
| status | `queued` |
| output_path | `null` |

stdout JSON：

```json
{
  "status": "queued",
  "job_id": "709cf4b8f094",
  "song": "clip30",
  "voice": "ExampleVoiceB",
  "pitch": 0,
  "output_path": null,
  "error": null,
  "user_message": "已收到，翻唱已进入制作队列。完成后会通知你。",
  "pretty": "已收到，翻唱已进入制作队列。完成后会通知你。"
}
```

queued 文件字段核对：

| 字段 | 值 |
|---|---|
| `input_audio` | `<repo-root>\workdir\_gpu_smoke\clip30.mp3` |
| `voice_id` | `example_voice_b` |
| `pitch` | `0` |
| `options` | reverb / f0_method=rmvpe / export_mp3=true |
| `hermes_session_id` | `integration-041d` |

失败路径检查（同次 Skill 输出）：

- **无** `status=completed`
- **无** 真实 `output_path`

---

## Worker execution

| 项 | 值 |
|---|---|
| worker_rc | **0** |
| wall time | **~13.8 s** |
| claim | `709cf4b8f094` |
| stages | uvr (cache hit) → svc → mixing → exporting → done |

---

## Final artifact

| 项 | 值 |
|---|---|
| completed | `jobs/completed/709cf4b8f094.json` |
| status | `completed` |
| output_path | `<repo-root>\outputs\709cf4b8f094\cover.mp3` |
| mp3 exists | yes |
| parent == job_id | **yes** (`709cf4b8f094`) |
| size | **1003146** bytes（> 50KB） |
| queued/running 残留 | 无该 job_id |

---

## Result

**PASS**

---

## Final confirmation

1. **Skill enqueue 可以被 Worker 正常消费。**  
2. **Hermes 已切换到异步执行链**（Skill 秒回 `queued`；Worker 独自跑 UVR/SVC）。  
3. **下一阶段才允许设计 / 实现 outbox**（飞书完成通知）。  

未改：`aivoice_cover.py` / Worker / Pipeline / UVR / SVC / CoverService / FileJobQueue。
