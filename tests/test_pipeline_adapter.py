"""Contract tests for PipelineAdapter (no GUI dependency)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aivoice_studio.cover.adapter.pipeline_adapter import PipelineAdapter
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.stage import Stage
from aivoice_studio.core.context import JobContext as PipelineJobContext
from aivoice_studio.core.state import JobState
from aivoice_studio.models.results import JobResult


def _request(**overrides) -> CoverRequest:
    base = dict(
        input_audio=r"D:\songs\demo.mp3",
        model_name="G_16000",
        pitch=2,
        reverb="录音棚",
        f0_method="rmvpe",
        export_mp3=True,
        accompaniment=r"D:\songs\inst.wav",
        workdir=r"D:\demo\workdir",
        output_dir=r"D:\demo\outputs",
        client="test",
    )
    base.update(overrides)
    return CoverRequest(**base)


def _fake_build(pipeline, config=None):
    def _builder(callback=None, mock_mode=None):
        return pipeline, config or {
            "runtime": {"workdir": "workdir", "output_dir": "outputs"},
            "pipeline": {"export_mp3": True},
            "svc": {"f0_method": "rmvpe"},
        }

    return _builder


class TestCoverRequestToJobContextMapping:
    def test_maps_all_fields_onto_pipeline_job_context(self):
        captured: dict = {}
        pipeline = MagicMock()
        pipeline.run.side_effect = lambda job: (
            captured.setdefault("job", job),
            JobResult(success=True, wav_path=Path("a.wav"), mp3_path=Path("a.mp3")),
        )[1]

        adapter = PipelineAdapter()
        req = _request()
        with patch(
            "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
            side_effect=_fake_build(pipeline),
        ):
            adapter.run(req, job_id="abc123def456")

        job: PipelineJobContext = captured["job"]
        assert isinstance(job, PipelineJobContext)
        assert job.input_audio == Path(req.input_audio)
        assert job.model_name == "G_16000"
        assert job.pitch == 2
        assert job.reverb == "录音棚"
        assert job.f0_method == "rmvpe"
        assert job.export_mp3 is True
        assert job.accompaniment == req.accompaniment
        assert job.job_id == "abc123def456"
        assert job.workdir == Path(req.workdir)
        assert job.output_dir == Path(req.output_dir)

    def test_defaults_workdir_output_from_runtime_config(self):
        captured: dict = {}
        pipeline = MagicMock()
        pipeline.run.side_effect = lambda job: (
            captured.setdefault("job", job),
            JobResult(success=True),
        )[1]

        adapter = PipelineAdapter()
        req = _request(workdir=None, output_dir=None)
        config = {
            "runtime": {
                "workdir": r"D:\demo\workdir",
                "output_dir": r"D:\demo\outputs",
            }
        }
        with patch(
            "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
            side_effect=_fake_build(pipeline, config),
        ):
            adapter.run(req, job_id="jid000000001")

        job: PipelineJobContext = captured["job"]
        assert job.workdir == Path(r"D:\demo\workdir")
        assert job.output_dir == Path(r"D:\demo\outputs")


class TestJobResultToCoverResultMapping:
    def test_success_paths_mapped(self):
        pipeline = MagicMock()
        pipeline.run.return_value = JobResult(
            success=True,
            wav_path=Path(r"D:\out\cover.wav"),
            mp3_path=Path(r"D:\out\cover.mp3"),
        )
        adapter = PipelineAdapter()
        req = _request()
        with patch(
            "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
            side_effect=_fake_build(pipeline),
        ):
            result = adapter.run(req, job_id="jobsuccess01")

        assert result.success is True
        assert result.job_id == "jobsuccess01"
        assert result.wav_path == r"D:\out\cover.wav"
        assert result.mp3_path == r"D:\out\cover.mp3"
        assert result.error is None
        assert result.model_name == req.model_name
        assert result.pitch == req.pitch
        assert result.reverb == req.reverb

    def test_failure_result_mapped_without_raising(self):
        pipeline = MagicMock()
        pipeline.run.return_value = JobResult(success=False, error="UVR failed")
        adapter = PipelineAdapter()
        with patch(
            "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
            side_effect=_fake_build(pipeline),
        ):
            result = adapter.run(_request(), job_id="jobfail00001")

        assert result.success is False
        assert result.error == "UVR failed"
        assert result.wav_path is None
        assert result.mp3_path is None


class TestFailurePassthrough:
    @pytest.mark.parametrize(
        "error_message",
        [
            "UVR failed",
            "SVC failed",
            "MP3 export failed",
        ],
    )
    def test_pipeline_stage_failures_surface_in_cover_result(self, error_message: str):
        pipeline = MagicMock()
        pipeline.run.return_value = JobResult(success=False, error=error_message)
        adapter = PipelineAdapter()
        with patch(
            "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
            side_effect=_fake_build(pipeline),
        ):
            result = adapter.run(_request(), job_id="failstage001")

        assert result.success is False
        assert result.error == error_message

    def test_unexpected_exception_from_pipeline_run_is_not_swallowed(self):
        pipeline = MagicMock()
        pipeline.run.side_effect = RuntimeError("boom from pipeline")
        adapter = PipelineAdapter()
        with patch(
            "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
            side_effect=_fake_build(pipeline),
        ):
            with pytest.raises(RuntimeError, match="boom from pipeline"):
                adapter.run(_request(), job_id="raise0000001")


class TestProgressCallbackPassthrough:
    def test_job_manager_callback_becomes_progress_events(self):
        events = []

        def fake_build(callback=None, mock_mode=None):
            pipeline = MagicMock()

            def _run(job):
                assert callback is not None
                callback(JobState.UVR, 10, "Separating")
                callback(JobState.SVC, 45, "Infer")
                callback(JobState.FAILED, 100, "SVC failed")
                return JobResult(success=False, error="SVC failed")

            pipeline.run.side_effect = _run
            return pipeline, {"runtime": {"workdir": "workdir", "output_dir": "outputs"}}

        adapter = PipelineAdapter()
        with patch(
            "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
            side_effect=fake_build,
        ):
            adapter.run(
                _request(),
                job_id="prog00000001",
                on_progress=events.append,
            )

        assert [e.stage for e in events] == [Stage.UVR, Stage.SVC, Stage.FAILED]
        assert [e.percent for e in events] == [10, 45, 100]
        assert events[0].job_id == "prog00000001"
        assert events[0].message == "Separating"
        assert events[1].message == "Infer"
        assert all(e.elapsed_s is not None and e.elapsed_s >= 0 for e in events)
