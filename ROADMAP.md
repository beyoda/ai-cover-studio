# Roadmap

## P0 - Open-source readiness

- Replace public demo assets with materials that have documented redistribution rights.
- Add verified runtime screenshots with private data removed.
- Validate a clean clone on a fresh Windows environment.
- Keep local machine paths out of committed configuration.

## P1 - Reproducibility

- Add CI for fast unit and contract tests.
- Add preflight diagnostics for ffmpeg, Git LFS, UVR, SVC, GPU/runtime, and configured voice paths.
- Make setup failures actionable without requiring knowledge of the maintainer's machine.

## P2 - Core contracts

- Expand tests around Voice Registry, MusicSource, queue lifecycle, worker execution, and notifier behavior.
- Keep agent/chat logic separate from the audio pipeline boundary.
- Document adapter changes before adding new voice-conversion frameworks.

## P3 - Responsible demos

- Provide a rights-cleared voice model or synthetic substitute.
- Provide a public-domain or self-authored input clip.
- Add a short, verified generated preview only after the source, model, and output can all be redistributed.
