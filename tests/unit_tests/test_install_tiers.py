"""The default ("core") install must work without Manim.

Manim is only present in the 'extras' install. These tests block the manim
(and cv2) imports in a subprocess and check that the core modules import, the
static renderer still produces an image, and --animate fails with an install
hint instead of a traceback.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
BLOCK_MANIM = "import sys; sys.modules['manim'] = None; sys.modules['cv2'] = None; "


def run_python(code: str, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", BLOCK_MANIM + code],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=cwd,
    )


def run_git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    for i in range(1, 3):
        (path / f"file{i}.txt").write_text(f"content {i}\n")
        run_git(path, "add", ".")
        run_git(path, "commit", "-m", f"commit {i}")
    return path


def test_core_modules_import_without_manim():
    result = run_python(
        "import git_sim.preflight, git_sim.textgraph, git_sim.claude_hook, "
        "git_sim.simulate, git_sim.mcp_server, git_sim.render, git_sim.animations; print('ok')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_cli_version_works_without_manim():
    result = run_python("from git_sim.__main__ import app; app(['--version'])")
    assert result.returncode == 0, result.stderr
    assert "git-sim version" in result.stdout


def test_cli_renders_static_image_without_manim(repo, tmp_path):
    media = tmp_path / "media"
    code = (
        "from git_sim.__main__ import app; "
        f"app(['-d', '--output-only-path', '--img-format=png', '--media-dir', {str(media)!r}, 'log'])"
    )
    # The user's own git_sim_* settings must not leak into the render.
    env_clean = {k: v for k, v in os.environ.items() if not k.lower().startswith("git_sim_")}
    result = subprocess.run(
        [sys.executable, "-c", BLOCK_MANIM + code],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=repo,
        env=env_clean,
    )
    assert result.returncode == 0, result.stderr
    image = Path(result.stdout.strip().splitlines()[-1])
    assert image.exists() and "git-sim-log" in image.name
    assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_cli_animate_without_manim_explains_extras(repo):
    result = run_python("from git_sim.__main__ import app; app(['--animate', 'log'])", cwd=repo)
    assert result.returncode == 1
    assert 'pip install "git-sim[extras]"' in result.stderr
    assert "Traceback" not in result.stderr


def test_pyproject_tiers():
    tomllib = pytest.importorskip("tomllib")
    with PYPROJECT.open("rb") as f:
        project = tomllib.load(f)["project"]
    core = " ".join(project["dependencies"])
    optional = project["optional-dependencies"]
    assert "manim" not in core
    assert "skia-python" in core
    assert "mcp" in core
    assert "manim" in " ".join(optional["extras"])
    assert "full" not in optional
    assert project["requires-python"] == ">=3.10"
