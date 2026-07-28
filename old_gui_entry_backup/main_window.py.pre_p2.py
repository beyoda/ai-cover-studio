"""AI Cover Studio v1.0 — Spotify-style UI."""

from __future__ import annotations

import os
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QProgressBar, QPushButton, QScrollArea, QSlider, QStackedWidget,
    QTabBar, QTextEdit, QVBoxLayout, QWidget,
)

from aivoice_studio.core.context import JobContext
from aivoice_studio.factory import build_pipeline
from aivoice_studio.ui.history_store import HistoryStore
from aivoice_studio.ui.library_scanner import LibraryScanner
from aivoice_studio.ui.library_page import LibraryPage
from aivoice_studio.ui.model_config_map import ModelConfigMap
from aivoice_studio.ui.theme import (
    ACCENT, BG, BG_CARD, BORDER, GLOBAL_QSS,
    TEXT, TEXT_DIM, TEXT_SEC,
)
from aivoice_studio.utils.config import ConfigLoader
from aivoice_studio.utils.paths import resolve_path


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


class DownloadWorker(QThread):
    """Download audio from B站/YouTube link via yt-dlp."""
    progress = pyqtSignal(str)  # status message
    finished = pyqtSignal(str)  # local file path
    error = pyqtSignal(str)

    def __init__(self, url: str, output_dir: str) -> None:
        super().__init__()
        self.url = url
        self.output_dir = output_dir

    def run(self) -> None:
        try:
            from yt_dlp import YoutubeDL
            self.progress.emit("解析链接中…")
            opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{self.output_dir}/%(title)s.%(ext)s",
                "quiet": True,
                "no_warnings": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                title = info.get("title", "audio")
                self.progress.emit(f"下载完成: {title}")
                path = f"{self.output_dir}/{title}.mp3"
                self.finished.emit(path)
        except Exception as e:
            self.error.emit(f"下载失败: {e}")


def _icon(char: str, size: int = 32, color: str = ACCENT) -> QLabel:
    widget = QLabel(char)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    widget.setStyleSheet(
        f"font-size:{size}px; color:{color}; background:transparent;"
    )
    return widget


def _txt(text: str, size: int = 14, color: str = TEXT, bold: bool = False, align: bool = False) -> QLabel:
    weight = "bold" if bold else "normal"
    halign = Qt.AlignmentFlag.AlignCenter if align else Qt.AlignmentFlag.AlignLeft
    label = QLabel(text)
    label.setAlignment(halign)
    label.setWordWrap(True)
    label.setStyleSheet(
        f"font-size:{size}px; font-weight:{weight}; color:{color}; background:transparent;"
    )
    return label


def _friendly_error(raw: str) -> str:
    """Map technical errors to user-friendly Chinese messages."""
    if not raw:
        return "未知错误"
    lower = raw.lower()
    if "file not found" in lower or "no such file" in lower or "找不到" in raw:
        return f"找不到文件\n{raw}\n请检查文件是否存在，或重新选择"
    if "permission" in lower or "denied" in lower:
        return f"无法读写文件\n{raw}\n请检查文件夹权限"
    if "memory" in lower:
        return f"内存不足\n{raw}\n请关闭其他程序后重试"
    if "no space" in lower or "disk" in lower:
        return f"磁盘空间不足\n{raw}\n请清理磁盘，至少保留 1GB 可用空间"
    if "model" in lower or "pth" in lower or "checkpoint" in lower:
        return f"模型加载失败\n{raw}\n请检查 logs/44k/ 目录下的模型文件是否完整"
    if "ffmpeg" in lower or "codec" in lower:
        return f"音频处理失败\n{raw}\n请检查音频文件是否损坏"
    if "command failed" in lower or "return code" in lower:
        return f"外部工具执行失败\n{raw}\n请重试，如果问题持续请联系开发者"
    return f"处理失败\n{raw}\n请重试，如果问题持续请联系开发者"


def _spacer(h: int = 12) -> QWidget:
    widget = QWidget()
    widget.setFixedHeight(h)
    widget.setStyleSheet("background:transparent;")
    return widget


def _hsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color:{BORDER}; background:transparent;")
    return f


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Cover Studio")
        self.setMinimumSize(760, 600)
        self.resize(800, 720)
        self.setStyleSheet(GLOBAL_QSS)

        self._input_path = ""
        self._accomp_path = ""
        self._worker: PipelineWorker | None = None
        self._history = HistoryStore()
        self._history.load()

        cfg = ConfigLoader().load()
        svc = cfg.get("svc", {})
        self._model_map = ModelConfigMap(svc.get("models_dir", "models"))
        self._models = self._model_map.list_models()
        self._def_model = svc.get(
            "default_model", self._models[0] if self._models else "G_16000"
        )
        self._stat_count = len(self._history.all())

        # smooth progress animation
        self._target_progress = 0
        self._display_progress = 0
        self._progress_timer = QTimer()
        self._progress_timer.timeout.connect(self._tick_progress)
        self._progress_timer.setInterval(80)

        self._build()
        self._restore_geo()

    def _build(self) -> None:
        c = QWidget()
        c.setObjectName("Main")
        self.setCentralWidget(c)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_home())
        self._stack.addWidget(self._build_result())
        self._library_page = LibraryPage()
        self._stack.addWidget(self._library_page)

        self._bottom_panel = self._build_bottom_panel()
        self._bottom_panel.setVisible(False)

        root = QVBoxLayout(c)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())
        root.addWidget(self._stack, stretch=1)
        root.addWidget(self._bottom_panel)
        root.addWidget(self._build_statusbar())
        self._stack.setCurrentIndex(0)

    # ── top bar ────────────────────────────────────

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 4, 16, 4)
        row.addWidget(_icon("♫", 16, ACCENT))
        row.addWidget(_txt("AI Cover Studio", 13, ACCENT, bold=True))

        # tabs
        self._tab_gen = QPushButton("翻唱")
        self._tab_lib = QPushButton("作品库")
        for btn in (self._tab_gen, self._tab_lib):
            btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton{{background:transparent;color:{TEXT_DIM};border:none;"
                f"font-size:13px;padding:6px 16px;margin:0 2px;border-radius:4px;}}"
                f"QPushButton:checked{{color:{TEXT};background:#1A1A1A;}}"
                f"QPushButton:hover{{color:{TEXT};}}"
            )
            row.addWidget(btn)
        self._tab_gen.setChecked(True)
        self._tab_gen.clicked.connect(lambda: self._switch_tab(0))
        self._tab_lib.clicked.connect(lambda: self._switch_tab(1))

        row.addStretch()
        row.addWidget(_txt("v1.0", 10, TEXT_DIM))
        return bar

    # ── home ───────────────────────────────────────

    def _build_home(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea{{background:{BG};border:none;}}")

        w = QWidget()
        w.setMaximumWidth(620)
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 20, 0, 16)
        ly.setSpacing(12)

        # drop zone
        self._drop = QFrame()
        self._drop.setObjectName("DropArea")
        self._drop.setAcceptDrops(True)
        self._drop.setMinimumHeight(120)
        self._drop.dragEnterEvent = self._drag_enter
        self._drop.dragLeaveEvent = self._drag_leave
        self._drop.dropEvent = self._drop_event
        self._drop.mousePressEvent = lambda e: self._browse_audio()

        dz = QVBoxLayout(self._drop)
        dz.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz.setSpacing(6)
        dz.addWidget(_icon("♫", 36, ACCENT))
        self._drop_label = _txt("拖拽音频文件到此处", 16, TEXT, bold=True, align=True)
        dz.addWidget(self._drop_label)
        dz.addWidget(_txt("MP3 · WAV · FLAC · M4A · OGG", 12, TEXT_DIM, align=True))
        dz.addWidget(_txt("或", 13, TEXT_DIM, align=True))
        btn = QPushButton("选择文件")
        btn.setObjectName("Secondary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._browse_audio)
        br = QHBoxLayout()
        br.setAlignment(Qt.AlignmentFlag.AlignCenter)
        br.addWidget(btn)
        dz.addLayout(br)
        ly.addWidget(self._drop)

        # paste link row
        link_row = QHBoxLayout()
        link_row.setSpacing(8)
        self._link_input = QLineEdit()
        self._link_input.setPlaceholderText("粘贴 B站 / YouTube 链接…")
        self._link_input.setStyleSheet(
            "QLineEdit{background:#1A1A1A;border:1px solid #2A2A2A;border-radius:8px;"
            "padding:8px 12px;color:#E8E8E8;font-size:12px;}"
            "QLineEdit:focus{border-color:#1ED760;}"
        )
        link_row.addWidget(self._link_input, stretch=1)
        self._link_btn = QPushButton("下载")
        self._link_btn.setObjectName("Secondary")
        self._link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link_btn.clicked.connect(self._download_link)
        link_row.addWidget(self._link_btn)
        ly.addLayout(link_row)
        self._link_status = _txt("", 11, TEXT_SEC)
        self._link_status.setVisible(False)
        ly.addWidget(self._link_status)

        # song card
        self._song_card = QFrame()
        self._song_card.setObjectName("SongCard")
        self._song_card.setFixedHeight(64)
        self._song_card.setVisible(False)
        sc = QHBoxLayout(self._song_card)
        sc.setContentsMargins(14, 10, 14, 10)
        sc.setSpacing(12)
        sc.addWidget(_icon("♫", 26, ACCENT))
        info = QVBoxLayout()
        info.setSpacing(2)
        self._song_title = _txt("", 14, TEXT, bold=True)
        self._song_detail = _txt("", 12, TEXT_DIM)
        info.addWidget(self._song_title)
        info.addWidget(self._song_detail)
        sc.addLayout(info, stretch=1)
        ly.addWidget(self._song_card)

        # params card
        card = QFrame()
        card.setObjectName("SongCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 12, 18, 12)
        cl.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(16)

        m_col = QVBoxLayout()
        m_col.setSpacing(4)
        m_col.addWidget(_txt("音色模型", 12, TEXT_SEC))
        self._model_combo = QComboBox()
        self._model_combo.addItems(self._models if self._models else ["G_16000"])
        d = self._def_model
        self._model_combo.setCurrentText(
            d if d in self._models else (self._models[0] if self._models else "G_16000")
        )
        m_col.addWidget(self._model_combo)
        row1.addLayout(m_col, stretch=1)

        p_col = QVBoxLayout()
        p_col.setSpacing(4)
        self._pitch_label = _txt("音高  0", 12, TEXT_SEC)
        p_col.addWidget(self._pitch_label)
        self._pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self._pitch_slider.setRange(-12, 12)
        self._pitch_slider.setValue(0)
        self._pitch_slider.valueChanged.connect(
            lambda v: self._pitch_label.setText(f"音高  {v:+d}")
        )
        p_col.addWidget(self._pitch_slider)
        row1.addLayout(p_col, stretch=2)

        cl.addLayout(row1)
        cl.addWidget(_hsep())

        # reverb
        reverb_row = QHBoxLayout()
        reverb_row.setSpacing(8)
        reverb_row.addWidget(_txt("混响", 12, TEXT_SEC))
        self._reverb_combo = QComboBox()
        self._reverb_combo.addItems(["关闭", "录音棚", "现场", "大教堂"])
        reverb_row.addWidget(self._reverb_combo, stretch=1)
        reverb_row.addStretch()
        cl.addLayout(reverb_row)

        # accompaniment
        acc_row = QHBoxLayout()
        acc_row.setSpacing(8)
        acc_col = QVBoxLayout()
        acc_col.setSpacing(4)
        acc_col.addWidget(_txt("伴奏文件（可选）", 12, TEXT_SEC))
        self._accomp_label = _txt(
            "跳过人声分离 · 使用自己的伴奏，音质更佳", 11, TEXT_DIM
        )
        acc_col.addWidget(self._accomp_label)
        acc_row.addLayout(acc_col, stretch=1)
        self._accomp_btn = QPushButton("选择")
        self._accomp_btn.setObjectName("Secondary")
        self._accomp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._accomp_btn.clicked.connect(self._browse_accomp)
        self._accomp_clear = QPushButton("✕")
        self._accomp_clear.setObjectName("LinkBtn")
        self._accomp_clear.setVisible(False)
        self._accomp_clear.clicked.connect(self._clear_accomp)
        acc_row.addWidget(self._accomp_btn)
        acc_row.addWidget(self._accomp_clear)
        cl.addLayout(acc_row)
        ly.addWidget(card)

        # generate button
        self._gen = QPushButton("生成翻唱")
        self._gen.setObjectName("Primary")
        self._gen.setMinimumHeight(52)
        self._gen.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gen.clicked.connect(self._start)
        ly.addWidget(self._gen)

        # progress
        self._prog = QProgressBar()
        self._prog.setRange(0, 100)
        self._prog.setValue(0)
        self._prog.setTextVisible(False)
        self._prog.setVisible(False)
        ly.addWidget(self._prog)
        self._prog_text = _txt("", 13, TEXT_SEC)
        self._prog_text.setVisible(False)
        ly.addWidget(self._prog_text)

        # stage labels
        self._stage_uvr = _txt("", 12, TEXT_DIM)
        self._stage_svc = _txt("", 12, TEXT_DIM)
        self._stage_mix = _txt("", 12, TEXT_DIM)
        for s in (self._stage_uvr, self._stage_svc, self._stage_mix):
            s.setVisible(False)
            ly.addWidget(s)

        # recent covers gallery
        ly.addWidget(_spacer(8))
        ly.addWidget(_txt("最近作品", 15, TEXT, bold=True))
        self._gallery = QVBoxLayout()
        self._gallery.setSpacing(6)
        ly.addLayout(self._gallery)
        self._refresh_gallery()

        ly.addStretch()
        scroll.setWidget(w)
        return scroll

    # ── result page ────────────────────────────────

    def _build_result(self) -> QWidget:
        pg = QWidget()
        pg.setStyleSheet(f"background:{BG};")
        w = QWidget()
        w.setMaximumWidth(420)
        ly = QVBoxLayout(w)
        ly.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.setSpacing(12)

        ly.addWidget(_icon("✓", 52, ACCENT))
        ly.addWidget(_txt("翻唱完成！", 26, TEXT, bold=True, align=True))
        self._result_info = _txt("", 14, TEXT_SEC, align=True)
        ly.addWidget(self._result_info)
        ly.addWidget(_spacer(8))

        self._play_btn = QPushButton("▶  播放 MP3")
        self._play_btn.setObjectName("Primary")
        self._play_btn.setMinimumHeight(44)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.clicked.connect(self._play)
        ly.addWidget(self._play_btn)

        self._folder_btn = QPushButton("打开文件夹")
        self._folder_btn.setObjectName("Secondary")
        self._folder_btn.setMinimumHeight(40)
        self._folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._folder_btn.clicked.connect(self._open_dir)
        ly.addWidget(self._folder_btn)

        self._again_btn = QPushButton("再来一首")
        self._again_btn.setObjectName("LinkBtn")
        self._again_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._again_btn.clicked.connect(self._go_home)
        ly.addWidget(self._again_btn)

        self._result_mp3 = ""
        self._result_dir = ""

        outer = QVBoxLayout(pg)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(w)
        return pg

    # ── bottom panel ───────────────────────────────

    def _build_bottom_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background:{BG_CARD}; border-top:1px solid {BORDER};")
        panel.setMinimumHeight(220)

        tabs = QTabBar()
        tabs.addTab("日志")
        tabs.addTab("历史")
        tabs.addTab("设置")
        tabs.addTab("关于")
        tabs.setExpanding(False)

        stack = QStackedWidget()
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        stack.addWidget(self._log_view)

        hist = QWidget()
        hist.setStyleSheet("background:transparent;")
        self._hist_list = QVBoxLayout(hist)
        self._hist_list.setAlignment(Qt.AlignmentFlag.AlignTop)
        stack.addWidget(hist)
        stack.addWidget(self._build_settings())
        stack.addWidget(self._build_about())

        tabs.currentChanged.connect(stack.setCurrentIndex)
        tabs.currentChanged.connect(
            lambda i: self._refresh_hist_panel() if i == 1 else None
        )

        ly = QVBoxLayout(panel)
        ly.setContentsMargins(12, 4, 12, 8)
        ly.setSpacing(2)
        ly.addWidget(tabs)
        ly.addWidget(stack, stretch=1)
        return panel

    def _build_settings(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        ly = QVBoxLayout(w)
        ly.setSpacing(6)
        cfg = ConfigLoader().load()
        for lbl, kp in [
            ("UVR 模型", ("uvr", "model_name")),
            ("默认音高", ("svc", "pitch")),
            ("输出目录", ("runtime", "output_dir")),
            ("ffmpeg", ("mix", "ffmpeg_path")),
        ]:
            ly.addWidget(_txt(lbl, 11, TEXT_DIM))
            ly.addWidget(_txt(
                str(cfg.get(kp[0], {}).get(kp[1], "—")), 13, TEXT_SEC
            ))
        ly.addStretch()
        return w

    def _build_about(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        ly = QVBoxLayout(w)
        ly.setSpacing(4)
        ly.addWidget(_txt("AI Cover Studio v1.0", 14, TEXT, bold=True))
        ly.addWidget(_txt(
            "Python · PyQt6 · audio-separator · so-vits-svc · ffmpeg",
            12, TEXT_DIM,
        ))
        ly.addWidget(_txt("本地 AI 翻唱流水线。无需联网，无限使用。", 12, TEXT_DIM))
        ly.addStretch()
        return w

    def _build_statusbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 4, 16, 4)
        self._stat_label = QLabel(self._status_text())
        self._stat_label.setStyleSheet(
            f"font-size:11px; color:{TEXT_DIM}; background:transparent;"
        )
        row.addWidget(self._stat_label)
        row.addStretch()
        return bar

    def _status_text(self) -> str:
        return f"已生成 {self._stat_count} 首翻唱"

    def _refresh_status(self) -> None:
        self._stat_count = len(self._history.all())
        self._stat_label.setText(self._status_text())

    # ── gallery / history ──────────────────────────

    def _refresh_gallery(self) -> None:
        while self._gallery.count():
            it = self._gallery.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        entries = self._history.all()
        if not entries:
            self._gallery.addWidget(_txt("你的作品将显示在这里", 13, TEXT_DIM))
            return
        cards = []
        for e in reversed(entries[-6:]):
            card = QFrame()
            card.setObjectName("HistoryCard")
            card.setFixedSize(170, 80)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(2)
            cl.addWidget(_txt(e.song_name[:20], 13, TEXT, bold=True))
            cl.addWidget(_txt(f"{e.model_name} · 音高 {e.pitch:+d}", 11, TEXT_DIM))
            cl.addStretch()
            br = QHBoxLayout()
            br.setSpacing(6)
            play = QPushButton("▶")
            play.setObjectName("Mini")
            play.setFixedSize(30, 22)
            play.clicked.connect(
                lambda checked, d=e.output_dir: self._play_in_library(str(Path(d) / "cover.mp3"))
            )
            br.addWidget(play)
            br.addStretch()
            cl.addLayout(br)
            cards.append(card)
        for i in range(0, len(cards), 3):
            row = QHBoxLayout()
            row.setSpacing(10)
            for c in cards[i:i + 3]:
                row.addWidget(c)
            row.addStretch()
            self._gallery.addLayout(row)

    def _refresh_hist_panel(self) -> None:
        while self._hist_list.count():
            it = self._hist_list.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        entries = self._history.all()
        if not entries:
            self._hist_list.addWidget(_txt("暂无作品", 13, TEXT_DIM))
            return
        for e in reversed(entries):
            row = QWidget()
            row.setStyleSheet(
                f"background:{BG_CARD}; border-radius:6px; padding:4px; margin:1px 0;"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.addWidget(_txt(
                f"{e.song_name} · {e.model_name} · 音高 {e.pitch:+d} · {e.timestamp}",
                12, TEXT_SEC,
            ))
            rl.addStretch()
            btn = QPushButton("打开")
            btn.setObjectName("Mini")
            btn.clicked.connect(lambda checked, d=e.output_dir: self._open_path(d))
            rl.addWidget(btn)
            self._hist_list.addWidget(row)

    # ── drag & drop ────────────────────────────────

    def _drag_enter(self, event) -> None:
        if event.mimeData().hasUrls():
            for u in event.mimeData().urls():
                p = Path(u.toLocalFile())
                if p.suffix.lower() in {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma"}:
                    event.acceptProposedAction()
                    self._drop.setStyleSheet(
                        "QFrame#DropArea{background:#1E1E1E;"
                        "border:2px dashed #1ED760;border-radius:16px;"
                        "margin:16px 24px;padding:40px 20px;}"
                    )
                    # show file info during drag
                    size_mb = p.stat().st_size / (1024 * 1024)
                    info = f"{p.name}  ·  {size_mb:.1f} MB"
                    try:
                        import ffmpeg as ff
                        probe = ff.probe(str(p))
                        a = next((s for s in probe.get("streams", []) if s["codec_type"] == "audio"), None)
                        if a:
                            dur = float(a.get("duration", 0))
                            m, s = divmod(int(dur), 60)
                            info = f"{p.name}  ·  {m}:{s:02d}  ·  {size_mb:.1f} MB"
                    except Exception:
                        pass
                    self._drop_label.setText(f"松开即生成 ✨\n{info}")
                    return
        event.ignore()

    def _drag_leave(self, event) -> None:
        self._drop.setStyleSheet("")
        self._drop_label.setText("拖拽音频文件到此处")

    def _drop_event(self, event) -> None:
        self._drop.setStyleSheet("")
        self._drop_label.setText("拖拽音频文件到此处")
        if event.mimeData().hasUrls():
            for u in event.mimeData().urls():
                p = u.toLocalFile()
                if Path(p).suffix.lower() in {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma"}:
                    self._set_audio(p)
                    return

    def _browse_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "",
            "音频文件 (*.mp3 *.wav *.flac *.m4a *.ogg);;所有文件 (*.*)",
        )
        if path:
            self._set_audio(path)

    def _browse_accomp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择伴奏文件", "",
            "音频文件 (*.mp3 *.wav *.flac *.m4a *.ogg);;所有文件 (*.*)",
        )
        if path:
            self._accomp_path = path
            self._accomp_label.setText(f"✓ {Path(path).name}")
            self._accomp_label.setStyleSheet(
                f"font-size:11px; color:{ACCENT}; background:transparent;"
            )
            self._accomp_clear.setVisible(True)
            self._accomp_btn.setVisible(False)

    def _clear_accomp(self) -> None:
        self._accomp_path = ""
        self._accomp_label.setText("跳过人声分离 · 使用自己的伴奏，音质更佳")
        self._accomp_label.setStyleSheet(
            f"font-size:11px; color:{TEXT_DIM}; background:transparent;"
        )
        self._accomp_clear.setVisible(False)
        self._accomp_btn.setVisible(True)

    def _set_audio(self, path: str) -> None:
        self._input_path = path
        p = Path(path)
        self._song_title.setText(p.name)
        size = f"{p.stat().st_size / 1024 / 1024:.1f} MB"
        detail = size
        try:
            import ffmpeg as ff
            probe = ff.probe(path)
            audio = next(
                (s for s in probe.get("streams", []) if s["codec_type"] == "audio"),
                None,
            )
            if audio:
                dur = float(audio.get("duration", 0))
                mins, secs = divmod(int(dur), 60)
                sr = int(audio.get("sample_rate", 0))
                ch = "立体声" if audio.get("channels") == 2 else "单声道"
                detail = f"{mins}:{secs:02d} · {sr // 1000}kHz · {ch} · {size}"
        except Exception:
            pass
        self._song_detail.setText(detail)
        self._song_card.setVisible(True)

    def _download_link(self) -> None:
        url = self._link_input.text().strip()
        if not url:
            return
        self._link_btn.setEnabled(False)
        self._link_btn.setText("下载中…")
        self._link_status.setVisible(True)
        self._link_status.setText("解析链接中…")

        out_dir = str(Path(__file__).resolve().parents[3] / "downloads")
        os.makedirs(out_dir, exist_ok=True)

        self._dl_worker = DownloadWorker(url, out_dir)
        self._dl_worker.progress.connect(self._link_status.setText)
        self._dl_worker.finished.connect(self._on_dl_done)
        self._dl_worker.error.connect(self._on_dl_error)
        self._dl_worker.start()

    def _on_dl_done(self, path: str) -> None:
        self._link_btn.setEnabled(True)
        self._link_btn.setText("下载")
        self._link_status.setText("✓ 下载完成")
        self._set_audio(path)

    def _on_dl_error(self, msg: str) -> None:
        self._link_btn.setEnabled(True)
        self._link_btn.setText("下载")
        self._link_status.setText(f"✗ {msg}")

    # ── job ────────────────────────────────────────

    def _start(self) -> None:
        if not self._input_path:
            self._log_view.append("⚠ 请先选择音频文件")
            return

        self._gen.setEnabled(False)
        self._gen.setText("处理中…")
        self._target_progress = 0
        self._display_progress = 0
        self._prog.setValue(0)
        self._prog.setVisible(True)
        self._prog_text.setVisible(True)
        self._prog_text.setText("启动中…")
        for s in (self._stage_uvr, self._stage_svc, self._stage_mix):
            s.setVisible(True)
            s.setText("○ —")
        self._stage_uvr.setText("● 人声分离中…")
        self._bottom_panel.setVisible(True)
        self._save_geo()

        model = self._model_combo.currentText().strip()
        pitch = self._pitch_slider.value()
        reverb = self._reverb_combo.currentText()
        self._worker = PipelineWorker(
            Path(self._input_path), model, pitch, self._accomp_path, reverb
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

        song = Path(self._input_path).name
        extra = " + 伴奏" if self._accomp_path else ""
        self._log_view.append(f"▶ {song} | {model} | 音高 {pitch:+d}{extra}")

    def _tick_progress(self) -> None:
        """Smoothly animate progress bar toward target."""
        diff = self._target_progress - self._display_progress
        if abs(diff) < 0.5:
            self._display_progress = self._target_progress
            if self._target_progress >= 100:
                self._progress_timer.stop()
        else:
            self._display_progress += diff * 0.12  # ease toward target
        self._prog.setValue(int(self._display_progress))

    def _on_progress(self, state: str, pct: int, msg: str, elapsed: float = 0.0) -> None:
        self._target_progress = pct
        if not self._progress_timer.isActive():
            self._display_progress = max(self._display_progress, pct - 10)
            self._progress_timer.start()
        elapsed_str = f"⏱ {int(elapsed)}s" if elapsed > 0 else ""
        self._prog_text.setText(f"{msg}（{pct}%）{elapsed_str}")
        su = state.upper()
        if "UVR" in su or "SEPARAT" in su:
            self._stage_uvr.setText(f"● 人声分离中… {pct}% {elapsed_str}")
        elif "SVC" in su or "CONVERT" in su or "INFER" in su:
            self._stage_uvr.setText("✓ 人声分离完成")
            self._stage_svc.setText(f"● 歌声转换中… {pct}% {elapsed_str}")
            self._stage_svc.setStyleSheet(
                f"font-size:12px; color:{TEXT_SEC}; background:transparent;"
            )
        elif "MIX" in su:
            self._stage_svc.setText("✓ 歌声转换完成")
            self._stage_mix.setText(f"● 混音中… {pct}% {elapsed_str}")
            self._stage_mix.setStyleSheet(
                f"font-size:12px; color:{TEXT_SEC}; background:transparent;"
            )
        elif "EXPORT" in su:
            self._stage_mix.setText("✓ 混音完成")
        elif "DONE" in su:
            for s in (self._stage_uvr, self._stage_svc, self._stage_mix):
                s.setText(s.text().replace("●", "✓"))
                s.setStyleSheet(
                    f"font-size:12px; color:{ACCENT}; background:transparent;"
                )
        self._log_view.append(f"{pct:>3}% {msg}")

    def _on_done(self, wav: str, mp3: str) -> None:
        self._target_progress = 100
        self._display_progress = 100
        self._prog.setValue(100)
        self._progress_timer.stop()
        self._gen.setEnabled(True)
        self._gen.setText("生成翻唱")
        self._prog.setVisible(False)
        self._prog_text.setVisible(False)

        elapsed = self._worker.elapsed if self._worker else 0
        mins, secs = divmod(int(elapsed), 60)
        model = self._model_combo.currentText()
        pitch = self._pitch_slider.value()
        song = Path(self._input_path).name
        self._result_mp3 = mp3
        self._result_dir = (
            str(Path(mp3).parent) if mp3 else str(Path(wav).parent) if wav else ""
        )

        self._result_info.setText(
            f"{song}\n模型: {model}  ·  音高: {pitch:+d}\n"
            f"耗时: {mins} 分 {secs} 秒\n{self._result_dir}"
        )
        self._history.add(song, model, pitch, self._result_dir)
        self._refresh_gallery()
        self._refresh_hist_panel()
        self._refresh_status()
        self._log_view.append(f"✓ 完成，耗时 {mins} 分 {secs} 秒 — {mp3}")

        # write metadata.json for library
        try:
            folder = Path(self._result_dir).name if self._result_dir else ""
            reverb = self._reverb_combo.currentText() if hasattr(self, '_reverb_combo') else "关闭"
            LibraryScanner.write_metadata(
                folder, song, artist="", model=model, pitch=pitch, reverb=reverb
            )
        except Exception:
            pass

        self._stack.setCurrentIndex(1)

        # auto-raise window
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

        # Windows toast notification
        try:
            import subprocess
            ps_cmd = (
                f'[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]'
                f' | Out-Null; '
                f'$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('
                f'[Windows.UI.Notifications.ToastTemplateType]::ToastText02); '
                f'$texts = $template.GetElementsByTagName("text"); '
                f'$texts[0].AppendChild($template.CreateTextNode("翻唱完成！")) | Out-Null; '
                f'$texts[1].AppendChild($template.CreateTextNode("{song}")) | Out-Null; '
                f'$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("AI Cover Studio"); '
                f'$notifier.Show($template)'
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass  # notification is non-critical

    def _on_error(self, msg: str) -> None:
        self._gen.setEnabled(True)
        self._gen.setText("生成翻唱")
        self._log_view.append(f"✗ {msg}")
        # write error log
        try:
            from pathlib import Path as _P
            log_dir = _P(__file__).resolve().parents[3] / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "error.log"
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    def _play(self) -> None:
        """Play result MP3 via built-in player."""
        self._play_in_library(self._result_mp3)

    def _open_dir(self) -> None:
        if self._result_dir:
            os.startfile(self._result_dir)

    def _open_path(self, path: str) -> None:
        """Open a folder in Explorer."""
        if Path(path).exists():
            os.startfile(path)

    def _play_in_library(self, mp3_path: str) -> None:
        """Route play request through library page's QMediaPlayer."""
        if not mp3_path or not Path(mp3_path).exists():
            return
        self._switch_tab(1)
        self._library_page.play_path(mp3_path)

    def _switch_tab(self, tab_index: int) -> None:
        """Tab 0 = 翻唱(home), Tab 1 = 作品库(library at stack index 2)."""
        self._tab_gen.setChecked(tab_index == 0)
        self._tab_lib.setChecked(tab_index == 1)
        if tab_index == 0:
            self._stack.setCurrentIndex(0)  # home
        else:
            self._stack.setCurrentIndex(2)  # library
            self._library_page._refresh()
            self._bottom_panel.setVisible(False)

    def _go_home(self) -> None:
        for s in (self._stage_uvr, self._stage_svc, self._stage_mix):
            s.setVisible(False)
        self._target_progress = 0
        self._display_progress = 0
        self._prog.setValue(0)
        self._progress_timer.stop()
        self._prog.setVisible(False)
        self._prog_text.setVisible(False)
        self._bottom_panel.setVisible(False)
        self._tab_gen.setChecked(True)
        self._tab_lib.setChecked(False)
        self._stack.setCurrentIndex(0)

    # ── geometry ───────────────────────────────────

    def _geo_file(self) -> Path:
        return Path(__file__).resolve().parents[3] / "window_geo.txt"

    def _restore_geo(self) -> None:
        p = self._geo_file()
        if p.exists():
            try:
                parts = p.read_text().strip().split(",")
                if len(parts) >= 4:
                    self.setGeometry(*map(int, parts[:4]))
            except (ValueError, OSError):
                pass

    def _save_geo(self) -> None:
        g = self.geometry()
        self._geo_file().write_text(f"{g.x()},{g.y()},{g.width()},{g.height()}")

    def closeEvent(self, event) -> None:
        self._save_geo()
        super().closeEvent(event)
