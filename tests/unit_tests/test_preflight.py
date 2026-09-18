import subprocess

import pytest

from git_sim.preflight import Risk, analyze


def run_git(cwd, *args):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path):
    """A repo with 3 commits on main and a feature branch 1 commit ahead."""
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    for i in range(1, 4):
        (path / f"file{i}.txt").write_text(f"content {i}\n")
        run_git(path, "add", ".")
        run_git(path, "commit", "-m", f"commit {i}")
    run_git(path, "checkout", "-b", "feature")
    (path / "feature.txt").write_text("feature\n")
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "feature commit")
    run_git(path, "checkout", "main")
    return path


def test_reset_hard_reports_abandoned_commits_and_dirty_files(repo):
    (repo / "file1.txt").write_text("modified\n")
    report = analyze("git reset --hard HEAD~2", str(repo))
    assert report.risk == Risk.DESTRUCTIVE
    assert any("commit 3" in f for f in report.facts)
    assert any("commit 2" in f for f in report.facts)
    assert any("file1.txt" in loss for loss in report.would_lose)
    assert any("reflog" in r for r in report.recovery)


def test_reset_soft_is_not_destructive(repo):
    report = analyze("git reset --soft HEAD~1", str(repo))
    assert report.risk == Risk.CAUTION
    assert not report.would_lose or all(
        "NOT recoverable" not in loss for loss in report.would_lose
    )


def test_clean_lists_exact_untracked_files(repo):
    (repo / "junk1.log").write_text("x")
    (repo / "junk2.log").write_text("x")
    report = analyze("git clean -f", str(repo))
    assert report.risk == Risk.DESTRUCTIVE
    assert any("junk1.log" in loss for loss in report.would_lose)
    assert any("junk2.log" in loss for loss in report.would_lose)


def test_clean_without_force_is_refused(repo):
    (repo / "junk.log").write_text("x")
    report = analyze("git clean", str(repo))
    assert report.risk == Risk.SAFE
    assert "refuses" in report.summary


def test_rebase_reports_replayed_commits(repo):
    run_git(repo, "checkout", "feature")
    report = analyze("git rebase main", str(repo))
    assert report.risk in (Risk.CAUTION, Risk.DESTRUCTIVE)
    assert "1 commit(s)" in report.summary
    assert any("feature commit" in f for f in report.facts)


def test_merge_fast_forward_detected(repo):
    report = analyze("git merge feature", str(repo))
    assert report.risk == Risk.SAFE
    assert "fast-forward" in report.summary


def test_merge_conflict_detected(repo):
    (repo / "file1.txt").write_text("main version\n")
    run_git(repo, "commit", "-am", "main edit")
    run_git(repo, "checkout", "feature")
    (repo / "file1.txt").write_text("feature version\n")
    run_git(repo, "commit", "-am", "feature edit")
    run_git(repo, "checkout", "main")
    report = analyze("git merge feature", str(repo))
    assert any("conflict" in w.lower() for w in report.warnings)
    assert any("file1.txt" in w for w in report.warnings)


def test_force_push_reports_remote_only_commits(repo, tmp_path):
    remote = tmp_path / "remote.git"
    run_git(tmp_path, "init", "--bare", str(remote))
    run_git(repo, "remote", "add", "origin", str(remote))
    run_git(repo, "push", "-u", "origin", "main")
    # Remote gains a commit we don't have locally.
    clone = tmp_path / "clone"
    run_git(tmp_path, "clone", str(remote), str(clone))
    run_git(clone, "config", "user.email", "other@example.com")
    run_git(clone, "config", "user.name", "Other")
    (clone / "remote-work.txt").write_text("important\n")
    run_git(clone, "add", ".")
    run_git(clone, "commit", "-m", "remote-only work")
    run_git(clone, "push")
    run_git(repo, "fetch")
    # Local diverges.
    (repo / "local.txt").write_text("local\n")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "local work")

    report = analyze("git push --force", str(repo))
    assert report.risk == Risk.DESTRUCTIVE
    assert any("remote-only work" in loss for loss in report.would_lose)

    plain = analyze("git push", str(repo))
    assert "REJECTED" in plain.summary


def test_branch_force_delete_unmerged(repo):
    report = analyze("git branch -D feature", str(repo))
    assert report.risk == Risk.DESTRUCTIVE
    assert any("feature commit" in f for f in report.facts)
    assert any("git branch feature" in r for r in report.recovery)


