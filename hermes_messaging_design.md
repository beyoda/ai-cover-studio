# Hermes Messaging Gateway — Platform Design

> Phase: **AIVOICE v1.2-2**（阶段一）  
> Date: 2026-07-26  
> Scope: 为 AIVOICE 移动入口选型 Messaging Adapter；**不改** Pipeline / Adapter / GUI / Registry / MusicSource 核心 / SVC / UVR

---

## 目标链路

```text
手机消息平台
      ↓
Hermes Gateway（Messaging Adapter）
      ↓
Hermes Agent
      ↓
aivoice-cover Skill
      ↓
CoverService.submit → status → result
      ↓
文本摘要 + cover.mp3 回传手机
```

---

## 1. 平台分析

### 1.1 Feishu / Lark（飞书）

| 维度 | 评估 |
|------|------|
| Hermes 支持 | 一等公民；`websocket` / `webhook`；文档完整 |
| 接入成本 | 中：开放平台建应用 + 权限 + 发布；可用 `hermes gateway setup` 扫码 |
| 国内可用性 | **高**（飞书中国域 `FEISHU_DOMAIN=feishu`） |
| 文件发送 | ✅ `im:resource` + `send_document` / 文件气泡 |
| 音频返回 | ✅ mp3/wav 等可上传为文件或语音类附件 |
| 长任务通知 | ✅ 可持续回复 / 编辑；cron home channel；适合「提交后分阶段更新」 |
| 额外优势 | 企业内可控 allowlist；WebSocket **无需公网**（笔记本即可） |

### 1.2 Telegram

| 维度 | 评估 |
|------|------|
| Hermes 支持 | 最成熟之一；polling / webhook |
| 接入成本 | **低**：BotFather 拿 token 即可 |
| 国内可用性 | **低/不稳定**（需代理；个人手机常无法直连） |
| 文件发送 | ✅ 文档/音频完善；`hermes send "MEDIA:path"` |
| 音频返回 | ✅ voice / audio / document |
| 长任务通知 | ✅ 多条消息 / 流式编辑 |

### 1.3 其他 Messaging Adapter（摘要）

| 平台 | 国内 | 文件/音频 | 接入成本 | 备注 |
|------|------|-----------|----------|------|
| Discord | 低 | 强 | 低 | 偏海外开发者 |
| Slack | 低 | 强 | 中 | 企业海外 |
| WhatsApp | 中低 | 有 | 高 | 商务云 API / 封号风险 |
| Signal | 低 | 有 | 中 | 隐私向 |
| 钉钉 DingTalk | 高 | 中 | 中 | Hermes 有适配；偏企业 |
| 企微 WeCom | 高 | 中高 | 中 | WebSocket AI Bot |
| 微信 Weixin | 高 | 有 | 中高 | iLink；个人号策略敏感 |
| QQ | 高 | 有 | 中 | 另配 |
| Webhook | N/A | 经 deliver 转发 | **最低** | 适合本机联调，不是终端用户 App |

---

## 2. 对比矩阵（AIVOICE 移动入口）

| 标准 | Feishu | Telegram | 钉钉/企微 | Webhook 联调 |
|------|--------|----------|-----------|--------------|
| 接入成本 | 中 | 低 | 中 | 最低 |
| 国内可用性 | **优** | 差 | 优 | 本机/内网 |
| 文件发送 | 优 | 优 | 中～优 | 依赖 deliver 目标 |
| 音频返回 | 优 | 优 | 中～优 | 同上 |
| 长任务通知 | 优 | 优 | 中～优 | 优（可多次 POST） |
| 与现有 AIVOICE | 旧 Flask 飞书蓝图可参考权限模型 | 无历史债 | 无 | 仅联调 |

---

## 3. 推荐方案

**首选：Feishu（飞书）+ Hermes Gateway WebSocket**

理由：

1. **国内手机可达**，符合「移动入口」前提（Telegram 在国内不可作为主路径）。  
2. Hermes 已支持文本 / 图片 / **文件 / 音频**回传，覆盖翻唱产物 `cover.mp3`。  
3. WebSocket 长连接：**无需公网 webhook**，本机 GPU 工作站即可当 Gateway。  
4. Allowlist（`FEISHU_ALLOWED_USERS`）适合单用户/家庭原型，暂不做多用户系统。  
5. 与 AIVOICE 仓库内历史 `server/feishu.py` 权限/回传思路一致，但**正式入口走 Hermes**，不再绕过 Skill。

**备选：**

- 开发联调：Hermes **Webhook**（本机 HTTP 模拟手机消息）。  
- 海外个人：Telegram（凭证到手即可，不作为国内主入口）。

**明确不选（本阶段）：** WhatsApp / 微信个人号主路径（合规与稳定性成本高）；不做自建 Worker。

---

## 4. 接入蓝图（Feishu）

### 4.1 环境变量（`%LOCALAPPDATA%\hermes\.env`）

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_DOMAIN=feishu
FEISHU_CONNECTION_MODE=websocket
# FEISHU_ALLOWED_USERS=ou_xxx   # 强烈建议
```

### 4.2 Gateway

```bash
hermes gateway setup   # 选 Feishu / Lark
hermes gateway run     # 前台运行验收
```

### 4.3 Skill 契约（消息侧）

用户：「用示例歌手声音翻唱示例曲目」/ 「使用示例歌手声音翻唱示例歌手-示例曲目.mp3」

Agent → `aivoice-cover` → stdout：

```json
{
  "status": "completed",
  "song": "示例曲目",
  "voice": "示例歌手",
  "pitch": 0,
  "duration": "34s",
  "output_path": "<repo-root>\\outputs\\...\\cover.mp3"
}
```

Agent 回复手机：

```text
歌曲: 示例曲目
音色: 示例歌手
状态: completed
```

并发送附件：`cover.mp3`（`MEDIA:<output_path>` / Feishu file upload）。

### 4.4 边界

| 做 | 不做 |
|----|------|
| Gateway + Feishu Adapter 配置 | 改 Pipeline / UVR / SVC |
| Skill 参数与回传文案 | Voice Registry / MusicSource 核心重写 |
| 单用户 allowlist | 多用户队列 / Worker / GPU 优化 |

---

## 5. 风险与依赖

| 风险 | 缓解 |
|------|------|
| 无 `FEISHU_APP_ID/SECRET` 无法真收手机消息 | 先完成设计 + Skill 回传原型；凭证到位后 `gateway run` 即接 |
| 长翻唱阻塞 Agent 回合 | 沿用 Skill 同进程轮询 + 阶段 stderr；后续再 Worker |
| 用户只发歌名「示例曲目」 | Skill 侧在 `test_songs/` 做安全本地模糊匹配（不刮网） |
| 企业应用需管理员审批 | 个人/小团队用自建应用 + 发布版本 |

---

## 6. 阶段结论

**推荐平台：Feishu（Hermes Messaging Gateway）。**  
下一阶段：写入 Hermes 配置脚手架 → 凭证接入后验证「手机 → Gateway 收信 → Skill → cover.mp3 回传」。
