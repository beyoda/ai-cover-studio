from dataclasses import dataclass


@dataclass(slots=True)
class UVRConfig:
    command: str
    model_name: str
    vocal_glob: str = "*Vocals*.wav"
    instrumental_glob: str = "*Instrumental*.wav"
    mock_mode: bool = True
