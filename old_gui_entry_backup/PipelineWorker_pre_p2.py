"""Backup of GUI cover entry BEFORE P2 (GUI → CoverService migration).

Source: git HEAD src/aivoice_studio/ui/main_window.py (PipelineWorker)
Restore: copy PipelineWorker.run (and related imports) back into main_window.py
"""

from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from aivoice_studio.core.context import JobContext
from aivoice_studio.factory import build_pipeline
from aivoice_studio.utils.paths import resolve_path

# NOTE: _friendly_error lives in main_window.py; keep that helper when restoring.

class PipelineWorker(QThread):
    progress = pyqtSignal(str, int, str, float)  # state, pct, msg, elapsed_s
    done = pyqtSignal(str, str)
    error = pyqtSignal(str)

    def __init__(self, input_audio: Path, model_name: str, pitch: int, accompaniment: str = "", reverb: str = "关闭") -> None:
        super().__init__()
        self.input_audio = input_audio
        self.model_name = model_name
        self.pitch = pitch
        self.accompaniment = accompaniment
        self.reverb = reverb
        self._t0 = 0.0
        self._stage_t0 = 0.0
        self._last_stage = ""

    def run(self) -> None:
        self._t0 = time.time()
        self._stage_t0 = self._t0

        def cb(state, pct: int, msg: str) -> None:
            stage = state.value if hasattr(state, "value") else str(state)
            now = time.time()
            if stage != self._last_stage:
                self._stage_t0 = now
                self._last_stage = stage
            elapsed = now - self._stage_t0
            self.progress.emit(stage, pct, msg, elapsed)

        try:
            pipeline, config = build_pipeline(cb)
            rt = config.get("runtime", {})
            result = pipeline.run(JobContext(
                input_audio=self.input_audio,
                model_name=self.model_name,
                pitch=self.pitch,
                f0_method=config.get("svc", {}).get("f0_method", "rmvpe"),
                workdir=resolve_path(rt.get("workdir", "workdir")),
                output_dir=resolve_path(rt.get("output_dir", "outputs")),
                export_mp3=bool(config.get("pipeline", {}).get("export_mp3", True)),
                accompaniment=self.accompaniment,
                reverb=self.reverb,
            ))
            if result.success:
                self.done.emit(str(result.wav_path or ""), str(result.mp3_path or ""))
            else:
                self.error.emit(_friendly_error(result.error or "未知错误"))
        except FileNotFoundError as e:
            self.error.emit(f"找不到文件：{e}\n请检查文件是否存在，或重新选择文件")
        except PermissionError as e:
            self.error.emit(f"无法读写文件：{e}\n请以管理员身份运行，或检查文件夹权限")
        except MemoryError:
            self.error.emit("内存不足\n请关闭其他程序后重试，或尝试处理更短的歌曲")
        except OSError as e:
            if "No space" in str(e) or "disk" in str(e).lower():
                self.error.emit("磁盘空间不足\n请清理磁盘，至少保留 1GB 可用空间")
            else:
                self.error.emit(f"系统错误：{e}\n请重试，如果问题持续请联系开发者")
        except Exception as e:
            msg = str(e)
            if "model" in msg.lower() or "pth" in msg.lower():
                self.error.emit(f"模型加载失败：{e}\n请检查 logs/44k/ 目录下的模型文件是否完整")
            else:
                self.error.emit(f"处理失败：{e}\n请重试，如果问题持续请联系开发者")
        finally:
            # log full error to file
            pass

    @property
    def elapsed(self) -> float:
        return time.time() - self._t0
