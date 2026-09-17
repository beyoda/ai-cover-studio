# Contributing

Thanks for helping improve AIVOICE.

Useful contributions include:

- Windows portability and setup fixes;
- reproducibility documentation;
- fast unit and contract tests;
- clearer diagnostics and error messages;
- rights-cleared example assets;
- small fixes that preserve the pipeline boundaries.

Before opening a pull request:

1. Do not commit API keys, Feishu credentials, cookies, user audio, generated jobs, private paths, or sensitive logs.
2. Do not add copyrighted songs, celebrity voice models, datasets, or model weights unless redistribution rights are documented in the PR.
3. Keep voice checkpoints behind `config/voices.json` rather than hard-coding model paths in the skill or UI.
4. Explain how the change was tested. Include Windows, Python, GPU/runtime, and model details when relevant.
5. Update docs when behavior, setup, or public examples change.

For large architecture changes, open an issue first.
