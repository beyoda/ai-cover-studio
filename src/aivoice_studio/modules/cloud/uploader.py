from pathlib import Path


class CloudUploader:
    def upload(self, file_path: Path) -> str:
        raise NotImplementedError("Cloud upload is reserved for future expansion")
