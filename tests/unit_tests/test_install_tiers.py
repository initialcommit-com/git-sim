"""The default ("core") install must work without Manim.

Manim is only present in the 'full' extra. These tests block the manim (and
cv2) imports in a subprocess and check that the core modules import, the CLI
fails with an install hint instead of a traceback, and the render bridge
reports the missing renderer instead of spawning a doomed process.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from git_sim import simulate

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

BLOCK_RENDERER = "import sys; sys.modules['manim'] = None; sys.modules['cv2'] = None; "


def run_python(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", BLOCK_RENDERER + code],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_core_modules_import_without_manim():
    result = run_python(
        "import git_sim.preflight, git_sim.textgraph, git_sim.claude_hook, "
        "git_sim.simulate, git_sim.mcp_server; print('ok')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_cli_version_works_without_manim():
    result = run_python("from git_sim.__main__ import app; app(['--version'])")
    assert result.returncode == 0, result.stderr
    assert "git-sim version" in result.stdout


def test_cli_render_command_explains_full_install_without_manim():
    result = run_python("from git_sim.__main__ import app; app(['log'])")
    assert result.returncode == 1
    assert 'pip install "git-sim[full]"' in result.stderr
    assert "Traceback" not in result.stderr


def test_render_simulation_reports_missing_renderer(monkeypatch):
    monkeypatch.setattr(simulate, "_renderer_available", lambda: False)

    def must_not_spawn(*args, **kwargs):
        raise AssertionError("render must not be attempted without the renderer")

    monkeypatch.setattr(simulate, "_run_git_sim", must_not_spawn)
    result = simulate.render_simulation("git reset --hard HEAD~1", ".")
    assert result["image_path"] is None
    assert "git-sim[full]" in result["render_note"]


def test_pyproject_tiers():
    tomllib = pytest.importorskip("tomllib")
    with PYPROJECT.open("rb") as f:
        project = tomllib.load(f)["project"]
    core = " ".join(project["dependencies"])
    full = " ".join(project["optional-dependencies"]["full"])
    assert "manim" not in core
    assert "mcp" in core
    assert "manim" in full
    assert project["requires-python"] == ">=3.10"
