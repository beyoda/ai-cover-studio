"""UVR via audio-separator with DirectML (Windows GPU) enabled.

audio-separator CLI has no --use_directml flag; this thin wrapper turns it on.
Usage mirrors the previous CLI:
  python scripts/uvr_directml.py <input> --output_dir <dir> --model_filename <name> --model_file_dir <dir>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UVR with DirectML GPU")
    parser.add_argument("input", help="Input audio path")
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--model_filename", required=True)
    parser.add_argument("--model_file_dir", required=True)
    parser.add_argument("--output_format", default="WAV")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"input not found: {input_path}", file=sys.stderr)
        return 1

    from audio_separator.separator import Separator

    sep = Separator(
        model_file_dir=args.model_file_dir,
        output_dir=args.output_dir,
        output_format=args.output_format,
        use_directml=True,
    )
    sep.load_model(model_filename=args.model_filename)
    outputs = sep.separate(str(input_path))
    print(f"uvr_directml ok: {outputs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
