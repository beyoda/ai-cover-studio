# AIVOICE / AI Cover Studio v1.0

Windows 本地 **AI 翻唱服务**：用飞书说话点歌，本机自动制作并回传 MP3。

```text
飞书 → Hermes → 入队 → Worker → UVR/SVC → 飞书收到成品
```

仓库：<https://github.com/beyoda/ai-cover-studio>  
版本：`v1.0.0` Stable（见 [CHANGELOG.md](CHANGELOG.md)）

---

## 1. Clone

```powershell
git clone https://github.com/beyoda/ai-cover-studio.git
cd ai-cover-studio
git checkout v1.0.0
```

> **注意：** GitHub 仓库**不含**模型权重与 `.venv`（体积大）。需要本机已有 UVR / so-vits-svc 模型与工具链，或从你的备份盘拷贝 `models/`、`tools/`。

---

## 2. 一分钟环境（开发机）

前提：Windows + 已安装 [ffmpeg](https://ffmpeg.org/download.html)（在 PATH 里）。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
# 若缺依赖：pip install -r requirements.txt
```

把音色写进 `config/voices.json`（仓库已带示例）。确认 `config/uvr.yaml`、`config/svc.yaml` 指向本机模型路径。

---

## 3. 日常怎么用（推荐：飞书）

### 3.1 启动 Gateway（常驻）

```powershell
hermes gateway run
```

保持这个窗口开着。电脑睡眠/关机后飞书不会再响应。

### 3.2 手机 / 飞书私聊机器人

直接说，例如：

```text
用 example_voice_b 翻唱古巨基的花洒
```

有多版本时回复序号，例如 `1`。

你会先收到「已入队」；大约 **1 分钟**后收到完成通知 + `cover.mp3`。

可选：

```text
用 example_voice_b 翻唱晴天，升两个 key
用 example_voice 翻唱花洒，不要混响
```

### 3.3 Worker 要不要开？

**一般不用手动开。**  
入队后会自动 kick：做完队列就退出。

若要手动排空队列：

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m aivoice_studio.worker --drain
```

---

## 4. 备选：桌面 GUI

若你装过启动脚本：

```powershell
# 若存在
.\AI Cover Studio.bat
```

或：

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m aivoice_studio
```

拖歌 → 选音色 → 生成。成品在 `outputs/`。

---

## 5. 目录速查

| 路径 | 作用 |
|------|------|
| `hermes_skill/media/aivoice-cover/` | 飞书 Skill |
| `src/aivoice_studio/worker/` | 任务 Worker |
| `src/aivoice_studio/notifier/` | 飞书推送 |
| `jobs/` | 队列状态（运行时生成 json） |
| `outputs/{job_id}/cover.mp3` | 成品 |
| `config/voices.json` | 音色注册表 |

更完整的冻结说明：[AIVOICE_V1.0_RELEASE.md](AIVOICE_V1.0_RELEASE.md)

---

## 6. 开发自检

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m pytest -q
```

---

## License

MIT
