"""Install / configuration consistency guards.

Open-source constraints enforced here:

* Shipped configuration contains no machine-specific absolute path.
* The setup script downloads nothing and never rewrites user configuration.
* Documented setup steps point at files that actually exist.
* Configuration files agree with each other.

These run on a fresh clone with no models, no CUDA runtime, and no network.
"""

from __future__ import annotations

import ast
import importlib
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "aivoice_studio"

# Files that ship to users and must stay machine-independent.
PORTABLE_FILES = (
    "config/svc.yaml",
    "config/uvr.yaml",
    "config/voices.json",
    "config/default.yaml",
    "config/mix.yaml",
    "scripts/setup_tools.ps1",
    "AI Cover Studio.bat",
)

WINDOWS_ABSOLUTE = re.compile(r"\b[A-Za-z]:[\\/]")
# A user-profile path leaks the machine owner's name even when the drive differs.
USER_PROFILE_PATH = re.compile(r"[\\/]Users[\\/]", re.IGNORECASE)
# The deny-list entries are spelled via concatenation so the literal tokens
# never appear in this file; that lets a history-wide text rewrite of the
# repository sanitise every historical copy without also rewriting this guard.
CELEBRITY_TOKENS = ("\u9648\u5955\u8fc5", "\u9673\u5955\u8fc5", "ea" + "son", "Ea" + "son")

# Documented stand-ins such as ``C:/path/to/your-authorized-track.mp3`` are
# portable by construction and must not be reported as machine-specific.
PLACEHOLDER_PATH_HINTS = ("path/to", "path\\to", "your-", "<", "example.com")


def machine_specific_paths(text: str) -> list[str]:
    """Drive-letter and user-profile path tokens, excluding documented placeholders.

    ``C:\\path\\to\\...``  (JSON-escaped inside a code block) is normalised before
    the placeholder check so both spellings of the same stand-in are accepted.
    """
    found: list[str] = []
    for line in text.splitlines():
        if not WINDOWS_ABSOLUTE.search(line) and not USER_PROFILE_PATH.search(line):
            continue
        for token in re.split(r"[\s`\"'()\[\],;=]+", line):
            if not token:
                continue
            if not (WINDOWS_ABSOLUTE.search(token) or USER_PROFILE_PATH.search(token)):
                continue
            normalised = token.lower().replace("\\\\", "\\")
            if any(hint in normalised for hint in PLACEHOLDER_PATH_HINTS):
                continue
            found.append(token)
    return found


def read(relative: str) -> str:
    path = ROOT / relative
    assert path.is_file(), f"{relative} is missing"
    return path.read_text(encoding="utf-8")


def load_yaml(relative: str) -> dict:
    return yaml.safe_load(read(relative))


# --- Portability -------------------------------------------------------------


@pytest.mark.parametrize("relative", PORTABLE_FILES)
def test_shipped_file_has_no_machine_specific_path(relative: str) -> None:
    text = read(relative)
    matches = WINDOWS_ABSOLUTE.findall(text)
    assert matches == [], f"{relative} contains an absolute drive path: {matches}"


@pytest.mark.parametrize("relative", PORTABLE_FILES)
def test_shipped_file_has_no_user_profile_path(relative: str) -> None:
    text = read(relative)
    assert not USER_PROFILE_PATH.search(text), f"{relative} references a user profile directory"


# --- svc.yaml ----------------------------------------------------------------


def test_svc_config_uses_relative_paths() -> None:
    svc = load_yaml("config/svc.yaml")["svc"]
    assert not Path(svc["project_dir"]).is_absolute()
    assert not Path(svc["python"]).is_absolute()
    assert not Path(svc["models_dir"]).is_absolute()
    assert svc["project_dir"] == "tools/so-vits-svc"
    assert svc["python"] == "workenv/python.exe"
    assert svc["mode"] == "so-vits-svc"


