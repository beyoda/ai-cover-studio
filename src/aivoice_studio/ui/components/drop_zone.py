"""Compact drag-and-drop zone with inline browse."""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from aivoice_studio.ui.theme import ACCENT, BG_CARD, BORDER, RADIUS, TEXT_MUTED, TEXT_SECONDARY


class DropZone(QWidget):
    file_selected = pyqtSignal(str)

    AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma"}

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)

        icon = QLabel("♫")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"font-size: 36px; color: {ACCENT}; background: transparent;")

        self.label = QLabel("Drop audio file here")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {TEXT_SECONDARY}; background: transparent;"
        )

        self.hint = QLabel("or")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet(f"font-size: 13px; color: {TEXT_MUTED}; background: transparent;")

        self.browse_btn = QPushButton("Browse Files")
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {ACCENT}; border: 1px solid {ACCENT}; "
            f"border-radius: 6px; padding: 6px 16px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {ACCENT}; color: #06140b; }}"
        )
        self.browse_btn.clicked.connect(self._browse)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.addWidget(self.browse_btn)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)
        layout.addWidget(icon)
        layout.addWidget(self.label)
        layout.addWidget(self.hint)
        layout.addSpacing(4)
        layout.addLayout(btn_row)

        self._apply_style(False)

    def _apply_style(self, hover: bool) -> None:
        bc = ACCENT if hover else BORDER
        self.setStyleSheet(
            f"DropZone {{ background: {BG_CARD}; border: 2px dashed {bc}; border-radius: {RADIUS}px; }}"
        )

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        if event and event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in self.AUDIO_EXTS:
                    event.acceptProposedAction()
                    self._apply_style(True)
                    return
        if event:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: ANN001
        self._apply_style(False)

    def dropEvent(self, event: QDropEvent | None) -> None:
        self._apply_style(False)
        if event and event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if Path(p).suffix.lower() in self.AUDIO_EXTS:
                    self.file_selected.emit(p)
                    return

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Audio File", "",
            "Audio Files (*.mp3 *.wav *.flac *.m4a *.ogg);;All Files (*.*)",
        )
        if path:
            self.file_selected.emit(path)
