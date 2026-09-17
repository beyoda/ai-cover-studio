# Python Protocol 契约（文本，本阶段不落业务代码）

> 实现阶段建议路径：`src/aivoice_studio/cover/`  
> 本文件是接口规格，**不是**可导入实现。

---

## Mapping: CoverRequest → JobContext

| CoverRequest | JobContext | Notes |
|--------------|------------|-------|
| `input_audio` | `input_audio: Path` | Must exist |
| `model_name` | `model_name` | |
| `pitch` | `pitch` | |
| `reverb` | `reverb` | |
| `f0_method` | `f0_method` | |
| `export_mp3` | `export_mp3` | |
| `accompaniment` | `accompaniment` | |
| `workdir` or config | `workdir` | `resolve_path` |
| `output_dir` or config | `output_dir` | `resolve_path` |
| (service) | `job_id` | Prefer Service-generated id aligned with output folder name |

`client` / `request_id` stay on CoverJob only — **not** passed into Pipeline.

---

## Mapping: JobResult → CoverResult

| JobResult | CoverResult |
|-----------|-------------|
| `success` | `success` |
| `wav_path` | `wav_path` (str or null) |
| `mp3_path` | `mp3_path` (str or null) |
| `error` | `error` |
| — | `job_id` from Service |
| — | echo `model_name` / `pitch` / `reverb` from request |

---

## Mapping: JobState → CoverProgressEvent.stage

Use `JobState.value` unchanged:  
`pending` | `uvr` | `svc` | `mixing` | `exporting` | `done` | `failed`

---

## Protocols (sketch)

```python
from typing import Callable, Protocol
from typing_extensions import TypedDict  # or typing.TypedDict on 3.12


class CoverRequestDict(TypedDict, total=False):
    input_audio: str
    model_name: str
    pitch: int
    reverb: str
    f0_method: str
    export_mp3: bool
    accompaniment: str
    workdir: str | None
    output_dir: str | None
    client: str
    request_id: str | None


class CoverResultDict(TypedDict, total=False):
    success: bool
    job_id: str
    wav_path: str | None
    mp3_path: str | None
    error: str | None
    model_name: str | None
    pitch: int | None
    reverb: str | None
    stages_timing: dict[str, float] | None


ProgressCallback = Callable[[str, int, str, float | None], None]
# (stage, percent, message, elapsed_s)


class PipelineAdapter(Protocol):
    """Only component allowed to call factory.build_pipeline / Pipeline.run."""

    def run(
        self,
        request: CoverRequestDict,
        *,
        job_id: str,
        on_progress: ProgressCallback | None = None,
    ) -> CoverResultDict: ...


class CoverService(Protocol):
    """Job orchestration for Hermes and future non-GUI clients."""

    def health(self) -> dict: ...

    def list_models(self) -> list[str]: ...

    def run_sync(self, request: CoverRequestDict) -> CoverResultDict: ...

    def create_job(self, request: CoverRequestDict) -> str: ...

    def get_job(self, job_id: str) -> dict: ...
```

---

## Dependency rule

```
cover.skill        → HTTP client only
cover.service      → cover.adapter (+ optional workers)
cover.adapter      → aivoice_studio.factory / core.context / models.results
ui / cli / server  → factory (unchanged; must NOT be forced through cover.service in phase 1)
```

Forbidden:

- `cover.skill` → `factory` / `Pipeline`
- `cover.service` → `modules.uvr.separator` (bypass adapter)
- Editing `core/pipeline.py` to know about Cover Skill

---

## GUI coexistence

```
GUI PipelineWorker.run:
    build_pipeline(cb)
    pipeline.run(JobContext(...))   # UNCHANGED

Hermes:
    POST /v1/cover/run
      → CoverService.run_sync
        → PipelineAdapter.run
          → build_pipeline(cb)
          → pipeline.run(JobContext(...))  # SAME pipeline
```

Both paths share one Pipeline implementation; they do not share one process or one job queue in phase 1.
