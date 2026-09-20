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


# ---------------------------------------------------------------------------
# flags and commands added after the first validation pass
# ---------------------------------------------------------------------------
def scene_texts(scene):
    return [
        mob.text
        for top in scene.mobjects
        for mob in top.get_family()
        if hasattr(mob, "text")
    ]


def title_fits(scene):
    title = next(
        m
        for top in scene.mobjects
        for m in top.get_family()
        if getattr(m, "text", None) == scene.cmd
    )
    return title.get_top()[1] <= scene.camera.frame.get_top()[1]


def make_branch_with_commit(repo, name, filename):
    run_git(repo, "checkout", "-q", "-b", name)
    (repo / filename).write_text("side\n")
    run_git(repo, "add", filename)
    run_git(repo, "commit", "-q", "-m", f"{name} work")
    sha = run_git(repo, "rev-parse", "HEAD").strip()
    run_git(repo, "checkout", "-q", "main")
    return sha


def test_branch_delete_refuses_unmerged_and_force_marks_it_gold(repo):
    from git_sim.branch import Branch

    wip = make_branch_with_commit(repo, "wip", "wip.txt")
    with pytest.raises(SystemExit):
        Branch(name="wip", delete=True)
    with pytest.raises(SystemExit):
        Branch(name="feature", new_name="wip", move=True)  # target exists
    scene = Branch(name="wip", force_delete=True)
    scene.construct()
    assert scene.orphaned == [wip]
    assert "wip" not in scene.drawnRefs
    assert any(f"git branch wip {wip[:6]}" in t for t in scene_texts(scene))
    assert title_fits(scene)
    merged = Branch(name="feature", delete=True)  # feature is an ancestor of main
    merged.construct()
    assert "feature" not in merged.drawnRefs and merged.orphaned == []


def test_branch_move_relabels_the_same_commit(repo):
    from git_sim.branch import Branch

    target = run_git(repo, "rev-parse", "feature").strip()
    scene = Branch(name="feature", new_name="topic", move=True)
    scene.construct()
    assert ref_commit(scene, "topic") == target
    assert "feature" not in scene.drawnRefs
    assert scene.cmd == "git branch -m feature topic"


def test_zone_rows_keep_arrows_straight_and_off_other_text():
    from git_sim.git_sim_base_command import GitSimBaseCommand, ZoneNames

    names = {1: ZoneNames(), 2: ZoneNames(), 3: ZoneNames()}
    for col, items in (
        (1, ["new.txt"]),
        (2, ["mod.txt", "other.txt"]),
        (3, ["new.txt", "mod.txt", "old.txt"]),
    ):
        for item in items:
            names[col].add(item)
    rows = GitSimBaseCommand.zone_rows(
        None, names, [("new.txt", 1, 3), ("mod.txt", 2, 3)]
    )
    # both ends of a move share a row, so its arrow is horizontal
    assert rows[(1, "new.txt")] == rows[(3, "new.txt")]
    assert rows[(2, "mod.txt")] == rows[(3, "mod.txt")]
    # the row an arrow crosses stays empty in the middle column
    crossed = rows[(1, "new.txt")]
    assert crossed not in {rows[(2, "mod.txt")], rows[(2, "other.txt")]}
    # no two entries of a column share a row
    for col in names:
        taken = [rows[(col, n)] for n in names[col]]
        assert len(taken) == len(set(taken))


def test_trim_path_keeps_the_file_name_readable():
    from git_sim.git_sim_base_command import GitSimBaseCommand

    trim = lambda p: GitSimBaseCommand.trim_path(None, p)
    assert trim("short/name.txt") == "short/name.txt"
    assert (
        trim("src/main/resources/static/js/learn/lesson.js")
        == "src/.../static/js/learn/lesson.js"
    )
    assert (
        trim("src/main/java/com/initialcommit/web/GitSimViewController.java")
        == ".../web/GitSimViewController.java"
    )
    long_name = trim("docs/a_really_long_file_name_that_goes_on_and_on_forever.md")
    assert (
        long_name.startswith(".../a_really")
        and long_name.endswith("forever.md")
        and len(long_name) <= 33
    )


