from pathlib import Path


class Downloader:
    def download(self, url: str, output_dir: Path) -> Path:
        raise NotImplementedError("Download module is reserved for plugin expansion")
