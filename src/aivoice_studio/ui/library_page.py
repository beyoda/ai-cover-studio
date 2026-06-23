"""Library page: browse covers, built-in player, playlists."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from aivoice_studio.ui.library_scanner import CoverMeta, LibraryScanner
from aivoice_studio.ui.theme import ACCENT, BG, BG_CARD, BG_SURFACE, BORDER, TEXT, TEXT_DIM, TEXT_SEC
from aivoice_studio.utils.paths import project_root

PLAYLIST_DIR = project_root() / "playlists"


def _label(text: str, size: int = 13, color: str = TEXT, bold: bool = False) -> QLabel:
    weight = "bold" if bold else "normal"
    label = QLabel(text)
    label.setStyleSheet(
        f"font-size:{size}px; font-weight:{weight}; color:{color}; background:transparent;"
    )
    return label


class LibraryPage(QWidget):
    """Full library page with search, list, player bar, and playlist sidebar."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{BG};")
        self._scanner = LibraryScanner()
        self._covers: list[CoverMeta] = []
        self._playlists: dict[str, list[str]] = {}

        # player
        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(0.8)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state_change)
        self._current_cover: CoverMeta | None = None

        self._build()
        self._load_playlists()
        self._refresh()

    # ── build ──────────────────────────────────────────

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── left: playlist sidebar ──
        sidebar = QWidget()
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet(f"background:{BG_CARD}; border-right:1px solid {BORDER};")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(12, 12, 12, 12)
        sl.setSpacing(8)
        sl.addWidget(_label("歌单", 14, TEXT, bold=True))

        self._pl_list = QListWidget()
        self._pl_list.setStyleSheet(
            f"QListWidget{{background:{BG};border:1px solid {BORDER};border-radius:6px;"
            f"color:{TEXT_SEC};font-size:12px;}}"
            f"QListWidget::item:selected{{background:{ACCENT};color:#06140b;}}"
        )
        self._pl_list.itemClicked.connect(self._on_playlist_clicked)
        sl.addWidget(self._pl_list, stretch=1)

        pl_btns = QHBoxLayout()
        add_pl = QPushButton("+")
        add_pl.setStyleSheet(
            f"QPushButton{{background:{ACCENT};border:none;border-radius:4px;"
            f"padding:4px 10px;color:#06140b;font-weight:700;}}"
        )
        add_pl.clicked.connect(self._create_playlist)
        del_pl = QPushButton("−")
        del_pl.setStyleSheet(
            f"QPushButton{{background:transparent;border:1px solid {BORDER};"
            f"border-radius:4px;padding:4px 10px;color:{TEXT_DIM};}}"
        )
        del_pl.clicked.connect(self._delete_playlist)
        pl_btns.addWidget(add_pl)
        pl_btns.addWidget(del_pl)
        sl.addLayout(pl_btns)
        root.addWidget(sidebar)

        # ── right side: content + player bar ──
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # content
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索歌曲名…")
        self._search.setStyleSheet(
            "QLineEdit{background:#1A1A1A;border:1px solid #2A2A2A;border-radius:8px;"
            "padding:8px 12px;color:#E8E8E8;font-size:13px;}"
            "QLineEdit:focus{border-color:#1ED760;}"
        )
        self._search.textChanged.connect(self._refresh)
        top_row.addWidget(self._search, stretch=2)

        self._filter_model = QComboBox()
        self._filter_model.setStyleSheet(
            f"QComboBox{{background:{BG_SURFACE};border:1px solid {BORDER};"
            f"border-radius:6px;padding:6px 10px;color:{TEXT};font-size:12px;}}"
        )
        self._filter_model.addItem("全部模型")
        self._filter_model.currentTextChanged.connect(self._refresh)
        top_row.addWidget(self._filter_model)

        self._sort_combo = QComboBox()
        self._sort_combo.setStyleSheet(self._filter_model.styleSheet())
        self._sort_combo.addItems(["最新", "歌名 A-Z"])
        self._sort_combo.currentTextChanged.connect(self._refresh)
        top_row.addWidget(self._sort_combo)
        cl.addLayout(top_row)

        count_row = QHBoxLayout()
        self._count_label = _label("", 12, TEXT_DIM)
        count_row.addWidget(self._count_label)
        count_row.addStretch()
        cl.addLayout(count_row)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{BG};border:1px solid {BORDER};border-radius:8px;"
            f"color:{TEXT};font-size:13px;}}"
            f"QListWidget::item{{padding:8px;border-bottom:1px solid {BORDER};}}"
            f"QListWidget::item:selected{{background:{ACCENT};color:#06140b;}}"
            f"QListWidget::item:hover{{background:{BG_CARD};}}"
        )
        self._list.itemDoubleClicked.connect(self._play_cover)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)
        cl.addWidget(self._list, stretch=1)

        rl.addWidget(content, stretch=1)

        # player bar
        self._player_bar = self._build_player_bar()
        self._player_bar.setVisible(False)
        rl.addWidget(self._player_bar)

        root.addWidget(right, stretch=1)

    def _build_player_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("PlayerBar")
        bar.setStyleSheet(f"QFrame#PlayerBar{{background:{BG_CARD};border-top:1px solid {BORDER};padding:8px 16px;}}")
        bar.setFixedHeight(64)

        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.setStyleSheet(
            f"QPushButton{{background:{ACCENT};border:none;border-radius:18px;"
            f"color:#06140b;font-size:16px;font-weight:700;}}"
        )
        self._play_btn.clicked.connect(self._toggle_play)
        row.addWidget(self._play_btn)

        self._now_playing = _label("未播放", 12, TEXT_SEC)
        self._now_playing.setFixedWidth(200)
        row.addWidget(self._now_playing)

        self._pos_slider = QSlider(Qt.Orientation.Horizontal)
        self._pos_slider.setRange(0, 1000)
        self._pos_slider.setValue(0)
        self._pos_slider.sliderMoved.connect(self._seek)
        row.addWidget(self._pos_slider, stretch=1)

        self._time_label = _label("0:00 / 0:00", 11, TEXT_DIM)
        self._time_label.setFixedWidth(80)
        row.addWidget(self._time_label)

        vol_icon = _label("🔊", 14, TEXT_DIM)
        row.addWidget(vol_icon)
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(80)
        self._vol_slider.setFixedWidth(80)
        self._vol_slider.valueChanged.connect(lambda v: self._audio.setVolume(v / 100))
        row.addWidget(self._vol_slider)
        return bar

    # ── data ─────────────────────────────────────────

    def _refresh(self, _=None) -> None:
        self._covers = self._scanner.scan()

        # populate model filter
        models = sorted(set(c.model for c in self._covers if c.model))
        current = self._filter_model.currentText()
        self._filter_model.blockSignals(True)
        self._filter_model.clear()
        self._filter_model.addItem("全部模型")
        self._filter_model.addItems(models)
        idx = self._filter_model.findText(current)
        self._filter_model.setCurrentIndex(idx if idx >= 0 else 0)
        self._filter_model.blockSignals(False)

        # filter
        query = self._search.text().strip().lower()
        model_filter = self._filter_model.currentText()
        filtered = self._covers
        if query:
            filtered = [c for c in filtered if query in c.song.lower()]
        if model_filter != "全部模型":
            filtered = [c for c in filtered if c.model == model_filter]

        # sort
        if self._sort_combo.currentText() == "歌名 A-Z":
            filtered = sorted(filtered, key=lambda c: c.song.lower())

        self._count_label.setText(f"共 {len(filtered)} 首")
        self._list.clear()
        for c in filtered:
            song = c.song if c.song != c.folder else (
                c.song + ("…" if len(c.song) > 12 else "")
            )
            model = c.model or "—"
            text = f"{song}  ·  {model}  ·  音高{c.pitch:+d}"
            if c.created:
                text += f"  ·  {c.created[:10]}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, c.folder)
            item.setToolTip("双击播放  ·  右键添加到歌单")
            self._list.addItem(item)

    # ── player ───────────────────────────────────────

    def play_path(self, mp3_path: str) -> None:
        """Play an MP3 file directly (called from main window)."""
        from pathlib import Path as _P
        p = _P(mp3_path)
        if not p.exists():
            return
        self._current_cover = None
        self._player.setSource(QUrl.fromLocalFile(str(p)))
        self._player.play()
        self._player_bar.setVisible(True)
        self._now_playing.setText(p.stem[:25])
        self._play_btn.setText("⏸")

    def _play_cover(self, item: QListWidgetItem) -> None:
        folder = item.data(Qt.ItemDataRole.UserRole)
        cover = next((c for c in self._covers if c.folder == folder), None)
        if not cover or not cover.mp3_path.exists():
            return

        self._current_cover = cover
        self._player.setSource(QUrl.fromLocalFile(str(cover.mp3_path)))
        self._player.play()
        self._player_bar.setVisible(True)
        self._now_playing.setText(cover.song[:25])
        self._play_btn.setText("⏸")

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._play_btn.setText("▶")
        else:
            if self._player.source().isEmpty() and self._current_cover:
                self._player.setSource(QUrl.fromLocalFile(str(self._current_cover.mp3_path)))
            self._player.play()
            self._play_btn.setText("⏸")

    def _seek(self, pos: int) -> None:
        dur = self._player.duration()
        if dur > 0:
            self._player.setPosition(int(dur * pos / 1000))

    def _on_position(self, pos: int) -> None:
        dur = self._player.duration()
        if dur > 0:
            slider_pos = int(pos * 1000 / dur)
            self._pos_slider.blockSignals(True)
            self._pos_slider.setValue(slider_pos)
            self._pos_slider.blockSignals(False)
            pm, ps = divmod(pos // 1000, 60)
            dm, ds = divmod(dur // 1000, 60)
            self._time_label.setText(f"{pm}:{ps:02d} / {dm}:{ds:02d}")

    def _on_duration(self, _dur: int) -> None:
        pass

    def _on_state_change(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._play_btn.setText("▶")
            self._pos_slider.setValue(0)

    # ── playlists ────────────────────────────────────

    def _load_playlists(self) -> None:
        PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
        self._playlists = {}
        for f in PLAYLIST_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._playlists[f.stem] = data.get("covers", [])
            except (json.JSONDecodeError, KeyError):
                pass
        self._refresh_pl_list()

    def _refresh_pl_list(self) -> None:
        self._pl_list.clear()
        self._pl_list.addItem("📂 全部作品")
        for name in sorted(self._playlists):
            self._pl_list.addItem(f"♫ {name}")

    def _on_playlist_clicked(self, item: QListWidgetItem) -> None:
        text = item.text()
        if text == "📂 全部作品":
            self._refresh()
            return
        pl_name = text[2:]  # remove "♫ "
        folders = self._playlists.get(pl_name, [])
        self._list.clear()
        covers = [c for c in self._covers if c.folder in folders]
        if not covers:
            # folders might not be in current scan
            self._refresh()
            covers = [c for c in self._covers if c.folder in folders]
        for c in covers:
            item_w = QListWidgetItem(
                f"{c.song}  ·  {c.model}  ·  音高{c.pitch:+d}"
            )
            item_w.setData(Qt.ItemDataRole.UserRole, c.folder)
            self._list.addItem(item_w)
        self._count_label.setText(f"歌单「{pl_name}」· {len(covers)} 首")

    def _create_playlist(self) -> None:
        name, ok = QInputDialog.getText(self, "新建歌单", "歌单名称：")
        if ok and name.strip():
            name = name.strip()
            self._playlists[name] = []
            self._save_playlist(name)
            self._refresh_pl_list()

    def _delete_playlist(self) -> None:
        item = self._pl_list.currentItem()
        if not item:
            return
        text = item.text()
        if text == "📂 全部作品":
            return
        pl_name = text[2:]
        f = PLAYLIST_DIR / f"{pl_name}.json"
        if f.exists():
            f.unlink()
        self._playlists.pop(pl_name, None)
        self._refresh_pl_list()

    def _context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        folder = item.data(Qt.ItemDataRole.UserRole)
        cover = next((c for c in self._covers if c.folder == folder), None)
        if not cover:
            return

        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{BG_CARD};color:{TEXT};border:1px solid {BORDER};}}"
            f"QMenu::item:selected{{background:{ACCENT};}}"
        )

        export_action = menu.addAction("📦 导出这首")
        export_action.triggered.connect(lambda: self._export_single(cover))

        menu.addSeparator()

        if self._playlists:
            for pl_name in sorted(self._playlists):
                action = menu.addAction(f"添加到「{pl_name}」")
                action.triggered.connect(
                    lambda checked, n=pl_name, f=folder: self._add_to_playlist(n, f)
                )
        menu.exec(self._list.mapToGlobal(pos))

    def _add_to_playlist(self, pl_name: str, folder: str) -> None:
        if folder not in self._playlists[pl_name]:
            self._playlists[pl_name].append(folder)
            self._save_playlist(pl_name)

    def _save_playlist(self, name: str) -> None:
        PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
        data = {"name": name, "covers": self._playlists.get(name, [])}
        (PLAYLIST_DIR / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _export_single(self, cover: CoverMeta) -> None:
        """Export a single cover with auto cover art."""
        import shutil

        from aivoice_studio.ui.cover_fetcher import fetch_cover

        # pick output dir
        from PyQt6.QtWidgets import QFileDialog
        out_dir = QFileDialog.getExistingDirectory(self, "选择导出位置")
        if not out_dir:
            return

        song = cover.song or cover.folder
        safe_name = song
        for ch in r'<>:"/\|?*':
            safe_name = safe_name.replace(ch, "_")

        pkg_dir = Path(out_dir) / safe_name
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # copy mp3
        if cover.mp3_path.exists():
            shutil.copy2(cover.mp3_path, pkg_dir / f"{safe_name}.mp3")

        # auto fetch cover
        cover_img = fetch_cover(song, cover.artist, output_dir=pkg_dir)
        if cover_img and cover_img.parent != pkg_dir:
            shutil.copy2(cover_img, pkg_dir / "cover.jpg")

        # info
        import time
        lines = [
            f"歌曲: {song}",
            f"模型: {cover.model}",
            f"音高: {cover.pitch:+d}",
            f"混响: {cover.reverb}",
            f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "由 AI Cover Studio 生成",
        ]
        (pkg_dir / "info.txt").write_text("\n".join(lines), encoding="utf-8")

        import os
        os.startfile(str(pkg_dir))
