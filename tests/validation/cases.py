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


def ref_before(name):
    def check(m, repo):
        assert name in m["refs"], f"no label {name!r} ({sorted(m['refs'])})"
        assert m["refs"][name]["phase"] == "before", f"{name!r} should be there from the start (phase before)"
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


def ignored_by_git(ignored=(), not_ignored=()):
    """The drawing's verdicts agree with git check-ignore run on its own."""
    def check(m, repo):
        for p in ignored:
            assert o.check_ignored(repo, p), f"git says {p!r} is not ignored"
            assert has_text(m, p), f"path {p!r} not drawn"
        for p in not_ignored:
            assert not o.check_ignored(repo, p), f"git says {p!r} is ignored"
            assert has_text(m, p), f"path {p!r} not drawn"
    return check


def no_text(*needles):
    def check(m, repo):
        for n in needles:
            assert not has_text(m, n), f"did not expect text {n!r} in the drawing"
    return check


def commit_count(n):
    def check(m, repo):
        assert len(m["commits"]) == n, f"drew {len(m['commits'])} commits, {n} expected"
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


def stack_of_entries(m, repo):
    """list / show / drop / clear draw the stash as cards, one per entry,
    labeled stash@{n}: no stash entry appears as a commit in the graph."""
    shas = o.git(repo, "stash", "list", "--format=%H").split()
    assert not set(shas) & set(m["commits"]), "stash entries should not be drawn as commits"
    for i in range(min(len(shas), 5)):
        assert f"stash@{{{i}}}" in m["refs"], f"no card labeled stash@{{{i}}} ({sorted(m['refs'])})"

def stashes_untracked(m, repo):
    """stash -u: every untracked file goes into the stash too."""
    untracked = [f for f in o.git(repo, "ls-files", "--others", "--exclude-standard").split() if "git-sim_media" not in f]
    got = files_in(m, "stash", "after")
    missing = [f for f in untracked if f not in got]
    assert not missing, f"untracked files not stashed: {missing} (stash: {got})"


def discards(*names):
    """restore / checkout -- <paths>: exactly the files git would reset from
    the staging area land in "Discarded changes"."""
    def check(m, repo):
        got = sorted(f["name"] for f in m["files"] if "discarded" in f["column"].lower() and f["phase"] == "after")
        assert got == sorted(names), f"discarded {got}, expected {sorted(names)}"
    return check


def restores_from(rev, name, zone):
    """restore --source REV: the commit is highlighted and labeled, and the
    file arrives from its column in the working directory or staging area."""
    def check(m, repo):
        sha = o.rev_parse(repo, rev)
        assert sha in m["commits"] and m["commits"][sha]["recolored"], f"{rev} ({sha[:7]}) is not highlighted"
        ref_after("source")(m, repo)
        assert name in table_column(m, f"from {sha[:7]}"), f"{name} is not listed as coming from {sha[:7]}"
        arrives(name, zone)(m, repo)
    return check


def reverts(*revs, commits=True):
    """revert of several commits: each is highlighted, and one revert commit
    per reverted commit follows HEAD (none with -n)."""
    def check(m, repo):
        shas = [o.rev_parse(repo, r) for r in revs]
        for r, s in zip(revs, shas):
            assert s in m["commits"] and m["commits"][s]["recolored"], f"{r} ({s[:7]}) is not marked"
        after_commits(len(shas) if commits else 0)(m, repo)
        if commits:
            drawn = sorted(c["message"] for c in commits_by_phase(m, "after").values())
            assert drawn == sorted(f"Revert {s[:6]}" for s in shas), f"revert commits {drawn}"
    return check


def untracks(name):
    """rm --cached: the file turns untracked and its deletion is staged."""
    def check(m, repo):
        assert files_in(m, "untracked", "after") == [name], f"{name} should turn untracked ({m['files']})"
        assert name in files_in(m, "staging", "after"), f"{name}'s deletion should be staged"
    return check


def squashes(branch):
    """merge --squash: the branch's changes since the merge base arrive staged, and no commit is made."""
    def check(m, repo):
        expected = [f for f in o.git(repo, "diff", "--name-only", f"HEAD...{branch}").split() if "git-sim_media" not in f]
        same_files(files_in(m, "staging", "after"), expected)
        assert not commits_by_phase(m, "after"), "merge --squash makes no commit"
    return check


def merge_committed(m, repo):
    """merge --continue: one new commit whose parents are HEAD and MERGE_HEAD."""
    merge_head = o.rev_parse(repo, "MERGE_HEAD")
    new = commits_by_phase(m, "after")
    assert len(new) == 1, f"one merge commit expected, drew {len(new)}"
    (c,) = new.values()
    assert set(c["parents"]) == {o.rev_parse(repo, "HEAD"), merge_head}, f"parents {c['parents']}"


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
        drawn = [c["message"] for c in commits_by_phase(m, "after").values()]
        # the drawing keeps the first 40 characters of a message
        assert any(d == text or (len(d) >= 40 and text.startswith(d)) for d in drawn), f"no simulated commit with message {text!r}; drew {drawn}"
    return check


def recolored(n):
    def check(m, repo):
        got = sum(1 for c in m["commits"].values() if c["recolored"])
        assert got == n, f"{got} gold commits, expected {n}"
    return check


def table_column(m, keyword):
    """Entries of the zone-table column whose title contains ``keyword``."""
    return sorted(f["name"] for f in m["files"] if keyword.lower() in f["column"].lower())


MAX_TABLE_ROWS = 14  # show / diff / blame list at most this many rows, then "..."


def same_files(drawn, expected):
    drawn = [d for d in drawn if d != "..."]
    assert set(drawn) <= set(expected), f"drew {sorted(set(drawn) - set(expected))} that git doesn't list"
    assert len(drawn) == min(len(expected), MAX_TABLE_ROWS), f"drew {len(drawn)} file(s), git lists {len(expected)}"


def shows(rev):
    """git show REV: the commit is highlighted and the table holds the files
    its first-parent diff touches, as git itself lists them."""
    def check(m, repo):
        sha = o.rev_parse(repo, f"{rev}^{{commit}}")
        assert sha in m["commits"] and m["commits"][sha]["recolored"], f"{rev} ({sha[:7]}) is not highlighted"
        parents = o.parents(repo, sha)
        base = [parents[0]] if parents else ["--root"]
        if parents:
            names = o.git(repo, "diff", "--name-only", "-M", parents[0], sha).split()
        else:
            names = o.git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "-M", sha).split()
        del base
        same_files(table_column(m, "files in"), names)
    return check