def test_branch_delete_merged_is_safe(repo):
    run_git(repo, "merge", "feature")
    report = analyze("git branch -d feature", str(repo))
    assert report.risk == Risk.SAFE
    assert "no commits lost" in report.summary


def test_restore_discards_modifications(repo):
    (repo / "file1.txt").write_text("modified\n")
    report = analyze("git restore file1.txt", str(repo))
    assert report.risk == Risk.DESTRUCTIVE
    assert any("file1.txt" in loss for loss in report.would_lose)


def test_restore_staged_keeps_content(repo):
    (repo / "file1.txt").write_text("modified\n")
    run_git(repo, "add", "file1.txt")
    report = analyze("git restore --staged file1.txt", str(repo))
    assert report.risk == Risk.SAFE


def test_stash_clear_lists_entries(repo):
    (repo / "file1.txt").write_text("modified\n")
    run_git(repo, "stash")
    report = analyze("git stash clear", str(repo))
    assert report.risk == Risk.DESTRUCTIVE
    assert report.would_lose


def test_amend_pushed_commit_warns(repo, tmp_path):
    remote = tmp_path / "remote.git"
    run_git(tmp_path, "init", "--bare", str(remote))
    run_git(repo, "remote", "add", "origin", str(remote))
    run_git(repo, "push", "-u", "origin", "main")
    report = analyze("git commit --amend -m 'new msg'", str(repo))
    assert report.risk == Risk.DESTRUCTIVE
    assert any("PUBLISHED" in w for w in report.warnings)


def test_amend_unpushed_commit_is_caution(repo):
    report = analyze("git commit --amend -m 'new msg'", str(repo))
    assert report.risk == Risk.CAUTION


def test_read_only_command_is_safe(repo):
    report = analyze("git status", str(repo))
    assert report.risk == Risk.SAFE


def test_not_a_repo_reports_error(tmp_path):
    report = analyze("git reset --hard", str(tmp_path))
    assert report.error


def test_unknown_command_defaults_to_caution(repo):
    report = analyze("git symbolic-ref HEAD refs/heads/other", str(repo))
    assert report.risk == Risk.CAUTION
    assert report.text_graph == ""


def test_additive_commands_are_safe(repo):
    for command in (
        "git add .",
        "git mv file1.txt other.txt",
        "git cherry-pick feature",
        "git pull",
    ):
        report = analyze(command, str(repo))
        assert report.risk == Risk.SAFE, command
        assert report.summary and not report.would_lose


def test_rm_reports_uncommitted_changes_lost(repo):
    (repo / "file1.txt").write_text("modified\n")
    report = analyze("git rm -f file1.txt file2.txt", str(repo))
    assert report.risk == Risk.DESTRUCTIVE
    assert any("file1.txt" in loss for loss in report.would_lose)
    assert (
        "tracked",
        "file2.txt",
        "DELETED (recoverable from HEAD)",
    ) in report.panel_rows
    clean = analyze("git rm file2.txt", str(repo))
    assert clean.risk == Risk.CAUTION and not clean.would_lose
    assert analyze("git rm --cached file1.txt", str(repo)).risk == Risk.SAFE
    assert "refuses" in analyze("git rm nope.txt", str(repo)).summary


def test_reflog_gc_and_filter_branch(repo):
    assert analyze("git reflog", str(repo)).risk == Risk.SAFE
    expire = analyze("git reflog expire --expire=now --all", str(repo))
    assert expire.risk == Risk.DESTRUCTIVE and expire.warnings
    assert analyze("git gc", str(repo)).risk == Risk.SAFE
    assert analyze("git gc --prune=now", str(repo)).risk == Risk.CAUTION
    rewrite = analyze("git filter-branch --force --index-filter x HEAD", str(repo))
    assert rewrite.risk == Risk.DESTRUCTIVE and "refs/original" in rewrite.recovery[0]


# --- text graph -----------------------------------------------------------


def test_reset_text_graph_marks_commits_and_files(repo):
    (repo / "file1.txt").write_text("modified\n")
    graph = analyze("git reset --hard HEAD~2", str(repo)).text_graph
    assert graph.count("<- ABANDONED") == 2
    assert "<- NEW HEAD" in graph
    assert "commit 1" in graph  # the target commit is visible
    assert "(HEAD -> main" in graph  # git's own ref decorations
    assert "Working tree:" in graph
    assert "modified  file1.txt" in graph
    assert "DISCARDED" in graph


