# Examples (v1.0)

These files are meant for **clone + one-click setup**, not for shipping the full 10GB `tools/` tree.

## Online demo (play in browser)

Open on GitHub to hear the example voice:

- **[demo/eason_preview.mp3](demo/eason_preview.mp3)** — ~25s clip from a completed example_voice cover of《示例曲目》(technical demo only; not an official release)

Model requirements & training: [docs/MODEL_GUIDE.md](../docs/MODEL_GUIDE.md)

| Path | What |
|------|------|
| `demo/eason_preview.mp3` | **Playable showcase** (~25s example_voice clip, Git LFS) |
| `voices/example_voice/G_27200.pth` | Example SVC checkpoint (Git LFS, ~599MB) |
| `voices/example_voice/config1.json` | Matching config |
| `models/uvr/UVR_MDXNET_Main.onnx` | Example UVR model (Git LFS, ~64MB) |
| `audio/sample_input.mp3` | Synthetic 12s test tone (not a commercial song) |

## Disclaimer

**Full text (Chinese):** [docs/DISCLAIMER.md](../docs/DISCLAIMER.md)

- The `example_voice` checkpoint and `demo/eason_preview.mp3` are **technical demos only** (pipeline wiring). They are **not** an official license, endorsement, or commercial voice pack.
- Do **not** use example voices or song covers for commercial distribution, ads, or misleading “official voice” claims without proper rights.
- Song search / cover / redistribution compliance is **your** responsibility.
- Replace example assets with voices and audio you are allowed to use. If you disagree, stop using the repo and delete the example models.

## Install into runtime paths

From repo root:

```powershell
.\scripts\setup_tools.ps1
```