def diffs(*git_args):
    """git diff ARGS: the changed-file column holds what git diff --name-only lists."""
    def check(m, repo):
        names = o.git(repo, "diff", "--name-only", "-M", *git_args).split()
        names = [n for n in names if "git-sim_media" not in n]
        same_files(table_column(m, "changes"), names)
    return check


def blames(path, lines=None):
    """git blame PATH: every commit git names (and that is drawn) is highlighted,
    and no other commit is."""
    def check(m, repo):
        args = ["blame", "--porcelain"] + (["-L", lines] if lines else []) + ["--", path]
        shas = {l.split()[0] for l in o.git(repo, *args).splitlines() if len(l) > 40 and l[40] == " " and all(c in "0123456789abcdef" for c in l[:40])}
        shas.discard("0" * 40)
        lit = {s for s, c in m["commits"].items() if c["recolored"]}
        assert lit <= shas, f"highlighted {sorted(s[:7] for s in lit - shas)} that git blame doesn't name"
        assert lit, "no blamed commit highlighted"
    return check


def lit(m):
    return {s for s, c in m["commits"].items() if c["recolored"]}


def logs(*git_args):
    """git log ARGS: exactly the drawn commits git log lists are highlighted,
    and the card says how many it lists."""
    def check(m, repo):
        listed = o.git(repo, "log", "--format=%H", *git_args).split()
        drawn = lit(m)
        assert drawn == set(listed) & set(m["commits"]), f"highlighted {sorted(s[:7] for s in drawn)}, git log lists {[s[:7] for s in listed]}"
        assert drawn or not listed, "git log lists commits but none is drawn highlighted"
        count = f"{len(listed)} commit" if listed else "No commits"
        assert has_text(m, count), f"expected {count!r} in the card"
    return check


def shortlogs(rev):
    """git shortlog REV: every drawn commit it counts takes its author's
    color, no other does, and each author is named with their count."""
    def check(m, repo):
        counted = o.git(repo, "rev-list", rev, "--").split()
        assert lit(m) == set(counted) & set(m["commits"]), "the counted commits are the colored ones"
        authors = {}
        for name in o.git(repo, "log", "--format=%aN", rev, "--").splitlines():
            authors[name] = authors.get(name, 0) + 1
        for name, count in sorted(authors.items(), key=lambda kv: -kv[1])[:8]:
            assert has_text(m, name), f"author {name!r} not named"
            assert has_text(m, str(count))
    return check


def greps(*git_args, rev=None):
    """git grep ARGS: the card's files are ones git grep lists, and at least
    one is drawn when it lists any."""
    def check(m, repo):
        out = o.git(repo, "grep", "-l", *git_args, check=False)
        names = [n.split(":", 1)[1] if rev else n for n in out.splitlines() if n]
        drawn = table_column(m, "match")
        assert set(drawn) <= set(names), f"drew {sorted(set(drawn) - set(names))} that git grep doesn't list"
        assert bool(drawn) == bool(names), f"git grep lists {names}, drew {drawn}"
    return check


def describes(*git_args):
    """git describe ARGS: git's name is in the drawing, and the highlighted
    commits are the tagged one and the drawn ones since it."""
    def check(m, repo):
        import re as _re

        name = o.git(repo, "describe", *git_args)
        assert has_text(m, name), f"git describe says {name!r}; not in the drawing"
        target = git_args[-1] if git_args and not git_args[-1].startswith("-") else "HEAD"
        tag = _re.sub(r"-\d+-g[0-9a-f]+$", "", name)
        tagged = o.rev_parse(repo, f"refs/tags/{tag}")
        since = set(o.git(repo, "rev-list", f"{tagged}..{o.rev_parse(repo, target)}").split())
        assert lit(m) == (since | {tagged}) & set(m["commits"]), "highlighted commits differ from the tag and the commits since"
        assert tagged in m["commits"], "the tagged commit is not drawn"
    return check


def bisect_next(bad="refs/bisect/bad", goods=None):
    """The commit git bisect checks out next, from git's own rev-list --bisect,
    is named in the drawing and HEAD moves to it."""
    def check(m, repo):
        good_refs = goods if goods is not None else [
            r for r in o.git(repo, "for-each-ref", "--format=%(refname)", "refs/bisect/").split() if "/good-" in r
        ]
        # --bisect-vars, not --bisect: with a session in progress, --bisect also
        # pulls in refs/bisect/* on its own, which would be the old marks
        out = o.git(repo, "rev-list", "--bisect-vars", bad, *[f"^{g}" for g in good_refs])
        expected = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)["bisect_rev"].strip("'")
        assert has_text(m, f"HEAD moves to {expected[:7]}"), f"expected git's pick {expected[:7]} in the drawing"
        relabelled("HEAD")(m, repo)
    return check


def bisect_next_after(word):
    """In the 'bisecting' shape: mark HEAD good or bad, then git's next pick."""
    def check(m, repo):
        goods = [r for r in o.git(repo, "for-each-ref", "--format=%(refname)", "refs/bisect/").split() if "/good-" in r]
        bad = "refs/bisect/bad"
        if word == "good":
            goods = goods + ["HEAD"]
        else:
            bad = "HEAD"
        bisect_next(bad, goods)(m, repo)
    return check


def lists_filtered(*git_args):
    """git branch --merged / --no-merged: the card says git lists as many
    branches as git itself prints for the same filter."""
    def check(m, repo):
        out = o.git(repo, "branch", *git_args)
        n = len([line for line in out.splitlines() if line.strip()])
        assert has_text(m, f"git lists the {n} highlighted"), f"expected git's {n} branch(es) highlighted"
    return check


def lists_every_branch(remotes=False):
    """git branch [-a]: every branch git prints is named in the card."""
    def check(m, repo):
        refs = ["refs/heads"] + (["refs/remotes"] if remotes else [])
        for ref in o.git(repo, "for-each-ref", "--format=%(refname)", *refs).split():
            if ref.endswith("/HEAD"):
                continue
            name = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else "remotes/" + ref[len("refs/remotes/"):]
            assert name in m["texts"], f"branch {name!r} missing from the listing"
    return check