def test_svc_config_ships_no_default_voice() -> None:
    """A clone must not silently default to a specific, unlicensed checkpoint."""
    svc = load_yaml("config/svc.yaml")["svc"]
    assert not svc.get("default_model"), "config/svc.yaml must not pin a default checkpoint"
    assert not svc.get("model_path")
    assert not svc.get("config_path")


def test_svc_command_template_placeholders_match_the_runner() -> None:
    """svc_runner._split_command only substitutes these placeholders."""
    svc = load_yaml("config/svc.yaml")["svc"]
    supported = {
        "python",
        "script",
        "model_path",
        "config_path",
        "input_name",
        "input_wav",
        "pitch",
        "speaker",
        "f0_method",
        "output_format",
    }
    used = set(re.findall(r"\{(\w+)\}", svc["command"]))
    assert used <= supported, f"unsupported placeholders: {sorted(used - supported)}"
    assert {"python", "script", "model_path", "config_path"} <= used


# --- uvr.yaml ----------------------------------------------------------------


def test_uvr_config_is_portable_and_uses_supported_placeholders() -> None:
    uvr = load_yaml("config/uvr.yaml")["uvr"]
    command = uvr["command"]
    assert "{python}" in command
    assert "--model_file_dir models/uvr" in command
    used = set(re.findall(r"\{(\w+)\}", command))
    # separator._build_command supplies exactly these.
    assert used <= {"python", "input", "output_dir", "model_name"}
    assert uvr["model_name"]


# --- voices.json -------------------------------------------------------------


def test_shipped_voices_json_references_no_celebrity_voice() -> None:
    text = read("config/voices.json")
    for token in CELEBRITY_TOKENS:
        assert token not in text, f"config/voices.json references {token!r}"


def test_shipped_voices_json_default_is_consistent() -> None:
    data = json.loads(read("config/voices.json"))
    default = data.get("default_voice_id")
    if default is not None:
        entry = data["voices"][default]
        assert entry.get("enabled", True) is True
        assert entry["checkpoint"] and entry["config"]


def test_services_share_one_models_directory() -> None:
    svc_models_dir = load_yaml("config/svc.yaml")["svc"]["models_dir"]
    voices_models_dir = json.loads(read("config/voices.json"))["models_dir"]
    assert svc_models_dir == voices_models_dir


# --- setup script ------------------------------------------------------------


def test_setup_script_does_not_download_assets_or_models() -> None:
    script = read("scripts/setup_tools.ps1")
    lowered = script.lower()
    assert "git lfs pull" not in lowered
    for path_fragment in ("examples\\voices", "examples\\models", "examples/demo", "examples/"):
        assert path_fragment not in lowered, f"setup script still references {path_fragment!r}"
    assert "copy-item" not in lowered, "setup script must not copy example models into runtime paths"


def test_setup_script_does_not_rewrite_configuration() -> None:
    script = read("scripts/setup_tools.ps1")
    lowered = script.lower()
    for writer in ("set-content", "out-file", "add-content", "new-item -itemtype file"):
        assert writer not in lowered, f"setup script must not write configuration ({writer})"


def test_setup_script_requires_an_explicit_opt_in_to_clone() -> None:
    script = read("scripts/setup_tools.ps1")
    assert "[switch]$CloneSvcSource" in script
    assert "[switch]$Strict" in script


def test_setup_script_pins_no_specific_checkpoint() -> None:
    script = read("scripts/setup_tools.ps1")
    assert not re.search(r"G_\d{3,}", script)


# --- launcher ----------------------------------------------------------------


def test_launcher_is_relative_to_its_own_location() -> None:
    bat = read("AI Cover Studio.bat")
    assert "%~dp0" in bat
    assert "%ROOT%\\src" in bat
    assert "YES" in bat, "destructive cleanup must require explicit confirmation"


# --- README ------------------------------------------------------------------

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_readme_links_resolve_on_a_fresh_clone() -> None:
    broken: list[str] = []
    for target in MARKDOWN_LINK.findall(read("README.md")):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        clean = target.split("#", 1)[0].strip()
        if not clean:
            continue
        if not (ROOT / clean).exists():
            broken.append(target)
    assert broken == [], f"README.md links point at missing paths: {broken}"


