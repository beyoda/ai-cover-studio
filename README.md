# AI Cover Studio v1

Windows 本地 AI 音乐翻唱工程。目标流程：输入音频 -> 人声分离 -> SVC 换声 -> 混音 -> WAV/MP3 输出。

## 已完成

- 标准 Python src 项目结构
- UI -> Pipeline -> Modules -> External Tools 分层
- PyQt6 桌面 UI
- CLI 调试入口
- YAML 配置系统
- 统一日志
- UVR / SVC / ffmpeg wrapper
- mock_mode：没有模型和外部工具也能跑通流程
- PyInstaller 打包脚本
- pytest 基础测试

## 快速运行

```powershell
cd D:\codex-aivoice
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_gui.ps1
```

CLI：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_cli.ps1 -InputAudio "D:\path\song.wav" -ModelName demo
```

## 接入真实工具

默认 `config/default.yaml` 中 `runtime.mock_mode: true`，先验证工程、UI、日志、打包流程。

接真实处理时：

1. 安装 ffmpeg，或把 ffmpeg.exe 路径写入 `config/mix.yaml`。
2. 安装 audio-separator/UVR，修改 `config/uvr.yaml` 命令模板。
3. 放入 so-vits-svc 和模型，修改 `config/svc.yaml`。
4. 将 `runtime.mock_mode` 改为 `false`。

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

输出在 `dist\AI Cover Studio\`。