def test_stash_push_moves_left_and_pop_moves_right(repo):
    from git_sim.enums import StashSubCommand
    from git_sim.stash import Stash

    (repo / "file1.txt").write_text("modified\n")
    (repo / "file2.txt").write_text("staged\n")
    run_git(repo, "add", "file2.txt")
    push = Stash(files=[], command=StashSubCommand.PUSH, stash_index="0")
    push.construct()
    # the stash sits left of the working directory: pushing moves changes left
    assert {t.text for t in push.firstColumnFiles} == {"file1.txt", "file2.txt"}
    assert {t.text for t in push.secondColumnFiles} == {"file1.txt"}
    assert {t.text for t in push.thirdColumnFiles} == {"file2.txt"}
    assert set(push.zone_arrows) == {("file1.txt", 2, 1), ("file2.txt", 3, 1)}

    run_git(repo, "stash")
    pop = Stash(files=[], command=StashSubCommand.POP, stash_index="0")
    pop.construct()
    # popping brings them back to the right, consuming the entry
    assert {t.text for t in pop.secondColumnFiles} == {"file1.txt", "file2.txt"}
    assert all(t.strikethrough for t in pop.firstColumnFiles)
    assert set(pop.zone_arrows) == {("file1.txt", 1, 2), ("file2.txt", 1, 2)}


def test_stash_drop_and_clear_strike_entries(repo):
    from git_sim.enums import StashSubCommand
    from git_sim.stash import Stash

    (repo / "file1.txt").write_text("changed\n")
    run_git(repo, "stash")
    (repo / "file2.txt").write_text("changed\n")
    run_git(repo, "stash")
    scene = Stash(files=[], command=StashSubCommand.DROP, stash_index="1")
    scene.construct()
    # dropped entries land in the left column (a removal moves right to left), struck through
    dropped = [(t.text, t.strikethrough) for t in scene.firstColumnFiles]
    assert len(dropped) == 1 and dropped[0][0].startswith("stash@{1}") and dropped[0][1]
    assert len(scene.thirdColumnFiles) == 2  # every entry is still listed on the right
    assert scene.cmd == "git stash drop stash@{1}"
    with pytest.raises(SystemExit):
        Stash(files=[], command=StashSubCommand.SHOW, stash_index="7")
    clear = Stash(files=[], command=StashSubCommand.CLEAR, stash_index="0")
    clear.construct()
    assert len(clear.firstColumnFiles) == 2


def test_rebase_interactive_todo_squash_and_drop(repo, tmp_path):
    from git_sim.rebase import Rebase

    c3, c4, c5 = (run_git(repo, "rev-parse", f"HEAD~{i}").strip() for i in (2, 1, 0))
    todo = tmp_path / "todo"
    todo.write_text(
        f"pick {c3[:7]} commit 3\nsquash {c4[:7]} commit 4\ndrop {c5[:7]} commit 5\n"
    )
    before = set(run_git(repo, "rev-list", "--all").split())
    scene = Rebase(branch="feature", interactive=True, todo=str(todo))
    scene.construct()
    copies = [s for s in scene.drawnCommits if s not in before]
    assert len(copies) == 1, "squash folds into the pick, drop makes no copy"
    assert ref_commit(scene, "HEAD") == copies[0]
    assert any(
        "1 commit(s) replayed, 1 squashed/fixed up into the previous one, 1 dropped"
        in t
        for t in scene_texts(scene)
    )
    with pytest.raises(SystemExit):
        Rebase(branch="feature", todo=str(todo))  # --todo needs -i


def test_rebase_onto_replays_on_the_onto_commit(repo):
    from git_sim.rebase import Rebase

    make_branch_with_commit(repo, "side", "side.txt")
    side = run_git(repo, "rev-parse", "side").strip()
    before = set(run_git(repo, "rev-list", "--all").split())
    scene = Rebase(branch="feature", onto="side")
    scene.construct()
    copies = [s for s in scene.drawnCommits if s not in before]
    assert len(copies) == 3  # commits 3, 4, 5
    assert scene.cmd == "git rebase --onto side feature"
    # The oldest copy sits right after the onto commit.
    first = min(
        copies,
        key=lambda s: abs(
            scene.drawnCommits[s].get_center()[0]
            - scene.drawnCommits[side].get_center()[0]
        ),
    )
    assert (
        abs(
            scene.drawnCommits[first].get_center()[1]
            - scene.drawnCommits[side].get_center()[1]
        )
        < 1e-6
    )