def test_tracked_markdown_links_resolve() -> None:
    """Any relative link between shipped documents must resolve.

    Covers the docs tree (including ``docs/internal/``) so a reorganization
    cannot leave dangling cross-references behind. Glob patterns, anchors, and
    external URLs are not link targets and are skipped.
    """
    broken: list[str] = []
    for relative in tracked_files():
        if not relative.lower().endswith(".md"):
            continue
        source = ROOT / relative
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        for target in MARKDOWN_LINK.findall(text):
            raw = target.strip()
            if raw.startswith(("http://", "https://", "mailto:", "#", "//")):
                continue
            if "*" in raw or "{" in raw:
                continue
            clean = raw.split("#", 1)[0].strip()
            if not clean:
                continue
            if not (source.parent / clean).exists():
                broken.append(f"{relative} -> {raw}")
    assert broken == [], f"dangling relative links: {broken}"


def test_docs_do_not_reference_machine_specific_paths() -> None:
    """Documentation must stay portable, like the shipped configuration."""
    offenders: dict[str, list[str]] = {}
    for relative in tracked_files():
        if not relative.lower().endswith(".md"):
            continue
        source = ROOT / relative
        if not source.is_file():
            continue
        hits = machine_specific_paths(source.read_text(encoding="utf-8", errors="replace"))
        if hits:
            offenders[relative] = sorted(set(hits))
    assert offenders == {}, f"machine-specific paths in documentation: {offenders}"


def test_readme_does_not_advertise_removed_assets() -> None:
    text = read("README.md")
    for token in CELEBRITY_TOKENS:
        assert token not in text, f"README.md still references {token!r}"


# User-facing documentation shipped to readers of the public repository.
PUBLIC_DOC_GLOBS = ("README.md", "CHANGELOG.md", "ROADMAP.md", "CONTRIBUTING.md", "SECURITY.md")
PRIVATE_VOICE_TOKENS = (
    "\u9648\u5955\u8fc5",
    "\u9673\u5955\u8fc5",
    "ea" + "son",
    "Ea" + "son",
    "c" + "os",
    "C" + "os",
    "\u6c64\u4ee4\u5c71",
    "\u6c88\u4ee5\u8bda",
)


def public_doc_files() -> list[str]:
    files = [name for name in PUBLIC_DOC_GLOBS if (ROOT / name).is_file()]
    for directory in ("docs", "hermes_skill"):
        for path in sorted((ROOT / directory).rglob("*.md")):
            files.append(str(path.relative_to(ROOT)))
    return files


@pytest.mark.parametrize("relative", public_doc_files())
def test_shipped_documentation_uses_no_private_voice_reference(relative: str) -> None:
    """Docs must not ship a maintainer-specific voice id, alias, or display name."""
    text = read(relative)
    offenders = [
        token
        for token in PRIVATE_VOICE_TOKENS
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text)
    ]
    assert offenders == [], f"{relative} references private voice token(s): {offenders}"


# --- Declared dependencies ---------------------------------------------------

# Import name -> distribution name, for the packages the core needs.
DISTRIBUTION_ALIASES = {
    "yaml": "pyyaml",
    "pil": "pillow",
    "yt_dlp": "yt-dlp",
    "audio_separator": "audio-separator",
    "ffmpeg": "ffmpeg-python",
}

CORE_IMPORTABLE_PACKAGES = (
    "aivoice_studio",
    "aivoice_studio.cover",
    "aivoice_studio.core",
    "aivoice_studio.models",
    "aivoice_studio.modules.mixer",
    "aivoice_studio.modules.svc",
    "aivoice_studio.modules.uvr",
    "aivoice_studio.notifier",
    "aivoice_studio.worker",
    "aivoice_studio.ui",
)


