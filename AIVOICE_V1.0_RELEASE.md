# AIVOICE v1.0 Stable — 冻结说明

> 版本：**v1.0.0 Stable**  
> 冻结日：2026-07-28  
> 包名：`aivoice-studio`  
> 状态：**正式可用，停止功能膨胀**

---

## 1. 定位

**AIVOICE** 是 Windows 本地个人 AI 音频服务：用自然语言（飞书）点歌换声，异步制作并回传成品。

不是「跑通一次模型脚本」，而是：

```text
用户请求 → 任务系统 → 异步执行 → 状态管理 → 通知闭环
```

---

## 2. 冻结架构

```text
飞书
  → Hermes Gateway（常驻）
  → aivoice-cover Skill
  → MusicSource / Voice Registry
  → FileJobQueue（enqueue）
  → kick → Worker --drain
  → CoverService.run → UVR → SVC → Mix → Export
  → jobs/outbox → Notifier（--real）
  → 飞书文案 + cover.mp3
```

| 层 | 路径 | 冻结约定 |
|---|---|---|
| Skill | `hermes_skill/media/aivoice-cover/` | 入队即结束；不本轮发 mp3 |
| Queue / Worker | `src/aivoice_studio/worker/` | 单 Worker + `worker.lock` |
| Cover 执行 | `cover/service` → Pipeline | **不改** UVR/SVC/Pipeline 主链除非修 bug |
| Notifier | `src/aivoice_studio/notifier/` | 独立进程；Worker 不嵌飞书 SDK |
| GUI | `ui/main_window.py` | 并行保留，非飞书主路径 |

详情见 [CHANGELOG.md](CHANGELOG.md)。

---

## 3. v1.0 已完成能力（清单）

- [x] 飞书自然语言入口（Hermes）
- [x] 搜歌 / 选曲 / track 缓存（MusicSource）
- [x] Voice Registry（ExampleVoiceB / example_voice 等）
- [x] UVR + SVC + 导出 MP3
- [x] Job Queue + Worker（含按需 drain）
- [x] Outbox + Notifier + 真飞书推送
- [x] 升降调、混响开关（NL）
- [x] 完成通知含时间与耗时
- [x] Mock / E2E / 幂等基础

---

## 4. 运维（冻结态日常用法）

1. 本机启动：`hermes gateway run`（旧机器人凭证）
2. **不要**常驻 Worker；入队后 Skill 会 kick
3. 飞书私聊示例：`用 example_voice_b 翻唱古巨基的花洒` → 回序号 → 等成品
4. 成品目录：`outputs/{job_id}/cover.mp3`

---

## 5. 备份清单（封版必做）

**要备份（建议整目录 zip / 另盘拷贝）：**

| 项 | 路径 | 说明 |
|---|---|---|
| 源码与 Skill | `<repo-root>\`（可排除 `cache/`、`outputs/`、大 `workdir/`） | 代码真相 |
| 虚拟环境 | `.venv\` | 或记录 `pip freeze` 以便重建 |
| 音色配置 | `config/voices.json`、`config/uvr.yaml`、`config/svc.yaml` | |
| 模型权重 | `models\`、`tools\so-vits-svc\`（按你本机实际布局） | 体积大，单独盘 |
| Hermes 技能挂载 | Hermes 配置里 `external_dirs` → 本仓 `hermes_skill` | |
| 成功样例 | 任选 `outputs/*/cover.mp3` + 对应 `jobs/completed/*.json` | 回归对照 |

**单独加密保管（勿提交 Git）：**

| 项 | 路径 |
|---|---|
| Hermes / 飞书密钥 | `%LOCALAPPDATA%\hermes\.env`（`FEISHU_APP_ID` / `SECRET`） |
| 其他本地密钥 | 任何自建 `.env` |

**可不进备份或可清：**

- `cache\uvr\`、`jobs\running\` 临时锁、`__pycache__`、`.pytest_cache`

**建议动作：**

1. 复制 `CHANGELOG.md` + 本文件到备份包根目录  
2. 对 `%LOCALAPPDATA%\hermes\.env` 做加密副本（不进网盘明文）  
3. `git tag v1.0.0`（若你希望用 Git 钉住；需你明确要求再执行）

---

## 6. 明确不做（v1.0 冻结期）

- 不加更多模型 / 平台 / Web UI / 多人合唱
- 不把 Notifier 嵌进 Worker
- 不恢复 Skill 同步长轮询发 mp3
- 大改 Pipeline / UVR / SVC 仅限严重 bug

下一体验向迭代：**v1.1**（默认音色/少确认/更自然回复）。  
质量向：**v1.2**。  
Athena / 多角色：**另开主线**，复用本仓的 Agent + Queue + Worker + Notify 模板。

---

## 7. 阶段评价

**AIVOICE v1.0：完成并冻结。**

这是第一个可长期运行的个人 AI 服务化样板；后续主线建议回到 **Project Athena**。
