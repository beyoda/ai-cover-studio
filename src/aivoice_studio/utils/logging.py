from __future__ import annotations

import logging
from pathlib import Path

from aivoice_studio.utils.paths import resolve_path


def setup_logging(log_file: str | Path = "logs/pipeline.log") -> logging.Logger:
    path = resolve_path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("aivoice_studio")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger
