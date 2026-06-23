"""AI Cover Studio — Spotify-style dark theme."""

ACCENT = "#1ED760"
ACCENT_DIM = "#1DB954"
BG = "#121212"
BG_CARD = "#181818"
BG_SURFACE = "#1F1F1F"
BG_HOVER = "#282828"
TEXT = "#FFFFFF"
TEXT_SEC = "#B3B3B3"
TEXT_DIM = "#6A6A6A"
BORDER = "#2A2A2A"
RADIUS = 12
RADIUS_BTN = 20

GLOBAL_QSS = f"""
QMainWindow, QWidget#Main {{ background: {BG}; color: {TEXT}; font-family: "Microsoft YaHei","Segoe UI",sans-serif; }}

QWidget#TopBar {{ background: #0A0A0A; border-bottom: 1px solid #1A1A1A; padding: 8px 20px; min-height: 42px; }}

QFrame#DropArea {{
    background: {BG_CARD}; border: 2px dashed {BORDER}; border-radius: 16px;
    margin: 16px 24px; padding: 40px 20px;
}}
QFrame#DropArea:hover {{ border-color: {ACCENT}; background: {BG_SURFACE}; }}

QFrame#SongCard, QFrame#ParamCard {{
    background: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; margin: 8px 24px;
}}

QComboBox {{
    background: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 14px; color: {TEXT}; font-size: 13px;
}}
QComboBox:hover {{ border-color: #3D3D3D; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {BG_SURFACE}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT}; color: {TEXT};
}}

QSlider::groove:horizontal {{ background: {BORDER}; height: 6px; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}

QPushButton#Primary {{
    background: {ACCENT}; border: none; border-radius: {RADIUS_BTN}px;
    padding: 14px 48px; color: #06140b; font-size: 16px; font-weight: 800;
}}
QPushButton#Primary:hover {{ background: #1FDF6A; }}
QPushButton#Primary:disabled {{ background: {BORDER}; color: {TEXT_DIM}; }}

QPushButton#Secondary {{
    background: transparent; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 18px; color: {TEXT_SEC}; font-size: 13px; font-weight: 600;
}}
QPushButton#Secondary:hover {{ border-color: {ACCENT}; color: {TEXT}; }}

QPushButton#LinkBtn {{
    background: transparent; border: none; color: {TEXT_SEC}; font-size: 13px;
    text-decoration: underline; padding: 4px 8px;
}}
QPushButton#LinkBtn:hover {{ color: {TEXT}; }}

QPushButton#Mini {{
    background: {ACCENT}; border: none; border-radius: 12px;
    padding: 3px 12px; color: #06140b; font-size: 11px; font-weight: 700;
}}
QPushButton#Mini:hover {{ background: #1FDF6A; }}

QProgressBar {{ background: {BORDER}; border: none; border-radius: 4px; height: 6px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACCENT_DIM},stop:1 {ACCENT}); border-radius: 4px; }}

QFrame#HistoryCard {{ background: {BG_CARD}; border-radius: 8px; padding: 10px 14px; }}
QFrame#HistoryCard:hover {{ background: {BG_HOVER}; }}

QFrame#StatusBar {{ background: #0A0A0A; border-top: 1px solid #1A1A1A; padding: 6px 16px; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3D3D3D; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #4D4D4D; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QTextEdit {{
    background: {BG}; border: 1px solid {BORDER}; border-radius: 8px;
    color: {TEXT_SEC}; font-size: 12px; padding: 8px;
    font-family: "Cascadia Code","Consolas",monospace;
}}

QTabBar::tab {{ background: transparent; color: {TEXT_DIM}; border: none; padding: 8px 16px; font-size: 13px; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: 700; }}

QToolTip {{ background: {BG_SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px 10px; border-radius: 6px; font-size: 12px; }}
"""
