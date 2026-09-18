"""Scene-level regression tests: construct subcommand scenes against small
repositories and check what they draw, without rendering.

These pin down bugs found by validating every subcommand against git ground
truth (see the commit history): amend parentage, the tag title, a switch
target with no labels, and argument validation in mv, stash and config.
"""

import os
import subprocess

import numpy as np
import pytest

from git_sim.settings import Settings, settings


def run_git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Five commits on main, a feature branch off commit 2, cwd inside the repo."""
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
    run_git(path, "branch", "feature", "HEAD~3")
    for key, value in Settings().model_dump().items():
        setattr(settings, key, value)
    settings.auto_open = False
    monkeypatch.chdir(path)
    return path


def ref_commit(scene, name):
    """Short sha of the drawn commit whose column the ref label sits above."""
    label = scene.drawnRefs[name].get_center()
    for sha, circle in scene.drawnCommits.items():
        center = circle.get_center()
        if abs(center[0] - label[0]) < 0.6 and label[1] > center[1]:
            return sha
    return None


def test_amend_replaces_head_instead_of_adding_a_child(repo):
    from git_sim.commit import Commit

    head = run_git(repo, "rev-parse", "HEAD").strip()
    parent = run_git(repo, "rev-parse", "HEAD~1").strip()
    scene = Commit(message="Amended message", amend=True)
    scene.construct()
    drawn = set(scene.drawnCommits)
    assert head not in drawn, "the old HEAD must drop out of the branch"
    assert parent in drawn
    amended = ref_commit(scene, "HEAD")
    assert amended is not None and amended not in {head, parent}
    assert ref_commit(scene, "main") == amended
    assert [p.hexsha for p in scene.repo.commit(amended).parents] == [parent]


def test_tag_title_includes_the_commit_argument(repo):
    from git_sim.tag import Tag

    assert Tag(name="v1", commit="HEAD~2", d=False).cmd == "git tag v1 HEAD~2"
    assert Tag(name="v1", commit=None, d=False).cmd == "git tag v1"
    run_git(repo, "tag", "v9")
    assert Tag(name="v9", commit=None, d=True).cmd == "git tag -d v9"


def test_switch_detach_to_unlabelled_commit_draws_head_there(repo):
    from git_sim.switch import Switch

    # Push the target out of the "reached" window so the scene draws only the
    # target's ancestry, where no branch label exists to stack HEAD on.
    for i in range(6, 13):
        (repo / f"file{i}.txt").write_text(f"content {i}\n")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "-m", f"commit {i}")
    target = run_git(repo, "rev-parse", "HEAD~8").strip()
    scene = Switch(branch="HEAD~8", c=False, detach=True)
    scene.construct()
    assert ref_commit(scene, "HEAD") == target
    assert np.isfinite(scene.camera.frame.get_center()).all()
    assert np.isfinite(scene.drawnRefs["HEAD"].get_center()).all()


def test_mv_refuses_untracked_or_missing_source(repo):
    from git_sim.mv import Mv

    (repo / "loose.txt").write_text("x\n")
    with pytest.raises(SystemExit):
        Mv(file="loose.txt", new_file="moved.txt")
    with pytest.raises(SystemExit):
        Mv(file="nope.txt", new_file="moved.txt")
    assert (
        Mv(file="file1.txt", new_file="renamed.txt").cmd
        == "git mv file1.txt renamed.txt"
    )


def test_stash_pop_with_missing_index_exits_with_message(repo, capsys):
    from git_sim.enums import StashSubCommand
    from git_sim.stash import Stash

    (repo / "file1.txt").write_text("changed\n")
    run_git(repo, "stash")
    scene = Stash(files=[], command=StashSubCommand.POP, stash_index="3")
    with pytest.raises(SystemExit):
        scene.construct()
    assert "No stash entry with index 3" in capsys.readouterr().out


def test_config_list_tolerates_missing_settings_list(repo):
    from git_sim.config import Config

    scene = Config(l=True, settings=None)
    scene.construct()
    texts = {
        mob.text
        for top in scene.mobjects
        for mob in top.get_family()
        if hasattr(mob, "text")
    }
    assert "[core]" in texts


def test_remote_listing_grows_its_box_for_many_remotes(repo):
    from git_sim.remote import Remote

    for i in range(8):
        run_git(repo, "remote", "add", f"mirror{i}", f"https://example.com/m{i}.git")
    scene = Remote(command=None, remote=None, url_or_path=None)
    scene.construct()
    lines = [
        mob
        for top in scene.mobjects
        for mob in top.get_family()
        if getattr(mob, "text", "").startswith(("[remote", "url =", "fetch ="))
    ]
    assert sum(t.text.startswith("[remote") for t in lines) == 8
    # Every config line, including the last, sits inside the box.
    assert scene.project_root.get_bottom()[1] < min(t.get_bottom()[1] for t in lines)


def test_shim_rejects_none_targets_like_manim():
    from git_sim import render as m

    with pytest.raises(TypeError):
        m.Circle().next_to(None, m.UP)
    with pytest.raises(TypeError):
        m.Circle().move_to(None)
    with pytest.raises(TypeError):
        m.Circle().align_to(None, m.UP)
