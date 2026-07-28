# 什么样的模型能用？如何训练？

AIVOICE 的音色转换层当前绑定 **so-vits-svc 4.x**（本仓默认推理脚本 `inference_main.py`）。

---

## 1. 试听示例（在线）

打开仓库中的预览文件即可在 GitHub 网页播放：

- **示例歌手 / example_voice 音色预览**：[`examples/demo/eason_preview.mp3`](../examples/demo/eason_preview.mp3)

（由 `examples/audio/sample_input.mp3` 经 UVR + example_voice SVC 生成的短样例，用于展示链路，非正式发行歌曲。）

---

## 2. AIVOICE 能直接用的模型

### 必须满足

| 项 | 要求 |
|----|------|
| 框架 | **so-vits-svc 4.0 / 4.1** 系列 checkpoint |
| 文件 | `G_xxxxx.pth`（生成器）+ 配套 `config.json`（或本仓命名的 `config1.json`） |
| 采样率 | 与 config 一致，本示例为 **44100** |
| 说话人 | config 里 `spk` 至少有一个 speaker（本示例 `{"output": 0}`） |
| 特征编码器 | 与训练时一致；本示例为 **`vec768l12`**（`ssl_dim` / `gin_channels` = 768） |
| 放置位置 | `tools/so-vits-svc/logs/44k/`（或你在 `config/voices.json` / `config/svc.yaml` 里配置的 `models_dir`） |

### 注册到 AIVOICE

编辑 [`config/voices.json`](../config/voices.json)：

```json
"example_voice": {
  "display_name": "示例歌手",
  "checkpoint": "G_27200.pth",
  "config": "config1.json",
  "enabled": true,
  "aliases": ["example_voice", "示例歌手"]
}
```

然后自然语言即可：`用示例歌手声音翻唱…` / `用 example_voice 翻唱…`。

### 目前不直接兼容

- **RVC / Retrieval-based Voice Conversion**（另一套权重与推理）
- **VITS / GPT-SoVITS / OpenVoice** 等非 so-vits-svc 格式
- 只有 `.onnx` 的 SVC、或缺少配对 `config` 的裸 `.pth`
- 训练用的 `D_*.pth`（判别器）——推理只需 **`G_*.pth`**

若要支持 RVC 等，属于后续版本，不在 v1.0 范围。

---

## 3. 训练流程（概要）

训练不在 AIVOICE 进程内完成，请在 **so-vits-svc** 工程中训练，再把产物拷进本仓。

官方参考：

- 英文 / 中文说明：<https://github.com/svc-develop-team/so-vits-svc>

### 推荐步骤

1. **准备干净干声**  
   目标音色的干声片段（尽量少混响、少伴奏）。可用本仓 UVR 先把歌曲拆成人声再切片。

2. **按 so-vits-svc 规范建数据集**  
   - 重采样到目标采样率（如 44.1k）  
   - 切片（常见 5–15 秒）  
   - 生成 filelist（`train.txt` / `val.txt`）

3. **提取特征**  
   按所选 speech encoder（如 ContentVec 768 / Hubert）跑预处理（hubert/f0 等）。  
   **编码器必须与日后推理 config 一致。**

4. **训练**  
   ```text
   python train.py -c configs/config.json -m 44k
   ```
   （具体命令以你使用的 so-vits-svc 版本 README 为准。）

5. **导出 / 选取 checkpoint**  
   取验证效果较好的 `G_xxxxx.pth`，连同**同一套** `config.json` 复制到：  
   `tools/so-vits-svc/logs/44k/`

6. **接入 AIVOICE**  
   - 写入 `config/voices.json`  
   - 飞书或 GUI 用新 `voice_id` 试听  
   - 可选：把短预览 mp3 放到 `examples/demo/` 方便 GitHub 在线播放

### 数据量经验（经验值，非硬性）

| 目标 | 干声量（大约） |
|------|----------------|
| 能听出像谁、可玩 | 10–30 分钟 |
| 更稳、更少破音 | 1 小时以上 |

音质、降噪、音高标注质量往往比「堆时长」更重要。

---

## 4. 本仓示例资产对照

| 文件 | 说明 |
|------|------|
| `examples/voices/example_voice/G_27200.pth` | 示例 G 权重（Git LFS） |
| `examples/voices/example_voice/config1.json` | 配对配置（vec768l12 / 44.1k） |
| `examples/demo/eason_preview.mp3` | **可在线试听**的短翻唱预览 |
| `scripts/setup_tools.ps1` | 一键拷贝到运行目录 |

---

## 5. 免责声明

完整条款见 **[DISCLAIMER.md](DISCLAIMER.md)**。

摘要：示例音色与预览音频仅用于技术演示；不代表艺人授权。训练数据、自建模型与翻唱成品的版权与合规责任由使用者承担；禁止未授权商用与公开伪冒。
