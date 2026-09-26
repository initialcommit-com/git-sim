"""The embeddable viewer script and the plain SVG output it embeds."""

import os
import subprocess
import sys

import pytest

from git_sim.render.embed import build_embed_js


def run_git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-q", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    for i in range(1, 4):
        (path / f"file{i}.txt").write_text(f"content {i}\n")
        run_git(path, "add", ".")
        run_git(path, "commit", "-q", "-m", f"commit {i}")
    run_git(path, "branch", "feature", "HEAD~1")
    return path


def test_embed_script_carries_the_viewer_and_mounts_by_class():
    js = build_embed_js()
    assert "window.GitSimEmbed" in js and ".git-sim[data-src]" in js
    # the viewer's stylesheet, header and script travel inside, as JSON strings
    assert "#bar{position:sticky" in js and 'id=\\"toBefore\\"' in js
    assert "function makeViewer(root){" in js and "window.GitSimViewer = Object.assign(makeViewer(document)" in js
    assert "__CSS__" not in js and "__VIEWER__" not in js and "__HEADER__" not in js
    # a saved page is fetched into the frame's document; an svg is fetched by the host and posted in
    assert "iframe.srcdoc = html" in js and "gitSimEmbedGraph" in js


def test_cli_writes_a_plain_svg_for_embedding(repo, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.lower().startswith("git_sim_")}
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "git_sim",
            "-d",
            "--media-dir",
            str(tmp_path / "m"),
            "--img-format",
            "svg",
            "--output-only-path",
            "commit",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout
    path = out.strip().splitlines()[-1]
    assert path.endswith(".svg") and os.path.exists(path)
    text = open(path, encoding="utf-8").read()
    assert text.startswith("<svg") and 'data-phase="after"' in text
    assert "<html" not in text