def test_cherry_pick_range_chains_copies_and_no_commit_stages_only(repo):
    from git_sim.cherrypick import CherryPick

    run_git(repo, "checkout", "-q", "-b", "side", "feature")
    for name in ("s1.txt", "s2.txt"):
        (repo / name).write_text("side\n")
        run_git(repo, "add", name)
        run_git(repo, "commit", "-q", "-m", f"side {name}")
    run_git(repo, "checkout", "-q", "main")
    scene = CherryPick(commit="side~2..side", edit=None)
    scene.construct()
    assert {"abcdef", "abcdeg"} <= set(scene.drawnCommits)
    assert ref_commit(scene, "HEAD") == "abcdeg"
    with pytest.raises(SystemExit):
        CherryPick(commit="side..side", edit=None)
    staged = CherryPick(commit="side", edit=None, no_commit=True)
    staged.construct()
    assert "abcdef" not in staged.drawnCommits
    assert {t.text for t in staged.secondColumnFiles} == {"s2.txt"}


def test_revert_merge_needs_mainline_and_no_commit_adds_nothing(repo):
    from git_sim.revert import Revert

    make_branch_with_commit(repo, "side", "side.txt")
    run_git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    with pytest.raises(SystemExit):
        Revert(commit="HEAD")
    with pytest.raises(SystemExit):
        Revert(commit="HEAD", mainline=3)
    scene = Revert(commit="HEAD", mainline=1)
    scene.construct()
    assert "abcdef" in scene.drawnCommits
    assert {t.text for t in scene.secondColumnFiles} == {"side.txt"}
    nc = Revert(commit="HEAD~1", no_commit=True)
    nc.construct()
    assert "abcdef" not in nc.drawnCommits and nc.cmd == "git revert -n HEAD~1"


def test_commit_flags(repo):
    from git_sim.commit import Commit

    assert Commit(message="New commit", amend=True, no_edit=True).message == "commit 5"
    with pytest.raises(SystemExit):
        Commit(message="x", amend=False, no_edit=True)
    (repo / "file1.txt").write_text("modified\n")
    (repo / "loose.txt").write_text("untracked\n")
    scene = Commit(message="all", amend=False, all=True)
    scene.construct()
    assert {t.text for t in scene.thirdColumnFiles} == {"file1.txt"}
    assert scene.cmd == 'git commit -a -m "all"'


def test_reset_path_unstages_without_moving_head(repo):
    from git_sim.enums import ResetMode
    from git_sim.reset import Reset

    (repo / "file1.txt").write_text("staged\n")
    run_git(repo, "add", "file1.txt")
    head = run_git(repo, "rev-parse", "HEAD").strip()
    scene = Reset(
        commit="file1.txt", mode=ResetMode.DEFAULT, soft=False, mixed=False, hard=False
    )
    assert scene.paths == ["file1.txt"] and scene.commit == "HEAD"
    scene.construct()
    assert ref_commit(scene, "HEAD") == head
    assert {t.text for t in scene.firstColumnFiles} == {"file1.txt"}
    with pytest.raises(SystemExit):
        Reset(
            commit="HEAD",
            mode=ResetMode.DEFAULT,
            soft=False,
            mixed=False,
            hard=True,
            paths=["file1.txt"],
        )
    with pytest.raises(SystemExit):
        Reset(
            commit="HEAD",
            mode=ResetMode.DEFAULT,
            soft=False,
            mixed=False,
            hard=False,
            paths=["nope.txt"],
        )


def test_restore_source_checks_the_file_exists_there(repo):
    from git_sim.restore import Restore

    with pytest.raises(SystemExit):
        Restore(files=["file5.txt"], staged=False, source="HEAD~1")  # added in commit 5
    scene = Restore(files=["file1.txt"], staged=True, source="HEAD~1")
    scene.construct()
    assert scene.cmd == "git restore --staged --source HEAD~1 file1.txt"
    assert any(t.startswith("Restored from ") for t in scene_texts(scene))


def test_clean_flags_follow_git_dry_run(repo):
    from git_sim.clean import Clean

    (repo / "loose.txt").write_text("x\n")
    (repo / "newdir").mkdir()
    (repo / "newdir" / "f.txt").write_text("x\n")
    assert Clean().would_remove() == ["loose.txt"]
    assert set(Clean(force=True, directories=True).would_remove()) == {
        "loose.txt",
        "newdir/",
    }
    assert Clean(force=True, directories=True, ignored=True).cmd == "git clean -f -d -x"


