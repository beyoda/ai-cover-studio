from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4


@dataclass(slots=True)
class JobContext:
    input_audio: Path
    model_name: str
    pitch: int = 0
    f0_method: str = "rmvpe"
    workdir: Path = Path("workdir")
    output_dir: Path = Path("outputs")
    export_mp3: bool = True
    accompaniment: str = ""
    reverb: str = "关闭"
    job_id: str = field(default_factory=lambda: uuid4().hex[:12])

    @property
    def job_workdir(self) -> Path:
        return self.workdir / self.job_id

    @property
    def job_output_dir(self) -> Path:
        return self.output_dir / self.job_id