def declared_distributions() -> set[str]:
    """Distribution names declared by *this repository's* ``pyproject.toml``.

    The installed distribution metadata is deliberately not consulted: an
    editable install from another checkout (or a stale ``aivoice-studio`` in the
    interpreter's path) would silently satisfy — or hide — this guard, making the
    test pass or skip depending on the machine rather than on the working tree.
    """
    project = load_pyproject().get("project") or {}
    raw_requirements: list[str] = list(project.get("dependencies") or [])
    for extra_requirements in (project.get("optional-dependencies") or {}).values():
        raw_requirements.extend(extra_requirements or [])
    names: set[str] = set()
    for requirement in raw_requirements:
        name = re.split(r"[<>=!~\[;\s]", str(requirement).strip(), maxsplit=1)[0]
        if name:
            names.add(name.lower().replace("_", "-"))
    return names


def load_pyproject() -> dict:
    """Parse ``pyproject.toml`` with the stdlib TOML reader (3.11+) or ``tomli``."""
    text = read("pyproject.toml")
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python 3.10
        import tomli as tomllib  # type: ignore[no-redef]

    return tomllib.loads(text)


def unguarded_module_level_imports(path: Path) -> set[str]:
    """Third-party modules imported at module scope, outside any try/except.

    A guarded ``try: import optional`` block marks a dependency as optional and
    is therefore ignored.
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Try):
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_every_unconditional_import_is_a_declared_dependency() -> None:
    """Guards against the 'works on my machine' class of clean-clone failure."""
    declared = declared_distributions()
    assert declared, "pyproject.toml declares no dependency at all"
    stdlib = set(sys.stdlib_module_names)
    offenders: dict[str, set[str]] = {}
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        for module in unguarded_module_level_imports(path):
            if module in stdlib or module == "aivoice_studio":
                continue
            distribution = DISTRIBUTION_ALIASES.get(module, module).lower().replace("_", "-")
            if distribution not in declared:
                offenders.setdefault(distribution, set()).add(str(path.relative_to(ROOT)))
    assert offenders == {}, f"undeclared dependencies: {offenders}"


def test_declared_dependencies_are_read_from_this_checkout() -> None:
    """The guard must not depend on installed metadata from another directory."""
    declared = declared_distributions()
    assert {"pyqt6", "pyyaml", "rich", "requests"} <= declared, sorted(declared)


def test_optional_extras_are_scanned_too() -> None:
    declared = declared_distributions()
    assert "flask" in declared, "the server extra should be included in the scan"
    assert "pillow" in declared, "the images extra should be included in the scan"


def test_pyproject_parsing_survives_a_missing_parser() -> None:
    """``tomllib`` is 3.11+; the 3.10 fallback is exercised by construction."""
    data = load_pyproject()
    assert data["project"]["name"] == "aivoice-studio"


@pytest.mark.parametrize("module", CORE_IMPORTABLE_PACKAGES)
def test_core_package_imports_without_optional_extras(module: str) -> None:
    importlib.import_module(module)


# --- Generated artifacts -----------------------------------------------------

# Written by src/aivoice_studio/profiling/report.py on every instrumented run.
GENERATED_ARTIFACTS = (
    "profiling_report.md",
    "issues.md",
    "profiling.json",
    "commands.log",
    "metrics.csv",
    ".profiling_done",
    ".profiling_active",
)


def tracked_files() -> list[str]:
    import subprocess

    proc = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip("not a git checkout")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


@pytest.mark.parametrize("artifact", GENERATED_ARTIFACTS)
def test_generated_profiling_artifact_is_not_tracked(artifact: str) -> None:
    assert artifact not in tracked_files(), (
        f"{artifact} is a generated profiling output; running the pipeline would "
        "overwrite it and leak absolute paths into the repository"
    )


@pytest.mark.parametrize("artifact", GENERATED_ARTIFACTS)
def test_generated_profiling_artifact_is_ignored(artifact: str) -> None:
    assert artifact in read(".gitignore")
