# Hermes Messaging Gateway E2E Report

> Phase: **AIVOICE v1.2-2**  
> Date: 2026-07-26  
> Scope: 手机飞书 → Hermes Gateway → Agent → aivoice-cover Skill → CoverService → 回传结果/音频  
> 禁止项遵守：未改 Pipeline / PipelineAdapter 核心 / GUI / Voice Registry / MusicSource 核心 / SVC·UVR 推理逻辑

---

## 总评

**PASS（真实闭环）**

飞书私聊可收发；Skill 调用 CoverService 完成翻唱；文本摘要 + `cover.mp3` 已回到飞书。

---

## 1. 平台选择

| 项 | 结论 |
|----|------|
| 推荐 | **Feishu（国内）+ WebSocket** |
| 设计文档 | `hermes_messaging_design.md` |
| 未选 Telegram | 国内可达性差 |
| 联调备选 | 本机 Webhook（未作为主路径） |

---

## 2. 配置过程

| 步骤 | 结果 |
|------|------|
| `hermes gateway setup` 扫码 | 失败，改手动 App ID/Secret |
| Domain / 连接 | `feishu` + `websocket` |
| 事件 | 长连接 + `im.message.receive_v1` |
| 权限 | 初缺 **`im:message.p2p_msg:readonly`**（仅有群 @）→ 补开并发布后私聊才通 |
| 白名单 | `GATEWAY_ALLOW_ALL_USERS=true` / `FEISHU_ALLOW_ALL_USERS=true`（联调） |
| 本机代理 | Clash `127.0.0.1:7890` 导致 `open.feishu.cn` SSL EOF → `.env` 增加 `NO_PROXY` 绕过飞书域名 |
| Gateway | `hermes gateway run` 保持运行 |

---

## 3. 消息链路

```text
飞书手机/桌面私聊
  → Feishu WebSocket
  → Hermes Gateway
  → Hermes Agent
  → aivoice-cover Skill (aivoice_cover.py)
  → CoverService.submit / status / result
  → 文本回复 + 文件 cover.mp3
```

验证话术：「你好」有回复；「使用示例歌手声音翻唱示例歌手-示例曲目.mp3」触发 Skill。

---

## 4. Skill 调用

| 项 | 值 |
|----|-----|
| 输入 | `示例歌手 - 示例曲目.mp3`（`test_songs/`） |
| `voice_id` | `example_voice` / 示例歌手 |
| 主 Job | `3ec5c8db314d` |
| 耗时 | **54s** |
| 输出 | `<repo-root>\outputs\3ec5c8db314d\cover.mp3` |

中间曾因 Hermes 终端 `PYTHONPATH` 泄漏进 SVC `workenv` 失败；已在 `aivoice_studio.utils.process.scrubbed_subprocess_env` 隔离子进程环境后恢复。

---

## 5. 文件返回

飞书侧收到：

```text
歌曲：示例曲目
音色：示例歌手
状态：completed
时长：54s
输出：<repo-root>\outputs\3ec5c8db314d\cover.mp3
```

并附带 **cover.mp3（约 8.3 MB）**。

说明：同请求曾重复提交产生第二份 Job `d1d1e2aa7b72`（60s）；**以 `3ec5c8db314d` 为有效成品**。

---

## 6. 问题与处理

| 问题 | 处理 |
|------|------|
| 扫码建应用失败 | 手动凭证 |
| 私聊无事件 | 开通 `im:message.p2p_msg:readonly` 并重新发布 |
| 连上但不回复 / 发消息 SSL 失败 | 本地代理 7890 → `NO_PROXY` |
| SVC `typing_extensions` 冲突 | `process.py` scrub `PYTHONPATH` 等 |
| Agent 盲搜调用链 | 用户打断，令其直接跑 Skill |
| 重复提交双 Job | 保留主输出 `3ec5c8db314d` |

---

## 7. 未做

- Telegram  
- Worker / GPU / 缓存优化 / 多用户系统  
- 正式收紧 allowlist（联调仍为 allow-all）

---

## 结论

**Hermes Messaging Gateway 可作为 AIVOICE 移动入口原型：飞书 ↔ Skill ↔ CoverService 真实可用。**
