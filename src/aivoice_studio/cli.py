from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from aivoice_studio.core.context import JobContext
from aivoice_studio.factory import build_pipeline
from aivoice_studio.ui.model_config_map import ModelConfigMap
from aivoice_studio.utils.paths import resolve_path

console = Console()


def first_available_model(config: dict) -> str | None:
    """Configured default, else the first locally installed checkpoint, else ``None``.

    No checkpoint ships with this repository, so ``None`` is a legitimate answer
    on a fresh clone and the caller must report it instead of guessing a name.
    """
    svc = config.get("svc", {})
    configured = svc.get("default_model")
    if configured:
        return str(configured)
    models = ModelConfigMap(svc.get("models_dir", "models")).list_models()
    return models[0] if models else None


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Cover Studio CLI")
    parser.add_argument("input_audio", help="Input audio path")
    parser.add_argument(
        "--model",
        default=None,
        help="SVC checkpoint stem; defaults to the first model found locally",
    )
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument("--f0-method", default="rmvpe")
    parser.add_argument("--no-mp3", action="store_true")
    args = parser.parse_args()

    def progress(_state, percent: int, message: str) -> None:
        console.print(f"[{percent:>3}%] {message}")

    pipeline, config = build_pipeline(progress)
    runtime = config.get("runtime", {})

    model = args.model or first_available_model(config)
    if not model:
        console.print(
            "[red]No model available[/red] — this repository ships no checkpoint. "
            "Add one under svc.models_dir and register it in config/voices.json "
            "(see README, 'Bring Your Own Models')."
        )
        raise SystemExit(2)

    result = pipeline.run(JobContext(
        input_audio=Path(args.input_audio),
        model_name=model,
        pitch=args.pitch,
        f0_method=args.f0_method,
        workdir=resolve_path(runtime.get("workdir", "workdir")),
        output_dir=resolve_path(runtime.get("output_dir", "outputs")),
        export_mp3=not args.no_mp3,
    ))
    if result.success:
        console.print(f"[green]Done[/green] WAV: {result.wav_path} MP3: {result.mp3_path}")
    else:
        console.print(f"[red]Failed[/red] {result.error}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()
