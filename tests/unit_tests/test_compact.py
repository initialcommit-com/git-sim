"""--compact: the drawing for a small space (a cheat sheet card, a thumbnail).
No title, no commit messages under the discs, no notes stacked above the
graph, a file table only as big as its rows, and no commit row at all for a
command that only moves files."""

import os
import re
import subprocess

import pytest

from git_sim.settings import Settings, settings
from git_sim.theme import theme_for


def run_git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Five commits on main, a feature branch with a commit of its own, a
    staged edit, cwd inside the repo."""
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    for i in range(1, 6):
        (path / f"file{i}.txt").write_text(f"content {i}\n")
        run_git(path, "add", ".")
        run_git(path, "commit", "-m", f"commit {i}")
    run_git(path, "checkout", "-q", "-b", "feature", "HEAD~2")
    (path / "extra.txt").write_text("extra\n")
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "feature work")
    run_git(path, "checkout", "-q", "main")
    (path / "file1.txt").write_text("staged edit\n")
    run_git(path, "add", "file1.txt")
    for key, value in Settings().model_dump().items():
        setattr(settings, key, value)
    settings.auto_open = False
    monkeypatch.chdir(path)
    yield path
    settings.compact = False


def draw(make, compact):
    settings.compact = compact
    scene = make()
    scene.construct()
    return scene.render_svg(background=theme_for(settings.light).bg, extra_mobjects=scene.removed_mobjects)


def roles(svg, role):
    return re.findall(rf'<[a-z]+ [^>]*data-role="{role}"[^>]*>', svg)


def texts(svg):
    return re.findall(r"<text [^>]*>([^<]*)</text>", svg)


def legibility(svg):
    """How big a file name is next to the whole drawing: its font size over
    the view box's width. Shown at a fixed width, that is how big it reads."""
    size = float(re.search(r'<text [^>]*font-size="([\d.]+)"[^>]*data-role="file"', svg).group(1))
    return size / float(re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+)', svg).group(1))


def test_a_files_only_command_drawn_compact_is_just_its_files(repo):
    from git_sim.restore import Restore

    full = draw(lambda: Restore(files=["file1.txt"], staged=True), compact=False)
    small = draw(lambda: Restore(files=["file1.txt"], staged=True), compact=True)
    assert roles(full, "commit") and roles(full, "title")
    assert not roles(small, "commit") and not roles(small, "title")
    # the table is still there, with the file moving back to the working directory
    assert any('data-name="file1.txt"' in f for f in roles(small, "file"))
    assert "Staging area" in texts(small) and "Working directory" in texts(small)
    assert legibility(small) > 1.5 * legibility(full)


def test_compact_keeps_the_commits_a_command_moves_but_not_their_messages(repo):
    from git_sim.reset import Reset
    from git_sim.enums import ResetMode

    make = lambda: Reset(commit="HEAD~2", mode=ResetMode.DEFAULT, soft=False, mixed=False, hard=True)  # noqa: E731
    full, small = draw(make, compact=False), draw(make, compact=True)
    assert len(roles(small, "commit")) == len(roles(full, "commit"))
    assert "commit 5" in texts(full) and "commit 5" not in texts(small)
    # hovering still tells the message: it stays in the disc's data
    assert any('data-message="commit 5"' in c for c in roles(small, "commit"))
    assert roles(full, "title") and not roles(small, "title")
    assert legibility(small) > 1.5 * legibility(full)


def test_compact_leaves_out_a_table_with_no_files(repo):
    from git_sim.reset import Reset
    from git_sim.enums import ResetMode

    # a clean tree, reset back two commits by mistake: going forward again to
    # HEAD@{1} restores commits and moves no files
    run_git(repo, "reset", "-q", "--hard", "HEAD~2")
    make = lambda: Reset(commit="HEAD@{1}", mode=ResetMode.DEFAULT, soft=False, mixed=False, hard=True)  # noqa: E731
    full, small = draw(make, compact=False), draw(make, compact=True)
    headers = {"Files restored in", "Modified files", "Staged files"}
    assert headers & set(texts(full)), "the full drawing keeps its (empty) table"
    assert not headers & set(texts(small))
    assert not roles(small, "file")
    assert len(roles(small, "commit")) == len(roles(full, "commit"))


def test_compact_leaves_out_the_notes_above_the_graph(repo):
    from git_sim.branch import Branch

    make = lambda: Branch(name="feature", force_delete=True)  # noqa: E731
    assert roles(draw(make, compact=False), "note")
    assert not roles(draw(make, compact=True), "note")


def test_the_compact_option_reaches_the_settings():
    from typer.testing import CliRunner

    from git_sim.__main__ import app

    seen = {}

    @app.command("probe-compact", hidden=True)
    def probe():
        seen["compact"] = settings.compact

    try:
        CliRunner().invoke(app, ["--compact", "probe-compact"])
        assert seen == {"compact": True}
        CliRunner().invoke(app, ["probe-compact"])
        assert seen == {"compact": False}
    finally:
        app.registered_commands[:] = [c for c in app.registered_commands if c.name != "probe-compact"]
        settings.compact = False