def test_reset_text_graph_marker_column_is_aligned(repo):
    graph = analyze("git reset --hard HEAD~2", str(repo)).text_graph
    positions = {line.index("<-") for line in graph.splitlines() if "<-" in line}
    assert len(positions) == 1


def test_rebase_text_graph_shows_replayed_and_new_base(repo):
    run_git(repo, "checkout", "feature")
    graph = analyze("git rebase main", str(repo)).text_graph
    assert "<- REPLAYED (new hash)" in graph
    assert "<- NEW BASE" in graph


def test_branch_force_delete_text_graph_includes_branch_tip(repo):
    graph = analyze("git branch -D feature", str(repo)).text_graph
    assert "feature commit" in graph
    assert "<- ABANDONED (branch deleted)" in graph


def test_clean_text_graph_lists_files_in_panel(repo):
    (repo / "junk1.log").write_text("x")
    graph = analyze("git clean -f", str(repo)).text_graph
    assert "untracked junk1.log" in graph
    assert "<- DELETED (not recoverable)" in graph


def test_file_only_operations_show_panel_without_commit_graph(repo):
    (repo / "file1.txt").write_text("modified\n")
    for command in (
        "git checkout -- file1.txt",
        "git restore file1.txt",
        "git reset --hard HEAD",
    ):
        graph = analyze(command, str(repo)).text_graph
        commit_lines = [line for line in graph.splitlines() if line.startswith("*")]
        assert commit_lines == [], command
        assert graph.startswith("Working tree:"), command
        assert "modified  file1.txt" in graph, command


def test_stash_clear_text_panel(repo):
    (repo / "file1.txt").write_text("modified\n")
    run_git(repo, "stash")
    graph = analyze("git stash clear", str(repo)).text_graph
    assert "Stashes:" in graph
    assert "stash@{0}" in graph
    assert "<- DELETED" in graph


def test_amend_text_graph_marks_head(repo):
    graph = analyze("git commit --amend -m 'x'", str(repo)).text_graph
    assert "<- REPLACED (new hash)" in graph


def test_force_push_text_graph_marks_remote_only(repo, tmp_path):
    remote = tmp_path / "remote.git"
    run_git(tmp_path, "init", "--bare", str(remote))
    run_git(repo, "remote", "add", "origin", str(remote))
    run_git(repo, "push", "-u", "origin", "main")
    clone = tmp_path / "clone"
    run_git(tmp_path, "clone", str(remote), str(clone))
    run_git(clone, "config", "user.email", "other@example.com")
    run_git(clone, "config", "user.name", "Other")
    (clone / "remote-work.txt").write_text("important\n")
    run_git(clone, "add", ".")
    run_git(clone, "commit", "-m", "remote-only work")
    run_git(clone, "push")
    run_git(repo, "fetch")
    (repo / "local.txt").write_text("local\n")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "local work")

    graph = analyze("git push --force", str(repo)).text_graph
    assert "remote-only work" in graph
    assert "<- OVERWRITTEN (remote only)" in graph
    assert "<- PUSHED" in graph
    # Divergent history draws a real graph with a connector row.
    assert any(line.startswith("|") for line in graph.splitlines())


def test_text_graph_elides_long_history_but_shows_target(repo):
    for i in range(20):
        (repo / "many.txt").write_text(f"{i}\n")
        run_git(repo, "add", "many.txt")
        run_git(repo, "commit", "-m", f"filler {i}")
    graph = analyze("git reset --hard HEAD~12", str(repo)).text_graph
    commit_lines = [line for line in graph.splitlines() if line.startswith("*")]
    assert graph.count("<- ABANDONED") == 12
    assert "<- NEW HEAD" in graph
    assert 13 <= len(commit_lines) <= 14  # target plus one line of context
    assert "earlier commit(s) not shown" in graph


def test_read_only_command_has_no_text_graph(repo):
    assert analyze("git status", str(repo)).text_graph == ""


def test_text_graph_can_be_disabled(repo):
    report = analyze("git reset --hard HEAD~1", str(repo), render_text=False)
    assert report.text_graph == ""
    assert report.marks  # structured hints are still recorded