def tracks(branch, upstream):
    """branch -u: the card shows the [branch "x"] lines git writes, and the
    branch's label says how far ahead/behind the upstream it is."""
    def check(m, repo):
        ahead, behind = o.git(repo, "rev-list", "--left-right", "--count", f"{branch}...{upstream}").split()
        parts = [p for p, k in ((f"ahead {ahead}", ahead), (f"behind {behind}", behind)) if k != "0"]
        relation = f"[{upstream}{': ' + ', '.join(parts) if parts else ''}]"
        ref_after(relation, "upstream")(m, repo)
        assert has_text(m, f'[branch "{branch}"]'), f"no [branch \"{branch}\"] section drawn"
    return check


def tags_matching(pattern):
    import fnmatch

    def check(m, repo):
        n = len([t for t in o.tags(repo) if fnmatch.fnmatchcase(t, pattern)])
        assert has_text(m, f"git lists the {n} highlighted"), f"expected {n} tag(s) matching {pattern!r}"
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
    Case("branch-list", "history", ["branch"], all_of(title("git branch"), lists_every_branch(), texts("* marks main"))),
    Case("branch-list-all-vv", "remote-branch", ["branch", "-a", "-vv"], all_of(title("git branch -a -vv"), lists_every_branch(remotes=True), texts("[origin/main: ahead 2]"))),
    Case("branch-list-all-verbose", "remote-branch", ["branch", "--all", "--verbose"], all_of(lists_every_branch(remotes=True), texts("[ahead 2]"))),
    Case("branch-merged", "history", ["branch", "--merged"], all_of(title("git branch --merged"), lists_filtered("--merged"))),
    Case("branch-no-merged", "classic", ["branch", "--no-merged", "branch3"], all_of(title("git branch --no-merged branch3"), lists_filtered("--no-merged", "branch3"))),
    Case("branch-merged-and-no-merged", "classic", ["branch", "--merged", "--no-merged"], error="git-sim error"),
    Case("branch-list-with-name", "classic", ["branch", "-v", "topic"], error="git-sim error"),
    Case("branch-set-upstream", "remote-branch", ["branch", "-u", "origin/old-idea"], all_of(title("git branch -u origin/old-idea"), tracks("main", "origin/old-idea"), texts("merge = refs/heads/old-idea"))),
    Case("branch-set-upstream-local", "classic", ["branch", "--set-upstream-to=main", "branch1"], all_of(tracks("branch1", "main"), texts("remote = ."))),
    Case("branch-set-upstream-missing", "classic", ["branch", "-u", "origin/nope"], error="does not exist"),
    # checkout
    Case("checkout-branch", "classic", ["checkout", "branch2"], all_of(title("git checkout branch2"), relabelled("HEAD"))),
    Case("checkout-new", "classic", ["checkout", "-b", "topic"], ref_after("topic", "branch")),
    Case("checkout-tag", "release", ["checkout", "v1.0.0"], relabelled("HEAD")),
    Case("checkout-commit", "classic", ["checkout", "HEAD~2"], relabelled("HEAD")),
    Case("checkout-missing", "classic", ["checkout", "nope"], error="git-sim error"),
    Case("checkout-current", "classic", ["checkout", "main"], error="already on"),
    # the older spelling of restore: after --, paths whose changes are discarded
    Case("checkout-paths", "messy", ["checkout", "--", "README.md"], all_of(title("git checkout -- README.md"), discards("README.md"))),
    Case("checkout-paths-dot", "messy", ["checkout", "--", "."], all_of(title("git checkout -- ."), discards("README.md", "app.py"))),
    Case("checkout-path-no-dashes", "messy", ["checkout", "app.py"], all_of(title("git checkout -- app.py"), discards("app.py"))),
    Case("checkout-paths-from-commit", "messy", ["checkout", "HEAD~1", "--", "app.py"], error="isn't simulated"),
    Case("checkout-paths-unmodified", "messy", ["checkout", "--", "routes.py"], error="No modified file"),
    # cherry-pick
    Case("cherry-pick-branch", "classic", ["cherry-pick", "branch2"], all_of(title("git cherry-pick"), picks(1))),
    Case("cherry-pick-sha", "classic", ["cherry-pick", "branch3~1"], picks(1)),
    Case("cherry-pick-range", "classic", ["cherry-pick", "branch2~2..branch2"], picks(2)),
    Case("cherry-pick-edit", "classic", ["cherry-pick", "branch2", "-e", "Picked with a new message"], all_of(picks(1), message_among_new("Picked with a new message"))),
    Case("cherry-pick-no-commit", "classic", ["cherry-pick", "branch2", "-n"], after_commits(0)),
    Case("cherry-pick-missing", "classic", ["cherry-pick", "nope"], error="git-sim error"),
    Case("cherry-pick-abort", "picking", ["cherry-pick", "--abort"], all_of(texts("Calls off the cherry-pick"), after_commits(0))),
    Case("cherry-pick-continue", "picking-resolved", ["cherry-pick", "--continue"], all_of(texts("Commits the picked change"), after_commits(1))),
    Case("cherry-pick-skip", "picking", ["cherry-pick", "--skip"], texts("Drops the commit that conflicted")),
    Case("cherry-pick-continue-none", "classic", ["cherry-pick", "--continue"], error="No cherry-pick in progress"),
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
    # --global: the suite's private config file (GIT_CONFIG_GLOBAL) is the global scope
    Case("config-global-set", "history", ["config", "--global", "core.editor", "code --wait"], all_of(title("git config --global core.editor"), texts("~/.gitconfig", "global", "editor = code --wait"))),
    Case("config-global-change", "history", ["config", "--global", "user.email", "me@example.com"], texts("email = validation@example.com", "email = me@example.com")),
    Case("config-global-get", "history", ["config", "--global", "user.email"], texts("~/.gitconfig", "validation@example.com")),
    Case("config-global-list", "history", ["config", "--list", "--global"], all_of(title("git config --list --global"), texts("~/.gitconfig", "[user]"))),
    Case("config-global-none", "history", ["config", "--global"], error="git-sim error"),
    # fetch
    Case("fetch", "behind", ["fetch", "origin", "main"], all_of(title("git fetch"), after_commits(2), relabelled("origin/main"))),
    Case("fetch-default", "behind", ["fetch"], after_commits(2)),
    Case("fetch-up-to-date", "ahead", ["fetch", "origin", "main"], after_commits(0)),
    Case("fetch-no-remote", "classic", ["fetch"], error="no remotes"),
    Case("fetch-prune", "stale-remote", ["fetch", "--prune"], all_of(title("git fetch --prune"), texts("Pruned origin/gone"), ref_removed("origin/gone"))),
    Case("fetch-stale-note", "stale-remote", ["fetch", "-p", "origin", "main"], texts("Pruned origin/gone")),
    # --all: every remote, and a line for what each brought
    Case("fetch-all", "remote-moved", ["fetch", "--all"], all_of(title("git fetch --all"), relabelled("origin/main"), ref_after("origin/fresh"), ref_after("upstream/main"), texts("origin: 2 new commits", "upstream:", "origin/old-idea no longer exists"))),
    Case("fetch-all-prune", "remote-moved", ["fetch", "--all", "--prune"], all_of(title("git fetch --all --prune"), ref_removed("origin/old-idea"))),
    Case("fetch-all-up-to-date", "ahead", ["fetch", "--all"], all_of(after_commits(0), texts("origin: nothing new"))),
    Case("fetch-all-with-remote", "remote-moved", ["fetch", "--all", "origin"], error="takes no remote"),
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
    # log's filters: the graph stays, the commits git lists are highlighted
    Case("log-oneline-graph", "history", ["log", "--oneline", "--graph"], all_of(title("git log --oneline --graph"), recolored(0))),
    Case("log-path", "history", ["log", "--", "app.py"], all_of(title("git log -- app.py"), logs("HEAD", "--", "app.py"))),
    Case("log-path-n", "history", ["log", "-n", "2", "app.py"], logs("-n2", "HEAD", "--", "app.py")),
    Case("log-author", "history", ["log", "--author", "Ada"], logs("--author=Ada", "HEAD")),
    Case("log-since-until", "history", ["log", "--since", "2024-03-02T12:00", "--until", "2024-03-02T16:30"], logs("--since=2024-03-02T12:00", "--until=2024-03-02T16:30", "HEAD")),
    Case("log-after-before", "history", ["log", "--all", "--after", "2024-03-02T14:00", "--before", "2024-03-02T18:00"], logs("--after=2024-03-02T14:00", "--before=2024-03-02T18:00", "--all")),
    Case("log-pickaxe", "history", ["log", "-S", "pagination"], all_of(texts('added or removed "pagination"'), logs("-S", "pagination", "HEAD"))),
    Case("log-patch", "history", ["log", "-p", "--", "app.py"], all_of(texts("The patch of"), logs("HEAD", "--", "app.py"))),
    Case("log-patch-long", "history", ["log", "--patch"], texts("The patch of")),
    Case("log-follow", "renamed", ["log", "--follow", "server.py"], all_of(texts("following its rename from app.py"), logs("--follow", "HEAD", "--", "server.py"))),
    Case("log-renamed-no-follow", "renamed", ["log", "server.py"], all_of(texts("--follow goes further back"), logs("HEAD", "--", "server.py"))),
    Case("log-no-match", "history", ["log", "--author", "Nobody"], texts("No commits by Nobody")),
    Case("log-follow-two", "history", ["log", "--follow", "app.py", "models.py"], error="exactly one"),
    Case("log-path-missing", "history", ["log", "--", "nope.py"], error="git-sim error"),
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
    Case("merge-squash", "rebase-ready", ["merge", "--squash", "main"], all_of(title("git merge --squash main"), squashes("main"))),
    Case("merge-squash-no-ff", "rebase-ready", ["merge", "--squash", "--no-ff", "main"], error="cannot combine"),
    Case("merge-abort", "merging", ["merge", "--abort"], all_of(title("git merge --abort"), texts("Calls off the merge"), after_commits(0))),
    Case("merge-continue", "merging-resolved", ["merge", "--continue"], merge_committed),
    Case("merge-continue-unresolved", "merging", ["merge", "--continue"], error="still have conflicts"),
    Case("merge-abort-none", "history", ["merge", "--abort"], error="no merge in progress"),
    Case("merge-default-message", "classic", ["merge", "branch2"], message_among_new("Merge branch 'branch2'")),
    Case("merge-ff-only", "ff", ["merge", "--ff-only", "branch1"], merge_of("branch1")),
    Case("merge-ff-only-diverged", "classic", ["merge", "--ff-only", "branch2"], error="Not possible to fast-forward"),
    Case("merge-ff-only-no-ff", "ff", ["merge", "--ff-only", "--no-ff", "branch1"], error="cannot combine"),
    Case("merge-unrelated", "orphan", ["merge", "gh-pages"], error="refusing to merge unrelated histories"),
    Case("merge-allow-unrelated", "orphan", ["merge", "--allow-unrelated-histories", "gh-pages"], merge_of("gh-pages")),
    # a remote-tracking branch that has diverged: merged (conflict check included) and rebased onto
    Case("merge-remote-tracking", "diverged-fetched", ["merge", "origin/main"], all_of(merge_of("origin/main"), message_among_new("Merge remote-tracking branch 'origin/main'"))),
    # mv
    Case("mv", "history", ["mv", "config.yaml", "settings.yaml"], all_of(title("git mv"), lambda m, r: any(f["name"] == "settings.yaml" for f in m["files"]) and any(f["name"] == "config.yaml" for f in m["files"]))),
    Case("mv-missing", "history", ["mv", "nope.txt", "x.txt"], error="git-sim error"),
    Case("mv-no-args", "history", ["mv"], error="git-sim error"),
    # pull
    Case("pull-ff", "behind", ["pull", "origin", "main"], all_of(title("git pull"), after_commits(2), relabelled("main"))),
    Case("pull-default", "behind", ["pull"], after_commits(2)),
    Case("pull-diverged", "diverged", ["pull", "origin", "main"], after_commits(3)),
    Case("pull-no-remote", "classic", ["pull"], error="no remotes"),
    Case("pull-rebase", "diverged", ["pull", "--rebase", "origin", "main"], all_of(title("git pull --rebase"), texts("replayed on top of what was fetched"), lambda m, r: not any(len(c["parents"]) == 2 for c in commits_by_phase(m, "after").values()))),
    Case("pull-rebase-short", "behind", ["pull", "-r"], texts("fast-forwards")),
    # push
    Case("push", "ahead", ["push", "origin", "main"], all_of(title("git push"), relabelled("origin/main"))),
    Case("push-default", "ahead", ["push"], relabelled("origin/main")),
    Case("push-set-upstream", "ahead", ["push", "-u", "origin", "main"], relabelled("origin/main")),
    Case("push-rejected", "diverged", ["push", "origin", "main"], texts("pull")),
    Case("push-force", "diverged", ["push", "--force", "origin", "main"], recolored(2)),
    Case("push-force-with-lease-stale", "diverged", ["push", "--force-with-lease", "origin", "main"], texts("force-with-lease")),
    Case("push-force-with-lease-fresh", "ahead", ["push", "--force-with-lease", "origin", "main"], relabelled("origin/main")),
    Case("push-no-remote", "classic", ["push"], error="git-sim error"),
    Case("push-delete", "remote-branch", ["push", "origin", "--delete", "old-idea"], all_of(texts("Deletes old-idea on origin"), ref_removed("origin/old-idea"))),
    Case("push-delete-short", "remote-branch", ["push", "origin", "-d", "old-idea"], texts("Deletes old-idea")),
    Case("push-delete-missing", "remote-branch", ["push", "origin", "--delete", "nope"], error="does not exist"),
    Case("push-tags", "new-tag", ["push", "--tags"], all_of(texts("Pushes 1 tag(s) origin doesn't have: v9.9"), ref_after("on origin"))),
    Case("push-tag", "new-tag", ["push", "origin", "v9.9"], all_of(title("git push origin v9.9"), texts("Pushes tag v9.9 to origin", "The 2 commit(s) it reaches"), ref_after("on origin"))),
    Case("push-tag-present", "remote-tag", ["push", "origin", "v0.9"], all_of(texts("origin already has tag v0.9"), ref_before("on origin"))),
    Case("push-tag-missing", "new-tag", ["push", "origin", "refs/tags/nope"], error="no tag"),
    Case("push-delete-tag", "remote-tag", ["push", "origin", "--delete", "v0.9"], all_of(texts("Deletes tag v0.9 on origin", "Your local tag v0.9 is kept"), ref_removed("on origin"), ref_after("deleted on origin", "deleted tag"))),
    Case("push-delete-remote-only-tag", "remote-tag", ["push", "origin", "-d", "refs/tags/v0.8"], all_of(texts("You have no local tag v0.8"), ref_before("v0.8"), ref_after("deleted on origin"))),
    # rebase
    Case("rebase", "rebase-ready", ["rebase", "main"], all_of(title("git rebase main"), rebase_onto("main"))),
    Case("rebase-classic", "classic", ["rebase", "branch2"], rebase_onto("branch2")),
    Case("rebase-interactive", "rebase-ready", ["rebase", "-i", "main"], all_of(rebase_onto("main"), lambda m, r: m["steps"] >= 2)),
    Case("rebase-onto", "classic", ["rebase", "branch3", "--onto", "branch2"], lambda m, r: len(commits_by_phase(m, "after")) == min(o.count(r, "branch3..main"), N_DEFAULT)),
    Case("rebase-todo", "rebase-ready", ["rebase", "-i", "main", "--todo", "{todo}"], after_commits(1)),
    Case("rebase-already", "classic", ["rebase", "branch1"], error="is up to date"),
    Case("rebase-remote-tracking", "diverged-fetched", ["rebase", "origin/main"], rebase_onto("origin/main")),
    Case("rebase-missing", "classic", ["rebase", "nope"], error="git-sim error"),
    Case("rebase-abort", "rebasing", ["rebase", "--abort"], all_of(title("git rebase --abort"), texts("Calls off the rebase"), relabelled("HEAD"))),
    Case("rebase-continue", "rebasing-resolved", ["rebase", "--continue"], all_of(texts("the rebase is done"), after_commits(1))),
    Case("rebase-skip", "rebasing", ["rebase", "--skip"], all_of(texts("Drops the commit that conflicted"), after_commits(0))),
    Case("rebase-continue-none", "history", ["rebase", "--continue"], error="No rebase in progress"),
    Case("rebase-abort-with-branch", "rebasing", ["rebase", "main", "--abort"], error="takes no other arguments"),
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
    Case("remote-verbose", "remote-moved", ["remote", "-v"], all_of(title("git remote -v"), texts("../remote_moved.push.git", "../remote_moved.origin.git"))),
    Case("remote-verbose-long", "ahead", ["remote", "--verbose"], all_of(title("git remote -v"), texts("push", "fetch"))),
    Case("remote-show", "remote-moved", ["remote", "show", "origin"], all_of(title("git remote show origin"), texts("new: the next fetch stores it as origin/fresh", "stale: deleted on origin", "tracked as origin/main", "merges with main", "pushes to feature (fast-forwardable)", "pushes to main (local out of date)"))),
    Case("remote-show-fresh", "ahead", ["remote", "show", "origin"], texts("tracked as origin/main", "pushes to main (fast-forwardable)")),
    Case("remote-show-missing", "ahead", ["remote", "show", "nope"], error="doesn't exist"),
    # ls-remote: the remote's refs beside the copies here
    Case("ls-remote", "remote-moved", ["ls-remote"], all_of(title("git ls-remote"), texts("not fetched yet", "deleted on origin", "you're 1 ahead: push sends it", "moved on since your last fetch", "only here: push --tags sends it"))),
    Case("ls-remote-heads", "remote-moved", ["ls-remote", "--heads", "origin"], all_of(title("git ls-remote --heads origin"), texts("fresh"), no_text("only here", "tags"))),
    Case("ls-remote-branches", "behind", ["ls-remote", "--branches"], texts("moved on since your last fetch")),
    Case("ls-remote-tags", "remote-moved", ["ls-remote", "-t"], all_of(title("git ls-remote --tags"), texts("v0.9"), no_text("not fetched yet", "branches"))),
    Case("ls-remote-upstream", "remote-moved", ["ls-remote", "upstream"], texts("not fetched yet")),
    Case("ls-remote-up-to-date", "ahead", ["ls-remote"], texts("you're 2 ahead: push sends them")),
    Case("ls-remote-no-remote", "classic", ["ls-remote"], error="no remotes"),
    Case("ls-remote-unreachable", "remote-moved", ["ls-remote", "../no-such-repo.git"], error="could not list the refs"),
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
    Case("restore-missing", "messy", ["restore", "nope.txt"], error="git-sim error"),
    Case("restore-all", "messy", ["restore"], title("git restore")),
    Case("restore-dot", "messy", ["restore", "."], all_of(title("git restore ."), discards("README.md", "app.py"))),
    Case("restore-source", "messy", ["restore", "--source", "HEAD~2", "utils.py"], all_of(title("git restore --source HEAD~2 utils.py"), restores_from("HEAD~2", "utils.py", "working"))),
    Case("restore-source-staged", "messy", ["restore", "-s", "HEAD~3", "--staged", "app.py"], restores_from("HEAD~3", "app.py", "staging")),
    Case("restore-source-missing", "messy", ["restore", "--source", "nope", "app.py"], error="not a valid Git ref"),
    Case("restore-source-unchanged", "messy", ["restore", "-s", "HEAD", "routes.py"], error="nothing to restore"),
    # revert
    Case("revert", "classic", ["revert", "HEAD~1"], all_of(title("git revert"), after_commits(1), lambda m, r: any(o.rev_parse(r, "HEAD") in c["parents"] for c in commits_by_phase(m, "after").values()))),
    Case("revert-older", "classic", ["revert", "HEAD~2"], after_commits(1)),
    Case("revert-no-commit", "classic", ["revert", "-n", "HEAD~1"], after_commits(0)),
    Case("revert-merge-needs-m", "classic", ["revert", "HEAD"], error="-m"),
    Case("revert-merge-mainline", "classic", ["revert", "-m", "1", "HEAD"], after_commits(1)),
    Case("revert-missing", "classic", ["revert", "nope"], error="git-sim error"),
    Case("revert-several", "linear", ["revert", "HEAD~1", "HEAD~3"], all_of(title("git revert HEAD~1 HEAD~3"), reverts("HEAD~1", "HEAD~3"))),
    Case("revert-range", "linear", ["revert", "HEAD~4..HEAD~1"], reverts("HEAD~1", "HEAD~2", "HEAD~3")),
    Case("revert-several-no-commit", "linear", ["revert", "-n", "HEAD", "HEAD~2"], all_of(reverts("HEAD", "HEAD~2", commits=False), lambda m, r: same_files(table_column(m, "changes staged"), ["main.10", "main.8"]))),
    Case("revert-empty-range", "linear", ["revert", "HEAD..HEAD"], error="contains no commits"),
    # rm
    Case("rm", "history", ["rm", "utils.py"], all_of(title("git rm"), gone("utils.py"))),
    Case("rm-two", "history", ["rm", "utils.py", "config.yaml"], gone("utils.py", "config.yaml")),
    Case("rm-untracked", "messy", ["rm", "scratch.txt"], error="git-sim error"),
    Case("rm-missing", "history", ["rm", "nope.txt"], error="git-sim error"),
    Case("rm-cached", "history", ["rm", "--cached", "utils.py"], all_of(title("git rm --cached utils.py"), untracks("utils.py"), texts("stays on disk"))),
    # stash
    Case("stash", "messy", ["stash"], all_of(title("git stash"), stashes_something)),
    Case("stash-push", "messy", ["stash", "push"], stashes_something),
    Case("stash-push-file", "messy", ["stash", "push", "README.md"], all_of(stashes_something, lambda m, r: files_in(m, "stash", "after") == ["README.md"])),
    Case("stash-pop", "messy", ["stash", "pop"], unstashes_something),
    Case("stash-apply", "messy", ["stash", "apply"], unstashes_something),
    Case("stash-list", "messy", ["stash", "list"], all_of(title("git stash list"), stack_of_entries)),
    Case("stash-show", "messy", ["stash", "show"], title("git stash show")),
    Case("stash-show-index", "messy", ["stash", "show", "0"], title("git stash show")),
    Case("stash-drop", "messy", ["stash", "drop"], all_of(title("git stash drop"), stack_of_entries, ref_removed("stash@{0}"))),
    Case("stash-clear", "messy", ["stash", "clear"], all_of(title("git stash clear"), stack_of_entries, texts("The stash is empty"))),
    Case("stash-pop-empty", "history", ["stash", "pop"], error="git-sim error"),
    Case("stash-drop-bad-index", "messy", ["stash", "drop", "7"], error="git-sim error"),
    Case("stash-push-missing", "messy", ["stash", "push", "nope.txt"], error="git-sim error"),
    Case("stash-push-u", "messy", ["stash", "push", "-u", "-m", "Half-done pagination"], all_of(stashes_untracked, texts("On main: Half-done pagination"))),
    Case("stash-untracked-without-u", "messy", ["stash", "push", "scratch.txt"], error="stash push -u"),
    Case("stash-drop-with-m", "messy", ["stash", "drop", "--message", "x"], error="stash push only"),
    Case("stash-nothing", "history", ["stash"], title("git stash")),
    Case("stash-push-message", "messy", ["stash", "push", "-m", "Pagination WIP"], all_of(title('git stash push -m "Pagination WIP"'), stashes_something, texts("On main: Pagination WIP"))),
    Case("stash-push-paths", "messy", ["stash", "push", "README.md", "models.py"], lambda m, r: files_in(m, "stash", "after") == ["README.md", "models.py"]),
    Case("stash-show-patch", "messy", ["stash", "show", "-p"], all_of(title("git stash show -p stash@{0}"), stack_of_entries, lambda m, r: same_files(table_column(m, "patch of"), o.git(r, "stash", "show", "--name-only").split()))),
    Case("stash-show-patch-long", "messy", ["stash", "show", "--patch", "stash@{{0}}"], title("git stash show -p stash@{0}")),
    Case("stash-push-patch", "messy", ["stash", "push", "-p"], error="-p applies to stash show only"),
    Case("stash-branch", "messy", ["stash", "branch", "topic"], all_of(title("git stash branch topic stash@{0}"), ref_after("topic", "branch"), unstashes_something)),
    Case("stash-branch-index", "messy", ["stash", "branch", "retry", "0"], all_of(title("git stash branch retry stash@{0}"), ref_after("retry", "branch"))),
    Case("stash-branch-existing", "messy", ["stash", "branch", "main"], error="already exists"),
    Case("stash-branch-empty", "history", ["stash", "branch", "topic"], error="the stash list is empty"),
    Case("stash-branch-no-name", "messy", ["stash", "branch"], error="needs the new branch's name"),
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
    Case("switch-previous", "switched", ["switch", "-"], all_of(title("git switch -"), relabelled("HEAD"), ref_before("@{-1}"), texts("the branch you were on before this one: branch2"))),
    Case("switch-previous-current", "history", ["switch", "-"], error="already on branch"),
    Case("switch-guess", "remote-branch", ["switch", "old-idea"], all_of(title("git switch old-idea"), ref_after("old-idea", "branch"), relabelled("HEAD"), texts("git makes one from origin/old-idea"))),
    Case("switch-create-tracking", "remote-branch", ["switch", "-c", "idea", "origin/old-idea"], all_of(title("git switch -c idea origin/old-idea"), ref_after("idea", "branch"), relabelled("HEAD"), texts("becomes idea's upstream"))),
    Case("switch-create-at", "classic", ["switch", "-c", "topic", "branch2"], all_of(ref_after("topic", "branch"), relabelled("HEAD"))),
    Case("switch-start-without-c", "classic", ["switch", "branch2", "main"], error="needs -c"),
    # tag
    Case("tag", "history", ["tag", "v9.9.9"], all_of(title("git tag v9.9.9"), ref_after("v9.9.9", "tag"))),
    Case("tag-commit", "history", ["tag", "v0.0.1", "HEAD~3"], ref_after("v0.0.1", "tag")),
    Case("tag-delete", "history", ["tag", "-d", "v1.1.0"], ref_removed("v1.1.0")),
    Case("tag-delete-older", "history", ["tag", "-d", "v1.0.0"], ref_removed("v1.0.0"), globals_=["-n", "20"]),
    Case("tag-existing", "history", ["tag", "v1.0.0"], error="git-sim error"),
    Case("tag-delete-missing", "history", ["tag", "-d", "nope"], error="git-sim error"),
    Case("tag-annotated", "history", ["tag", "-a", "v2.0.0", "-m", "Release two"], all_of(title('git tag -a v2.0.0 -m "Release two"'), ref_after("v2.0.0", "annotated tag"), texts("tag object v2.0.0", "Release two", "Validation <validation@example.com>"))),
    Case("tag-annotated-long", "history", ["tag", "--annotate", "v2.0.1", "--message", "Point release", "HEAD~1"], all_of(ref_after("v2.0.1", "annotated tag"), texts("tag object v2.0.1"))),
    Case("tag-message-implies-a", "history", ["tag", "v2.0.2", "-m", "Just a message"], ref_after("v2.0.2", "annotated tag")),
    Case("tag-annotated-no-message", "history", ["tag", "-a", "v2.0.0"], error="needs its message"),
    Case("tag-list", "history", ["tag", "-l"], all_of(title("git tag -l"), texts("git lists every tag", "v1.0.0", "v1.1.0"))),
    Case("tag-list-pattern", "history", ["tag", "--list", "v1.1*"], all_of(title('git tag -l "v1.1*"'), tags_matching("v1.1*"))),
    Case("tag-list-and-delete", "history", ["tag", "-l", "-d", "v1.0.0"], error="git-sim error"),
    # worktree
    Case("worktree-list", "worktree", ["worktree", "list"], all_of(title("git worktree"), texts(M))),
    Case("worktree-add", "worktree", ["worktree", "add", "../hotfix", "main"], texts("hotfix")),
    Case("worktree-add-new-branch", "worktree", ["worktree", "add", "-b", "topic", "../topic-wt"], texts("topic")),
    Case("worktree-remove", "worktree", ["worktree", "remove", "{worktree_path}"], texts("remove")),
    Case("worktree-remove-force", "worktree", ["worktree", "remove", "--force", "{worktree_path}"], title("git worktree")),
    Case("worktree-prune", "worktree", ["worktree", "prune"], title("git worktree")),
    Case("worktree-remove-missing", "worktree", ["worktree", "remove", "../nope"], error="git-sim error"),
    Case("worktree-default", "worktree", ["worktree"], all_of(title("git worktree list"), texts(M))),
    Case("worktree-list-prunable", "worktree-gone", ["worktree", "list"], texts("prunable: directory missing", "git worktree prune removes its record")),
    Case("worktree-prune-gone", "worktree-gone", ["worktree", "prune"], all_of(title("git worktree prune"), texts("Prunes the record of 'old-idea-wt'", "record pruned"))),
    # show
    Case("show", "history", ["show"], all_of(title("git show"), shows("HEAD"))),
    Case("show-commit", "history", ["show", "HEAD~2"], shows("HEAD~2")),
    Case("show-tag", "history", ["show", "v1.0.0"], shows("v1.0.0")),
    Case("show-root", "linear", ["show", "HEAD~9"], shows("HEAD~9")),
    # further back than the window: drawn in HEAD's line after a "..." for the commits between
    Case("show-far", "linear", ["show", "HEAD~7"], all_of(shows("HEAD~7"), texts("stands for the 4 commit(s)"))),
    Case("show-path", "history", ["show", "HEAD:app.py"], texts("app.py")),
    Case("show-missing", "history", ["show", "nope"], error="git-sim error"),
    Case("show-path-missing", "history", ["show", "HEAD:nope.txt"], error="git-sim error"),
    # diff
    Case("diff", "messy", ["diff"], all_of(title("git diff"), diffs())),
    Case("diff-staged", "messy", ["diff", "--staged"], diffs("--cached")),
    Case("diff-cached-commit", "messy", ["diff", "--cached", "HEAD~1"], diffs("--cached", "HEAD~1")),
    Case("diff-commit", "messy", ["diff", "HEAD~1"], diffs("HEAD~1")),
    Case("diff-two", "history", ["diff", "HEAD~3", "HEAD"], all_of(diffs("HEAD~3", "HEAD"), ref_before("from"), ref_after("to"))),
    # nothing staged: the comparison starts from the HEAD commit; something staged: from the staging area
    Case("diff-unstaged", "unstaged", ["diff"], all_of(diffs(), ref_before("from"), texts("Unstaged changes"))),
    Case("diff-with-staged", "messy", ["diff"], all_of(diffs(), texts("HEAD + your staged edits", "git diff --staged shows them"))),
    Case("diff-range", "history", ["diff", "HEAD~2..HEAD"], diffs("HEAD~2", "HEAD")),
    Case("diff-merge-base", "history", ["diff", f"v1.0.0...{M}"], diffs(f"v1.0.0...{M}")),
    Case("diff-path", "messy", ["diff", "HEAD", "README.md"], diffs("HEAD", "--", "README.md")),
    Case("diff-clean", "history", ["diff"], texts("No differences")),
    Case("diff-missing", "history", ["diff", "nope"], error="git-sim error"),
    Case("diff-staged-two", "history", ["diff", "--staged", "HEAD~1", "HEAD"], error="git-sim error"),
    Case("diff-stat", "history", ["diff", "--stat", "HEAD~2..HEAD"], all_of(title("git diff --stat HEAD~2..HEAD"), diffs("HEAD~2", "HEAD"), texts("files changed"))),
    Case("diff-stat-two", "messy", ["diff", "--stat", "HEAD~1", "HEAD"], diffs("HEAD~1", "HEAD")),
    # shortlog
    Case("shortlog", "history", ["shortlog"], all_of(title("git shortlog"), shortlogs("HEAD"), texts("33 commits in HEAD by 6 authors"))),
    Case("shortlog-sne", "history", ["shortlog", "-sne"], all_of(title("git shortlog -sne"), shortlogs("HEAD"), texts("ada@example.com", "most commits first"))),
    Case("shortlog-range", "history", ["shortlog", "-s", "-n", "v1.0.0..HEAD"], shortlogs("v1.0.0..HEAD")),
    Case("shortlog-long-flags", "release", ["shortlog", "--summary", "--numbered", "--email", "main"], shortlogs("main")),
    Case("shortlog-missing", "history", ["shortlog", "nope"], error="git-sim error"),
    # grep
    Case("grep", "history", ["grep", "orders"], all_of(title("git grep orders"), greps("orders"))),
    Case("grep-rev-path", "history", ["grep", "-n", "-i", "ORDER", "HEAD~3", "--", "routes.py"], all_of(title("git grep -n -i ORDER HEAD~3 -- routes.py"), greps("-i", "ORDER", "HEAD~3", "--", "routes.py", rev="HEAD~3"), recolored(1))),
    Case("grep-long-flags", "history", ["grep", "--line-number", "--ignore-case", "PAGINATION"], greps("-i", "PAGINATION")),
    Case("grep-none", "history", ["grep", "zzz-nowhere"], texts("No line matches")),
    Case("grep-missing-rev", "history", ["grep", "orders", "nope"], error="git-sim error"),
    Case("grep-bad-pattern", "history", ["grep", "["], error="git grep refused"),
    # describe
    Case("describe-tags", "history", ["describe", "--tags", "HEAD~1"], all_of(title("git describe --tags HEAD~1"), describes("--tags", "HEAD~1"), ref_after("v1.0.0-6-gbeea529", "describe"))),
    Case("describe-exact", "history", ["describe", "--tags"], all_of(describes("--tags"), texts("the tagged commit"))),
    Case("describe-annotated", "annotated", ["describe"], describes()),
    Case("describe-lightweight", "history", ["describe"], error="try --tags"),
    Case("describe-no-tags", "linear", ["describe"], error="no tags"),
    Case("describe-missing", "history", ["describe", "nope"], error="git-sim error"),
    # blame
    Case("blame", "history", ["blame", "app.py"], all_of(title("git blame"), blames("app.py"))),
    Case("blame-lines", "history", ["blame", "-L", "1,3", "app.py"], blames("app.py", "1,3")),
    Case("blame-modified", "messy", ["blame", "README.md"], texts("not committed yet")),
    Case("blame-untracked", "messy", ["blame", "scratch.txt"], error="git-sim error"),
    Case("blame-bad-range", "history", ["blame", "-L", "abc", "app.py"], error="git-sim error"),
    # check-ignore (the ignores shape: *.log ignored, !keep.log un-ignores, tracked.log committed anyway)
    Case("check-ignore", "ignores", ["check-ignore", "debug.log", "notes.txt"], all_of(title("git check-ignore"), texts("ignored by .gitignore:1", "not ignored: no rule matches it"), ignored_by_git(["debug.log"], ["notes.txt"]))),
    Case("check-ignore-verbose", "ignores", ["check-ignore", "-v", "keep.log", "debug.log"], texts(".gitignore:3:!keep.log", ".gitignore:1:*.log")),
    Case("check-ignore-tracked", "ignores", ["check-ignore", "--verbose", "tracked.log"], all_of(texts("tracked, so .gitignore doesn't apply"), ignored_by_git(not_ignored=["tracked.log"]))),
    Case("check-ignore-no-gitignore", "history", ["check-ignore", "debug.log"], texts("no .gitignore", "exits with status 1")),
    Case("check-ignore-no-path", "ignores", ["check-ignore"], error="no path specified"),
    Case("check-ignore-outside", "ignores", ["check-ignore", "../elsewhere.txt"], error="outside repository"),
    # bisect
    Case("bisect-start", "linear", ["bisect", "start", "HEAD", "HEAD~7"], all_of(title("git bisect start"), bisect_next("HEAD", ["HEAD~7"]), ref_after("bad", "bisect"))),
    Case("bisect-start-empty", "linear", ["bisect", "start"], texts("waiting")),
    Case("bisect-good", "bisecting", ["bisect", "good"], bisect_next_after("good")),
    Case("bisect-bad", "bisecting", ["bisect", "bad"], bisect_next_after("bad")),
    Case("bisect-skip", "bisecting", ["bisect", "skip"], all_of(title("git bisect skip"), relabelled("HEAD"))),
    Case("bisect-reset", "bisecting", ["bisect", "reset"], all_of(ref_removed("bad"), relabelled("HEAD"))),
    Case("bisect-new-mixed", "bisecting", ["bisect", "new"], error="terms"),
    Case("bisect-old-no-session", "linear", ["bisect", "old"], error="not bisecting"),
    Case("bisect-good-no-session", "linear", ["bisect", "good"], error="not bisecting"),
    Case("bisect-start-swapped", "linear", ["bisect", "start", "HEAD~7", "HEAD"], error="ancestor"),
    # clone (runs in a plain folder; the URL is the ahead shape's remote)
    Case("clone", "notrepo", ["clone", "{remote_url}"], all_of(title("git clone"), texts("cloned"))),
    Case("clone-bad-url", "notrepo", ["clone", "not-a-url"], error="git-sim error"),
    # shallow: only the last commits, the oldest drawn cut off (grafted)
    Case("clone-depth", "notrepo", ["clone", "--depth", "2", "{remote_url}"], all_of(title("git clone --depth 2"), texts("grafted", "only the last 2 commits"), commit_count(2))),
    Case("clone-branch", "notrepo", ["clone", "-b", "main", "{remote_url}", "copy"], all_of(title("git clone -b main"), texts("on main"), ref_before("main"))),
    Case("clone-depth-branch", "notrepo", ["clone", "--depth", "1", "--branch", "main", "{remote_url}"], all_of(texts("grafted"), commit_count(1))),
    Case("clone-bad-branch", "notrepo", ["clone", "-b", "nope", "{remote_url}"], error="Remote branch nope not found"),
    # not a repository / bare
    Case("status-notrepo", "notrepo", ["status"], error="git-sim error"),
    Case("log-bare", "bare", ["log"], error="git-sim error"),
    # the large shape: a smoke test of layout at scale
    Case("log-large", "large", ["log", "--all", "-n", "30"], commits_at_least(30), slow=True),
    Case("status-large", "large", ["status"], title("git status"), slow=True),
]

TODO_FILE = "pick {c1}\nsquash {c2}\n"
