# AIVOICE / AI Cover Studio v1.0

Windows 本地 **AI 翻唱服务**：用飞书说话点歌，本机自动制作并回传 MP3。

```text
飞书 → Hermes → 入队 → Worker → UVR/SVC → 飞书收到成品
```

仓库：<https://github.com/beyoda/ai-cover-studio>  
版本：`v1.0.0` Stable（见 [CHANGELOG.md](CHANGELOG.md)）

---

## 1. Clone（记得拉 LFS）

```powershell
git lfs install
git clone https://github.com/beyoda/ai-cover-studio.git
cd ai-cover-studio
git checkout v1.0.0
git lfs pull
```

仓库包含：

- 代码 + Hermes Skill
- **示例音色**：示例歌手 / `example_voice`（`examples/voices/example_voice/`，Git LFS）
- **示例 UVR 模型**（`examples/models/uvr/`，Git LFS）
- **示例测试音频**（`examples/audio/sample_input.mp3`，合成短音，非商业歌曲）

仓库**不含**：完整 `tools/so-vits-svc/workenv`（约 5GB CUDA 环境）。用一键脚本安装/拷贝。

---

## 2. 一键安装工具与示例模型

前提：已装 [Git LFS](https://git-lfs.com)、[ffmpeg](https://ffmpeg.org/download.html)（在 PATH）。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .

# 一键：拉 LFS、准备 so-vits-svc 源码、安装 example_voice+UVR 到运行目录、改配置路径
.\scripts\setup_tools.ps1
```

若提示缺少 `tools\so-vits-svc\workenv\python.exe`：

- 从你的备份盘拷贝整个 `workenv` 到 `tools\so-vits-svc\workenv`，或  
- 按 so-vits-svc 文档自建 CUDA Python 环境后再跑翻唱。

---

## 3. 日常怎么用（推荐：飞书）

### 启动 Gateway（常驻）

```powershell
hermes gateway run
```

### 对机器人说（示例歌手示例）

```text
用示例歌手声音翻唱晴天
```

或：

```text
用 example_voice 翻唱花洒
用 example_voice 翻唱晴天，升一个 key
```

有多版本时回复序号，例如 `1`。  
先收到「已入队」，大约 1 分钟后收到完成通知 + `cover.mp3`。

### 本地文件示例（合成测试音）

把路径发给 Skill / 或在 GUI 里打开：

```text
examples/audio/sample_input.mp3
```

自然语言示例：

```text
用 example_voice 翻唱 examples/audio/sample_input.mp3
```

---

## 4. Worker 要不要手动开？

一般不用。入队后会自动 kick，队列做完退出。

手动排空：

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m aivoice_studio.worker --drain
```

---

## 5. 备选：桌面 GUI

```powershell
.\AI Cover Studio.bat
```

或：

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m aivoice_studio
```

---

## 6. 目录速查

| 路径 | 作用 |
|------|------|
| `examples/` | 示例音色 / UVR / 测试 MP3（见 [examples/README.md](examples/README.md)） |
| `scripts/setup_tools.ps1` | 一键安装到运行目录 |
| `hermes_skill/media/aivoice-cover/` | 飞书 Skill |
| `src/aivoice_studio/worker/` | 任务 Worker |
| `src/aivoice_studio/notifier/` | 飞书推送 |
| `outputs/{job_id}/cover.mp3` | 成品 |

冻结说明：[AIVOICE_V1.0_RELEASE.md](AIVOICE_V1.0_RELEASE.md)

---

## 7. 免责声明

示例 `example_voice` 音色仅用于打通技术链路的个人/研究用途。  
请勿在未获授权时将他人音色或歌曲用于商业传播。请替换为你有权使用的资产。

---

## License

MIT（第三方模型/歌曲版权归原权利人，不因本仓库 MIT 而改变）