def test_text_graph_in_to_dict(repo):
    assert "text_graph" in analyze("git reset --hard HEAD~1", str(repo)).to_dict()


# --- worktrees --------------------------------------------------------------


@pytest.fixture
def linked(repo, tmp_path):
    """A linked worktree 'wt' with the feature branch checked out."""
    wt = tmp_path / "wt"
    run_git(repo, "worktree", "add", str(wt), "feature")
    return wt


def test_single_worktree_has_no_location_line(repo):
    report = analyze("git status", str(repo))
    assert report.location == ""
    assert report.worktree["is_main"] and report.worktree["others"] == []


def test_location_names_current_and_other_worktrees(repo, linked):
    from_main = analyze("git status", str(repo))
    assert from_main.worktree["branch"] == "main" and from_main.worktree["is_main"]
    assert from_main.location.startswith("In the main worktree on main")
    assert "wt (feature)" in from_main.location
    assert from_main.to_dict()["worktree"]["others"][0]["branch"] == "feature"

    from_wt = analyze("git status", str(linked))
    assert from_wt.worktree["branch"] == "feature" and not from_wt.worktree["is_main"]
    assert from_wt.location.startswith("In worktree 'wt' on feature")


def test_branch_delete_refused_when_checked_out_in_another_worktree(repo, linked):
    report = analyze("git branch -D feature", str(repo))
    assert report.risk == Risk.SAFE
    assert "checked out in worktree 'wt'" in report.summary
    assert not report.would_lose


def test_checkout_refused_when_branch_checked_out_elsewhere(repo, linked):
    report = analyze("git checkout feature", str(repo))
    assert report.risk == Risk.SAFE
    assert "already checked out in worktree 'wt'" in report.summary
    override = analyze("git checkout --ignore-other-worktrees feature", str(repo))
    assert "refuses" not in override.summary


def test_stash_entries_from_other_worktrees_are_flagged(repo, linked):
    (linked / "feature.txt").write_text("changed\n")
    run_git(linked, "stash")
    report = analyze("git stash clear", str(repo))
    assert report.risk == Risk.DESTRUCTIVE
    assert any("[worktree: wt]" in row[1] for row in report.panel_rows)
    assert any("shared by every worktree" in w for w in report.warnings)
    own = analyze("git stash drop", str(linked))
    assert not any("shared by every worktree" in w for w in own.warnings)


def test_rebase_warns_about_worktree_based_on_replayed_commits(repo, linked, tmp_path):
    run_git(repo, "branch", "feature2", "feature")
    run_git(repo, "worktree", "add", str(tmp_path / "wt2"), "feature2")
    report = analyze("git rebase main", str(linked))
    assert any("wt2" in w and "based on 1" in w for w in report.warnings)


def test_worktree_remove_with_changes_needs_force(repo, linked):
    (linked / "feature.txt").write_text("changed\n")
    (linked / "junk.txt").write_text("x\n")
    refused = analyze(f"git worktree remove {linked}", str(repo))
    assert refused.risk == Risk.SAFE
    assert "refuses" in refused.summary and "2 uncommitted" in refused.summary
    forced = analyze(f"git worktree remove --force {linked}", str(repo))
    assert forced.risk == Risk.DESTRUCTIVE
    assert any("feature.txt" in loss for loss in forced.would_lose)
    assert any("junk.txt" in loss for loss in forced.would_lose)
    assert ("untracked", "junk.txt", "DELETED (not recoverable)") in forced.panel_rows
    assert any("git worktree add" in r for r in forced.recovery)


def test_worktree_remove_clean_is_safe_and_matches_by_name(repo, linked):
    report = analyze("git worktree remove wt", str(repo))
    assert report.risk == Risk.SAFE
    assert "it is clean" in report.summary and "feature stays" in report.summary


def test_worktree_prune_reports_stale_records(repo, linked):
    import shutil

    assert "No stale" in analyze("git worktree prune", str(repo)).summary
    shutil.rmtree(linked)
    report = analyze("git worktree prune", str(repo))
    assert "1 stale" in report.summary
    assert any("worktrees/wt" in f for f in report.facts)


def test_text_graph_labels_branches_checked_out_elsewhere(repo, linked):
    graph = analyze("git merge feature", str(repo)).text_graph
    assert "feature @wt" in graph
