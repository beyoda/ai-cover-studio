import sys

from PyQt6.QtWidgets import QApplication

from aivoice_studio.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AI Cover Studio")
    window = MainWindow()
    window.resize(980, 680)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
