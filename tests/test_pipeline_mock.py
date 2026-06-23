import wave
from pathlib import Path

from aivoice_studio.core.context import JobContext
from aivoice_studio.factory import build_pipeline


def _make_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\x00\x00" * 4410)


def test_pipeline_mock(tmp_path):
    audio = tmp_path / "input.wav"
    _make_wav(audio)
    pipeline, _ = build_pipeline(mock_mode=True)
    result = pipeline.run(JobContext(
        input_audio=audio,
        model_name="demo",
        workdir=tmp_path / "workdir",
        output_dir=tmp_path / "outputs",
    ))
    assert result.success
    assert result.wav_path and result.wav_path.exists()
    assert result.mp3_path and result.mp3_path.exists()