def test_push_force_draws_the_overwritten_remote_commits(repo, tmp_path):
    from git_sim.push import Push

    remote = tmp_path / "remote.git"
    run_git(repo, "clone", "-q", "--bare", str(repo), str(remote))
    run_git(repo, "remote", "add", "origin", str(remote))
    run_git(repo, "fetch", "-q", "origin")
    other = tmp_path / "other"
    run_git(tmp_path, "clone", "-q", str(remote), str(other))
    run_git(other, "config", "user.email", "o@example.com")
    run_git(other, "config", "user.name", "Other")
    (other / "remote.txt").write_text("remote\n")
    run_git(other, "add", "remote.txt")
    run_git(other, "commit", "-q", "-m", "remote only")
    run_git(other, "push", "-q")
    remote_only = run_git(other, "rev-parse", "HEAD").strip()
    (repo / "local.txt").write_text("local\n")
    run_git(repo, "add", "local.txt")
    run_git(repo, "commit", "-q", "-m", "local only")
    with pytest.raises(SystemExit):
        Push(force=True, force_with_lease=True)
    scene = Push(force=True)
    scene.construct()
    assert remote_only in scene.drawnCommits
    assert any("1 remote commit(s) were overwritten" in t for t in scene_texts(scene))
    assert scene.cmd == "git push --force"
    assert title_fits(scene)


def test_reflog_draws_commits_only_the_reflog_still_reaches(repo):
    from git_sim.reflog import Reflog

    lost = run_git(repo, "rev-parse", "HEAD").strip()
    run_git(repo, "reset", "-q", "--hard", "HEAD~1")
    scene = Reflog(n=3)
    scene.construct()
    assert lost in scene.drawnCommits
    assert ref_commit(scene, "HEAD@{1}") == lost
    assert any("git reset --hard HEAD@{1}" in t for t in scene_texts(scene))
    assert scene.cmd == "git reflog -n 3"


def test_worktree_scenes(repo, tmp_path):
    from git_sim.enums import WorktreeSubCommand
    from git_sim.worktree import Worktree

    wt = tmp_path / "wt"
    run_git(repo, "worktree", "add", "-q", str(wt), "feature")
    (wt / "scratch.txt").write_text("wip\n")
    scene = Worktree(
        command=WorktreeSubCommand.LIST, path=None, branch=None, force=False
    )
    scene.construct()
    assert [r[1] for r in scene.rows] == ["main", "feature"]
    assert scene.rows[1][2] == "1 uncommitted change(s)"
    refused = Worktree(
        command=WorktreeSubCommand.REMOVE, path=str(wt), branch=None, force=False
    )
    refused.construct()
    assert refused.rows[1][2].startswith("refused")
    forced = Worktree(
        command=WorktreeSubCommand.REMOVE, path=str(wt), branch=None, force=True
    )
    forced.construct()
    assert forced.rows[1][3] is True  # struck through
    with pytest.raises(SystemExit):
        Worktree(command=WorktreeSubCommand.ADD, path=str(wt), branch=None, force=False)
    added = Worktree(
        command=WorktreeSubCommand.ADD, path="../fresh", branch="topic", force=False
    )
    added.construct()
    assert added.rows[-1][1] == "topic  (new branch)"
    with_b = Worktree(
        command=WorktreeSubCommand.ADD,
        path="../fresh",
        branch=None,
        force=False,
        new_branch="topic",
    )
    assert with_b.cmd == "git worktree add -b topic ../fresh"
    with pytest.raises(SystemExit):
        Worktree(
            command=WorktreeSubCommand.ADD,
            path="../fresh",
            branch=None,
            force=False,
            new_branch="feature",
        )


def test_submodule_scenes(repo):
    from git_sim.enums import SubmoduleSubCommand
    from git_sim.submodule import Submodule

    none = Submodule(
        command=SubmoduleSubCommand.STATUS,
        url_or_path=None,
        path=None,
        init=False,
        force=False,
    )
    none.construct()
    assert none.rows == [] and any("No submodules" in t for t in scene_texts(none))
    add = Submodule(
        command=SubmoduleSubCommand.ADD,
        url_or_path="https://example.com/lib.git",
        path=None,
        init=False,
        force=False,
    )
    assert add.path == "lib"
    add.construct()
    assert add.rows[-1][0] == "lib  (new)"
    with pytest.raises(SystemExit):
        Submodule(
            command=SubmoduleSubCommand.DEINIT,
            url_or_path="lib",
            path=None,
            init=False,
            force=False,
        )
    with pytest.raises(SystemExit):
        Submodule(
            command=SubmoduleSubCommand.ADD,
            url_or_path=None,
            path=None,
            init=False,
            force=False,
        )


def test_preflight_submodule_deinit_is_flagged():
    from git_sim.preflight import RISKY_SUBCOMMANDS

    assert "submodule" in RISKY_SUBCOMMANDS
