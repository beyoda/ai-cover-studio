from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ServiceResult:
    success: bool
    error: str | None = None


@dataclass(slots=True)
class UVRResult(ServiceResult):
    vocal_path: Path | None = None
    instrumental_path: Path | None = None


@dataclass(slots=True)
class SVCResult(ServiceResult):
    output_path: Path | None = None


@dataclass(slots=True)
class MixResult(ServiceResult):
    wav_path: Path | None = None


@dataclass(slots=True)
class ExportResult(ServiceResult):
    output_path: Path | None = None


@dataclass(slots=True)
class JobResult(ServiceResult):
    wav_path: Path | None = None
    mp3_path: Path | None = None
