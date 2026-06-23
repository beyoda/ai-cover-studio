from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from aivoice_studio.core.context import JobContext
from aivoice_studio.factory import build_pipeline
from aivoice_studio.utils.paths import resolve_path

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Cover Studio CLI")
    parser.add_argument("input_audio", help="Input audio path")
    parser.add_argument("--model", default="demo", help="SVC model name")
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument("--f0-method", default="rmvpe")
    parser.add_argument("--no-mp3", action="store_true")
    args = parser.parse_args()

    def progress(_state, percent: int, message: str) -> None:
        console.print(f"[{percent:>3}%] {message}")

    pipeline, config = build_pipeline(progress)
    runtime = config.get("runtime", {})
    result = pipeline.run(JobContext(
        input_audio=Path(args.input_audio),
        model_name=args.model,
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
