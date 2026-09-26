"""The matrix: every subcommand, its options, and the repository shapes it
can meet. Each case names a shape, the git-sim arguments, and a check that
compares the drawing with what git itself says about the repository.

A case with ``error`` set must fail with that text in its output and never a
traceback. Every successful case is also compared with its golden model.

Zone columns as git-sim names them: "Untracked files", "Modified files",
"Staged files" (status, add), "Working directory", "Staging area", "Stashed
changes" (stash, rm, restore), "Removed files" (rm), "Deleted files" (clean).
The helpers below match them by keyword.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

import oracle as o
from svgmodel import commits_by_phase, has_text

N_DEFAULT = 5  # git-sim's default -n: the window of commits drawn per branch


@dataclass
class Case:
    id: str
    shape: str
    args: List[str]
    check: Optional[Callable] = None
    error: Optional[str] = None  # expected failure text
    fmt: str = "svg"
    slow: bool = False
    globals_: List[str] = field(default_factory=list)  # global options for the run


# ---- zone helpers ---------------------------------------------------------------------------

ZONES = {
    "staging": ("staged", "staging"),
    "working": ("working", "modified"),
    "untracked": ("untracked",),
    "stash": ("stash",),
    "gone": ("removed", "deleted"),
}


def files_in(model, zone, phase=None):
    words = ZONES[zone]
    return sorted(
        f["name"]
        for f in model["files"]
        if any(w in f["column"].lower() for w in words) and (phase is None or f["phase"] == phase)
    )


# ---- reusable checks --------------------------------------------------------------------------


def title(prefix):
    def check(m, repo):
        assert m["title"].replace("  ", " ").startswith(prefix), f"title {m['title']!r} does not start with {prefix!r}"
    return check


def after_commits(n):
    def check(m, repo):
        got = len(commits_by_phase(m, "after"))
        assert got == n, f"expected {n} simulated commit(s), drew {got}"
    return check


def merge_of(branch):
    """A merge commit appears whose parents are HEAD and the branch tip, unless
    the merge is a fast-forward (labels move, nothing new)."""
    def check(m, repo):
        head, tip = o.rev_parse(repo, "HEAD"), o.rev_parse(repo, branch)
        if o.is_ancestor(repo, head, tip):
            assert not commits_by_phase(m, "after"), "fast-forward should add no commit"
            assert any(r["moved"] for r in m["refs"].values()), "labels should move on a fast-forward"
            return
        new = commits_by_phase(m, "after")
        assert len(new) == 1, f"one merge commit expected, drew {len(new)}"
        (c,) = new.values()
        assert set(c["parents"]) == {head, tip}, f"merge parents {c['parents']} != {{HEAD, {branch}}}"
        assert c["kind"] == "merge"
    return check


def rebase_onto(upstream):
    """Replays the commits of HEAD that the upstream lacks, up to the drawing
    window (-n); past it, the oldest replays fold into one elided marker."""
    def check(m, repo):
        replayed = o.count(repo, f"{upstream}..HEAD")
        new = commits_by_phase(m, "after")
        expected = min(replayed, N_DEFAULT)
        assert len(new) == expected, f"rebase should draw {expected} replayed commit(s) ({replayed} in git), drew {len(new)}"
        if replayed:
            assert any(o.rev_parse(repo, upstream) in c["parents"] for c in new.values()), "the first replay sits on the upstream tip"
    return check


def picks(n, parent="HEAD"):
    def check(m, repo):
        new = commits_by_phase(m, "after")
        assert len(new) == n, f"expected {n} picked commit(s), drew {len(new)}"
        if n == 1:
            (c,) = new.values()
            assert o.rev_parse(repo, parent) in c["parents"]
    return check


def moved(*names):
    def check(m, repo):
        for name in names:
            assert name in m["refs"], f"no label {name!r} drawn ({sorted(m['refs'])})"
            assert m["refs"][name]["moved"], f"label {name!r} should move"
    return check


def relabelled(*names):
    """The label either slides to its new commit or is drawn anew there."""
    def check(m, repo):
        for name in names:
            assert name in m["refs"], f"no label {name!r} drawn ({sorted(m['refs'])})"
            r = m["refs"][name]
            assert r["moved"] or r["phase"] == "after", f"label {name!r} should move or appear"
    return check


def ref_after(name, kind=None):
    def check(m, repo):
        assert name in m["refs"], f"no label {name!r} ({sorted(m['refs'])})"
        assert m["refs"][name]["phase"] == "after", f"{name!r} should be simulated (phase after)"
        if kind:
            assert m["refs"][name]["kind"] == kind
    return check


def ref_removed(name):
    def check(m, repo):
        assert name in m["refs"], f"no label {name!r} ({sorted(m['refs'])})"
        assert m["refs"][name]["phase"] == "removed", f"{name!r} should be removed"
    return check


def orphaned_by(ref):
    """Commits only that ref reached are drawn recolored (gold)."""
    def check(m, repo):
        expected = set(o.only_reachable_from(repo, ref))
        gold = {s for s, c in m["commits"].items() if c["recolored"]}
        assert gold == expected & set(m["commits"]), f"gold {sorted(s[:7] for s in gold)} != orphaned {sorted(s[:7] for s in expected)}"
    return check


def reset_to(target):
    def check(m, repo):
        relabelled("HEAD")(m, repo)
        branch = o.head_branch(repo)
        if branch:
            relabelled(branch)(m, repo)
        gold = {s for s, c in m["commits"].items() if c["recolored"]}
        left_behind = set(o.only_reachable_from(repo, "HEAD")) - set(o.git(repo, "rev-list", target).split())
        assert gold == left_behind & set(m["commits"]), f"gold {sorted(s[:7] for s in gold)} != commits left behind {sorted(s[:7] for s in left_behind)}"
    return check


def amended(m, repo):
    """The amended commit replaces HEAD in place: a new commit with HEAD's
    parents arrives (phase after) where the old one, drawn as removed, was.
    The labels sit on that slot before and after, so they neither move nor
    appear."""
    head = o.rev_parse(repo, "HEAD")
    replacements = {s: c for s, c in m["commits"].items() if s != head and set(c["parents"]) == set(o.parents(repo, "HEAD"))}
    assert replacements, "no commit with HEAD's parents replaces HEAD"
    assert all(c["phase"] == "after" for c in replacements.values()), "the replacement should be simulated (phase after)"
    assert head in m["commits"] and m["commits"][head]["phase"] == "removed", "the old HEAD commit should be drawn as removed"
    assert "HEAD" in m["refs"], f"no HEAD label ({sorted(m['refs'])})"
    assert not m["refs"]["HEAD"]["moved"], "HEAD stays on the same slot"


def arrives(name, zone):
    def check(m, repo):
        got = files_in(m, zone, "after")
        assert name in got, f"{name!r} should arrive in {zone} (after: {got})"
    return check


def gone(*names):
    def check(m, repo):
        got = files_in(m, "gone", "after")
        for n in names:
            assert n in got, f"{n!r} should be shown removed or deleted (got {got})"
    return check


def status_matches(m, repo):
    st = o.status(repo)
    assert set(files_in(m, "staging")) >= set(st["staged"]), f"staged {st['staged']} not all drawn: {files_in(m, 'staging')}"
    assert set(files_in(m, "working")) >= set(st["modified"]), f"modified {st['modified']} not all drawn: {files_in(m, 'working')}"
    assert set(files_in(m, "untracked")) >= set(st["untracked"]), f"untracked {st['untracked']} not all drawn"


def texts(*needles):
    def check(m, repo):
        for n in needles:
            assert has_text(m, n), f"expected text {n!r} in the drawing"
    return check


def all_of(*checks):
    def check(m, repo):
        for c in checks:
            c(m, repo)
    return check


def commits_at_most(n):
    def check(m, repo):
        assert len(m["commits"]) <= n, f"drew {len(m['commits'])} commits, at most {n} expected"
    return check


def commits_at_least(n):
    def check(m, repo):
        assert len(m["commits"]) >= n, f"drew {len(m['commits'])} commits, at least {n} expected"
    return check


def reflog_labels(at_most=None):
    def check(m, repo):
        labels = [n for n in m["refs"] if n.startswith("HEAD@{")]
        assert labels, f"no HEAD@{{k}} labels ({sorted(m['refs'])})"
        if at_most is not None:
            assert len(labels) <= at_most, f"{len(labels)} reflog labels, at most {at_most}"
        assert len(labels) <= o.reflog_count(repo)
    return check


def stashes_something(m, repo):
    got = files_in(m, "stash", "after")
    assert got, f"no files arriving in the stash (files: {m['files']})"


def unstashes_something(m, repo):
    arriving = [f for f in m["files"] if f["phase"] == "after" and not any(w in f["column"].lower() for w in ZONES["stash"])]
    assert arriving, f"no files leaving the stash (files: {m['files']})"


def head_detached_ok(m, repo):
    assert "HEAD" in m["refs"]
    assert o.head_branch(repo) is None


def merge_parents_at_least(n):
    def check(m, repo):
        assert any(len(c["parents"]) >= n for c in m["commits"].values()), f"no commit with {n}+ parents drawn"
    return check


def roots(n):
    def check(m, repo):
        got = sum(1 for c in m["commits"].values() if not c["parents"])
        assert got >= n, f"expected {n} root commits, drew {got}"
    return check


def message_among_new(text):
    def check(m, repo):
        assert any(c["message"] == text for c in commits_by_phase(m, "after").values()), f"no simulated commit with message {text!r}"
    return check


def recolored(n):
    def check(m, repo):
        got = sum(1 for c in m["commits"].values() if c["recolored"])
        assert got == n, f"{got} gold commits, expected {n}"
    return check


# ---- the cases ----------------------------------------------------------------------------------

M = "feature/pagination"  # the history, rebase-ready, criss-cross and worktree shapes' first branch
CASES: List[Case] = [
    # add
    Case("add-untracked", "messy", ["add", "scratch.txt"], all_of(title("git add"), arrives("scratch.txt", "staging"))),
    Case("add-modified", "messy", ["add", "README.md"], arrives("README.md", "staging")),
    # `git add` with no pathspec stages nothing ("Nothing specified, nothing added")
    Case("add-all", "messy", ["add"], all_of(title("git add"), lambda m, r: not files_in(m, "staging", "after"))),
    Case("add-two", "messy", ["add", "scratch.txt", "notes-2.txt"], all_of(arrives("scratch.txt", "staging"), arrives("notes-2.txt", "staging"))),
    Case("add-missing", "messy", ["add", "nope.txt"], error="git-sim error"),
    Case("add-clean-tree", "history", ["add"], title("git add")),
    # branch
    Case("branch-new", "classic", ["branch", "topic"], all_of(title("git branch topic"), ref_after("topic", "branch"))),
    Case("branch-delete-merged", "history", ["branch", "-d", M], ref_removed(M), globals_=["-n", "20"]),
    Case("branch-delete-unmerged-refused", "classic", ["branch", "-d", "branch2"], error="git-sim error"),
    Case("branch-force-delete", "classic", ["branch", "-D", "branch2"], all_of(ref_removed("branch2"), orphaned_by("branch2"))),
    Case("branch-force-delete-merged", "classic", ["branch", "-D", "branch1"], all_of(ref_removed("branch1"), orphaned_by("branch1"))),
    Case("branch-rename", "classic", ["branch", "-m", "branch2", "topic"], all_of(ref_removed("branch2"), ref_after("topic"))),
    Case("branch-existing", "classic", ["branch", "branch2"], error="git-sim error"),
    Case("branch-delete-missing", "classic", ["branch", "-d", "nope"], error="git-sim error"),
    Case("branch-delete-current", "classic", ["branch", "-D", "main"], error="git-sim error"),
    # checkout
    Case("checkout-branch", "classic", ["checkout", "branch2"], all_of(title("git checkout branch2"), relabelled("HEAD"))),
    Case("checkout-new", "classic", ["checkout", "-b", "topic"], ref_after("topic", "branch")),
    Case("checkout-tag", "release", ["checkout", "v1.0.0"], relabelled("HEAD")),
    Case("checkout-commit", "classic", ["checkout", "HEAD~2"], relabelled("HEAD")),
    Case("checkout-missing", "classic", ["checkout", "nope"], error="git-sim error"),
    Case("checkout-current", "classic", ["checkout", "main"], error="already on"),
    # cherry-pick
    Case("cherry-pick-branch", "classic", ["cherry-pick", "branch2"], all_of(title("git cherry-pick"), picks(1))),
    Case("cherry-pick-sha", "classic", ["cherry-pick", "branch3~1"], picks(1)),
    Case("cherry-pick-range", "classic", ["cherry-pick", "branch2~2..branch2"], picks(2)),
    Case("cherry-pick-edit", "classic", ["cherry-pick", "branch2", "-e", "Picked with a new message"], all_of(picks(1), message_among_new("Picked with a new message"))),
    Case("cherry-pick-no-commit", "classic", ["cherry-pick", "branch2", "-n"], after_commits(0)),
    Case("cherry-pick-missing", "classic", ["cherry-pick", "nope"], error="git-sim error"),
    # clean
    Case("clean-force", "messy", ["clean", "-f"], all_of(title("git clean"), gone("scratch.txt", "notes-2.txt"))),
    Case("clean-force-dirs", "messy", ["clean", "-f", "-d"], gone("scratch.txt")),
    Case("clean-dry", "messy", ["clean", "-n"], gone("scratch.txt")),
    Case("clean-ignored", "messy", ["clean", "-f", "-x"], gone("scratch.txt")),
    Case("clean-no-force", "messy", ["clean"], title("git clean")),
    Case("clean-nothing", "history", ["clean", "-f"], title("git clean")),
    # commit
    Case("commit", "messy", ["commit", "-m", "Ship it"], all_of(title("git commit"), after_commits(1), message_among_new("Ship it"))),
    Case("commit-all", "messy", ["commit", "-a", "-m", "Everything"], all_of(after_commits(1), message_among_new("Everything"), lambda m, r: any(f["name"] == "README.md" for f in m["files"]))),
    Case("commit-amend", "history", ["commit", "--amend", "-m", "Reworded"], amended),
    Case("commit-amend-no-edit", "history", ["commit", "--amend", "--no-edit"], amended),
    Case("commit-detached", "detached", ["commit", "-m", "On a detached HEAD"], all_of(after_commits(1), head_detached_ok)),
    Case("commit-first", "empty", ["commit", "-m", "First"], title("git commit")),
    # config
    Case("config-set", "history", ["config", "user.name", "Ada"], all_of(title("git config"), texts("user.name", "Ada"))),
    Case("config-get", "history", ["config", "user.email"], texts("user.email")),
    Case("config-list", "history", ["config", "--list"], texts("[core]")),
    Case("config-remote-key", "ahead", ["config", "remote.origin.url"], texts("remote")),
    Case("config-none", "history", ["config"], error="git-sim error"),
    Case("config-bad-key", "history", ["config", "nodot", "x"], error="git-sim error"),
    # fetch
    Case("fetch", "behind", ["fetch", "origin", "main"], all_of(title("git fetch"), after_commits(2), relabelled("origin/main"))),
    Case("fetch-default", "behind", ["fetch"], after_commits(2)),
    Case("fetch-up-to-date", "ahead", ["fetch", "origin", "main"], after_commits(0)),
    Case("fetch-no-remote", "classic", ["fetch"], error="no remotes"),
    # init
    Case("init-new", "notrepo", ["init"], all_of(title("git init"), texts("Initialized"))),
    Case("init-existing", "history", ["init"], texts("Reinitialized")),
    # log
    Case("log", "history", ["log"], all_of(title("git log"), commits_at_least(1), commits_at_most(N_DEFAULT * 4))),
    Case("log-all", "history", ["log", "--all"], commits_at_least(6)),
    Case("log-n", "history", ["log", "-n", "2", "--all"], commits_at_most(2 * 6)),
    Case("log-octopus", "octopus", ["log", "--all"], merge_parents_at_least(4)),
    Case("log-orphan", "orphan", ["log", "--all"], roots(2)),
    Case("log-criss-cross", "criss-cross", ["log", "--all", "-n", "12"], commits_at_least(6)),
    Case("log-detached", "detached", ["log"], head_detached_ok),
    Case("log-single", "single", ["log"], all_of(commits_at_most(1), commits_at_least(1))),
    Case("log-empty", "empty", ["log"], error="no commits"),
    Case("log-notrepo", "notrepo", ["log"], error="git-sim error"),
    Case("log-conflict", "conflict", ["log", "--all"], commits_at_least(4)),
    # merge
    Case("merge", "classic", ["merge", "branch2"], all_of(title("git merge branch2"), merge_of("branch2"))),
    Case("merge-other", "classic", ["merge", "branch3"], merge_of("branch3")),
    Case("merge-already", "classic", ["merge", "branch1"], error="already included"),
    Case("merge-ff", "ff", ["merge", "branch1"], merge_of("branch1")),
    Case("merge-no-ff", "ff", ["merge", "--no-ff", "branch1"], all_of(after_commits(1), lambda m, r: all(len(c["parents"]) == 2 for c in commits_by_phase(m, "after").values()))),
    Case("merge-message", "classic", ["merge", "-m", "Bring in branch2", "branch2"], message_among_new("Bring in branch2")),
    Case("merge-criss-cross", "criss-cross", ["merge", M], merge_of(M)),
    Case("merge-into-feature", "rebase-ready", ["merge", "main"], merge_of("main")),
    Case("merge-missing", "classic", ["merge", "nope"], error="git-sim error"),
    # mv
    Case("mv", "history", ["mv", "config.yaml", "settings.yaml"], all_of(title("git mv"), lambda m, r: any(f["name"] == "settings.yaml" for f in m["files"]) and any(f["name"] == "config.yaml" for f in m["files"]))),
    Case("mv-missing", "history", ["mv", "nope.txt", "x.txt"], error="git-sim error"),
    Case("mv-no-args", "history", ["mv"], error="git-sim error"),
    # pull
    Case("pull-ff", "behind", ["pull", "origin", "main"], all_of(title("git pull"), after_commits(2), relabelled("main"))),
    Case("pull-default", "behind", ["pull"], after_commits(2)),
    Case("pull-diverged", "diverged", ["pull", "origin", "main"], after_commits(3)),
    Case("pull-no-remote", "classic", ["pull"], error="no remotes"),
    # push
    Case("push", "ahead", ["push", "origin", "main"], all_of(title("git push"), relabelled("origin/main"))),
    Case("push-default", "ahead", ["push"], relabelled("origin/main")),
    Case("push-set-upstream", "ahead", ["push", "-u", "origin", "main"], relabelled("origin/main")),
    Case("push-rejected", "diverged", ["push", "origin", "main"], texts("pull")),
    Case("push-force", "diverged", ["push", "--force", "origin", "main"], recolored(2)),
    Case("push-force-with-lease-stale", "diverged", ["push", "--force-with-lease", "origin", "main"], texts("force-with-lease")),
    Case("push-force-with-lease-fresh", "ahead", ["push", "--force-with-lease", "origin", "main"], relabelled("origin/main")),
    Case("push-no-remote", "classic", ["push"], error="git-sim error"),
    # rebase
    Case("rebase", "rebase-ready", ["rebase", "main"], all_of(title("git rebase main"), rebase_onto("main"))),
    Case("rebase-classic", "classic", ["rebase", "branch2"], rebase_onto("branch2")),
    Case("rebase-interactive", "rebase-ready", ["rebase", "-i", "main"], all_of(rebase_onto("main"), lambda m, r: m["steps"] >= 2)),
    Case("rebase-onto", "classic", ["rebase", "branch3", "--onto", "branch2"], lambda m, r: len(commits_by_phase(m, "after")) == min(o.count(r, "branch3..main"), N_DEFAULT)),
    Case("rebase-todo", "rebase-ready", ["rebase", "-i", "main", "--todo", "{todo}"], after_commits(1)),
    Case("rebase-already", "classic", ["rebase", "branch1"], error="git-sim error"),
    Case("rebase-missing", "classic", ["rebase", "nope"], error="git-sim error"),
    # reflog
    Case("reflog", "reflog", ["reflog"], all_of(title("git reflog"), reflog_labels())),
    Case("reflog-n", "reflog", ["reflog", "-n", "2"], reflog_labels(at_most=2)),
    Case("reflog-classic", "classic", ["reflog"], reflog_labels()),
    # remote
    Case("remote-list", "ahead", ["remote"], all_of(title("git remote"), texts("origin"))),
    Case("remote-add", "classic", ["remote", "add", "upstream", "https://github.com/example/up.git"], texts("upstream", "up.git")),
    Case("remote-remove", "ahead", ["remote", "remove", "origin"], texts("removed")),
    Case("remote-rename", "ahead", ["remote", "rename", "origin", "upstream"], texts("upstream")),
    Case("remote-set-url", "ahead", ["remote", "set-url", "origin", "git@example.com:x/y.git"], texts("x/y.git")),
    Case("remote-get-url", "ahead", ["remote", "get-url", "origin"], texts("origin")),
    Case("remote-none", "classic", ["remote"], texts("no remotes")),
    Case("remote-add-existing", "ahead", ["remote", "add", "origin", "x"], error="git-sim error"),
    Case("remote-remove-missing", "ahead", ["remote", "remove", "nope"], error="git-sim error"),
    # reset
    Case("reset-mixed", "classic", ["reset", "HEAD~2"], all_of(title("git reset"), reset_to("HEAD~2"))),
    Case("reset-hard", "classic", ["reset", "--hard", "HEAD~2"], reset_to("HEAD~2")),
    Case("reset-soft", "classic", ["reset", "--soft", "HEAD~1"], reset_to("HEAD~1")),
    Case("reset-mode", "classic", ["reset", "--mode", "hard", "HEAD~1"], reset_to("HEAD~1")),
    Case("reset-mixed-flag", "classic", ["reset", "--mixed", "HEAD~1"], reset_to("HEAD~1")),
    Case("reset-to-branch", "classic", ["reset", "--hard", "branch2"], relabelled("HEAD", "main")),
    Case("reset-tagged-safe", "history", ["reset", "--hard", "HEAD~1"], reset_to("HEAD~1")),
    Case("reset-path", "messy", ["reset", "HEAD", "models.py"], arrives("models.py", "working")),
    Case("reset-messy-hard", "messy", ["reset", "--hard"], title("git reset")),
    Case("reset-missing", "classic", ["reset", "nope"], error="git-sim error"),
    # restore
    Case("restore", "messy", ["restore", "README.md"], all_of(title("git restore"), lambda m, r: any(f["name"] == "README.md" for f in m["files"]))),
    Case("restore-staged", "messy", ["restore", "--staged", "models.py"], arrives("models.py", "working")),
    Case("restore-source", "messy", ["restore", "--source", "HEAD~1", "README.md"], texts("README.md")),
    Case("restore-source-missing", "messy", ["restore", "--source", "HEAD~1", "nope.txt"], error="git-sim error"),
    Case("restore-missing", "messy", ["restore", "nope.txt"], error="git-sim error"),
    Case("restore-all", "messy", ["restore"], title("git restore")),
    # revert
    Case("revert", "classic", ["revert", "HEAD~1"], all_of(title("git revert"), after_commits(1), lambda m, r: any(o.rev_parse(r, "HEAD") in c["parents"] for c in commits_by_phase(m, "after").values()))),
    Case("revert-older", "classic", ["revert", "HEAD~2"], after_commits(1)),
    Case("revert-no-commit", "classic", ["revert", "-n", "HEAD~1"], after_commits(0)),
    Case("revert-merge-needs-m", "classic", ["revert", "HEAD"], error="-m"),
    Case("revert-merge-mainline", "classic", ["revert", "-m", "1", "HEAD"], after_commits(1)),
    Case("revert-missing", "classic", ["revert", "nope"], error="git-sim error"),
    # rm
    Case("rm", "history", ["rm", "utils.py"], all_of(title("git rm"), gone("utils.py"))),
    Case("rm-two", "history", ["rm", "utils.py", "config.yaml"], gone("utils.py", "config.yaml")),
    Case("rm-untracked", "messy", ["rm", "scratch.txt"], error="git-sim error"),
    Case("rm-missing", "history", ["rm", "nope.txt"], error="git-sim error"),
    # stash
    Case("stash", "messy", ["stash"], all_of(title("git stash"), stashes_something)),
    Case("stash-push", "messy", ["stash", "push"], stashes_something),
    Case("stash-push-file", "messy", ["stash", "push", "README.md"], all_of(stashes_something, lambda m, r: files_in(m, "stash", "after") == ["README.md"])),
    Case("stash-pop", "messy", ["stash", "pop"], unstashes_something),
    Case("stash-apply", "messy", ["stash", "apply"], unstashes_something),
    Case("stash-list", "messy", ["stash", "list"], title("git stash list")),
    Case("stash-show", "messy", ["stash", "show"], title("git stash show")),
    Case("stash-show-index", "messy", ["stash", "show", "0"], title("git stash show")),
    Case("stash-drop", "messy", ["stash", "drop"], title("git stash drop")),
    Case("stash-clear", "messy", ["stash", "clear"], title("git stash clear")),
    Case("stash-pop-empty", "history", ["stash", "pop"], error="git-sim error"),
    Case("stash-drop-bad-index", "messy", ["stash", "drop", "7"], error="git-sim error"),
    Case("stash-push-missing", "messy", ["stash", "push", "nope.txt"], error="git-sim error"),
    Case("stash-nothing", "history", ["stash"], title("git stash")),
    # status
    Case("status", "messy", ["status"], all_of(title("git status"), status_matches)),
    Case("status-clean", "history", ["status"], status_matches),
    Case("status-conflict", "conflict", ["status"], title("git status")),
    Case("status-detached", "detached", ["status"], head_detached_ok),
    Case("status-empty", "empty", ["status"], title("git status")),
    # submodule
    Case("submodule-default", "submodule", ["submodule"], all_of(title("git submodule"), texts("lib"))),
    Case("submodule-status", "submodule", ["submodule", "status"], texts("lib")),
    Case("submodule-add", "history", ["submodule", "add", "https://github.com/example/lib.git", "vendor/lib"], texts("vendor/lib")),
    Case("submodule-init", "submodule", ["submodule", "init"], texts("lib")),
    Case("submodule-update-init", "submodule", ["submodule", "update", "--init"], texts("lib")),
    Case("submodule-deinit", "submodule", ["submodule", "deinit", "lib"], texts("lib")),
    Case("submodule-deinit-force", "submodule", ["submodule", "deinit", "--force", "lib"], texts("lib")),
    Case("submodule-deinit-missing", "submodule", ["submodule", "deinit", "nope"], error="git-sim error"),
    Case("submodule-add-no-url", "history", ["submodule", "add"], error="git-sim error"),
    # switch
    Case("switch", "classic", ["switch", "branch2"], all_of(title("git switch branch2"), relabelled("HEAD"))),
    Case("switch-create", "classic", ["switch", "-c", "topic"], ref_after("topic", "branch")),
    Case("switch-detach", "classic", ["switch", "--detach", "branch2"], relabelled("HEAD")),
    Case("switch-missing", "classic", ["switch", "nope"], error="git-sim error"),
    # tag
    Case("tag", "history", ["tag", "v9.9.9"], all_of(title("git tag v9.9.9"), ref_after("v9.9.9", "tag"))),
    Case("tag-commit", "history", ["tag", "v0.0.1", "HEAD~3"], ref_after("v0.0.1", "tag")),
    Case("tag-delete", "history", ["tag", "-d", "v1.1.0"], ref_removed("v1.1.0")),
    Case("tag-delete-older", "history", ["tag", "-d", "v1.0.0"], ref_removed("v1.0.0"), globals_=["-n", "20"]),
    Case("tag-existing", "history", ["tag", "v1.0.0"], error="git-sim error"),
    Case("tag-delete-missing", "history", ["tag", "-d", "nope"], error="git-sim error"),
    # worktree
    Case("worktree-list", "worktree", ["worktree", "list"], all_of(title("git worktree"), texts(M))),
    Case("worktree-add", "worktree", ["worktree", "add", "../hotfix", "main"], texts("hotfix")),
    Case("worktree-add-new-branch", "worktree", ["worktree", "add", "-b", "topic", "../topic-wt"], texts("topic")),
    Case("worktree-remove", "worktree", ["worktree", "remove", "{worktree_path}"], texts("remove")),
    Case("worktree-remove-force", "worktree", ["worktree", "remove", "--force", "{worktree_path}"], title("git worktree")),
    Case("worktree-prune", "worktree", ["worktree", "prune"], title("git worktree")),
    Case("worktree-remove-missing", "worktree", ["worktree", "remove", "../nope"], error="git-sim error"),
    # clone (runs in a plain folder; the URL is the ahead shape's remote)
    Case("clone", "notrepo", ["clone", "{remote_url}"], all_of(title("git clone"), texts("cloned"))),
    Case("clone-bad-url", "notrepo", ["clone", "not-a-url"], error="git-sim error"),
    # not a repository / bare
    Case("status-notrepo", "notrepo", ["status"], error="git-sim error"),
    Case("log-bare", "bare", ["log"], error="git-sim error"),
    # the large shape: a smoke test of layout at scale
    Case("log-large", "large", ["log", "--all", "-n", "30"], commits_at_least(30), slow=True),
    Case("status-large", "large", ["status"], title("git status"), slow=True),
]

TODO_FILE = "pick {c1}\nsquash {c2}\n"
