"""Validate every git-sim subcommand against git ground truth.

Usage: python scripts/validate_commands.py [image-output-dir]
Needs the dev environment (git-dummy, skia). Prints a PASS/FAIL table.

For each case: build a fixture repo (git-dummy plus targeted edits), construct
the scene in-process, capture what it drew (commits, where ref labels landed,
arrows between commits, zone column titles and file lists, the title), and
compare with expectations computed from the repo with GitPython. An image is
rendered per case for spot checks.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

for var in list(os.environ):
    if var.lower().startswith("git_sim_"):
        del os.environ[var]

import git  # noqa: E402
import numpy as np  # noqa: E402

from git_sim.settings import Settings, settings  # noqa: E402
from git_sim.enums import ResetMode, StashSubCommand, RemoteSubCommand  # noqa: E402

ROOT = Path(tempfile.mkdtemp(prefix="gitsim_validate_"))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "images"
OUT.mkdir(exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()
PY = sys.executable
DEFAULTS = Settings().model_dump()
RESULTS = []


# ----------------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------------
def sh(*args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=check)


def g(repo, *args, check=True):
    return sh("git", *args, cwd=repo, check=check).stdout


def base_repo(name="sample_repo"):
    """git-dummy repo: 10 commits, main + branch1..3 diverging at 2, branch1 merged."""
    target = ROOT / name
    if not target.exists():
        sh(
            PY,
            "-m",
            "git_dummy",
            "--commits=10",
            "--branches=4",
            "--merge=1",
            "--constant-sha",
            f"--name={name}",
            "--diverge-at=2",
            cwd=ROOT,
        )
    return target


_counter = [0]


def fresh(builder=None, name="repo"):
    """A private copy of the base repo, optionally modified by builder(path)."""
    _counter[0] += 1
    dest = ROOT / f"{name}_{_counter[0]}"
    shutil.copytree(base_repo(), dest)
    if builder:
        builder(dest)
    return dest


def dirty(repo):
    (repo / "untracked.txt").write_text("new\n")
    (repo / "main.3").write_text("modified\n")
    (repo / "main.4").write_text("staged\n")
    g(repo, "add", "main.4")


def with_stash(repo):
    (repo / "main.5").write_text("stashed change\n")
    g(repo, "stash")


def with_remote(repo):
    """origin = bare clone of the repo; returns path of the bare remote."""
    remote = repo.parent / (repo.name + "_remote.git")
    sh("git", "clone", "-q", "--bare", str(repo), str(remote), cwd=repo.parent)
    g(repo, "remote", "add", "origin", str(remote))
    g(repo, "fetch", "-q", "origin")
    g(repo, "branch", "-u", "origin/main", "main")
    return remote


def local_ahead(repo):
    with_remote(repo)
    (repo / "local_new.txt").write_text("local\n")
    g(repo, "add", ".")
    g(repo, "commit", "-q", "-m", "local-only commit")


def remote_ahead(repo, n=2, conflict=False):
    remote = with_remote(repo)
    other = repo.parent / (repo.name + "_other")
    sh("git", "clone", "-q", str(remote), str(other), cwd=repo.parent)
    g(other, "config", "user.email", "o@e.com")
    g(other, "config", "user.name", "Other")
    for i in range(n):
        (other / f"remote_new_{i}.txt").write_text(f"remote {i}\n")
        if conflict:
            (other / "main.1").write_text("remote edit\n")
        g(other, "add", ".")
        g(other, "commit", "-q", "-m", f"remote-only commit {i}")
    g(other, "push", "-q")
    if conflict:
        (repo / "main.1").write_text("local edit\n")
        g(repo, "commit", "-q", "-am", "local conflicting edit")


def conflict_branches(repo):
    g(repo, "checkout", "-q", "-b", "hot")
    (repo / "main.1").write_text("hot version\n")
    g(repo, "commit", "-q", "-am", "hot edit")
    g(repo, "checkout", "-q", "main")
    (repo / "main.1").write_text("main version\n")
    g(repo, "commit", "-q", "-am", "main edit")


def behind_branch(repo):
    g(repo, "checkout", "-q", "-b", "behind", "HEAD~2")


# ----------------------------------------------------------------------------
# oracle helpers
# ----------------------------------------------------------------------------
def expected_commits(repo, start, n, first_parent_only):
    """The commits parse_commits visits: depth < n along parents."""
    seen = set()

    def walk(c, i):
        if i >= n:
            return
        seen.add(c.hexsha)
        parents = c.parents[:1] if first_parent_only else c.parents
        for p in parents:
            walk(p, i + 1)

    walk(start, 0)
    return seen


def repo_status(repo):
    r = git.Repo(repo)
    return {
        "untracked": set(r.untracked_files),
        "modified": {d.a_path for d in r.index.diff(None)},
        "staged": {d.a_path for d in r.index.diff("HEAD")},
    }


# ----------------------------------------------------------------------------
# scene capture
# ----------------------------------------------------------------------------
class Capture:
    def __init__(self, scene):
        self.scene = scene
        self.cols = None
        self.zone_files = {}
        self.zone_arrows = {}
        orig_sdz = scene.setup_and_draw_zones
        orig_pz = scene.populate_zones

        def sdz(
            first_column_name="Untracked files",
            second_column_name="Modified files",
            third_column_name="Staged files",
            reverse=False,
        ):
            names = [first_column_name, second_column_name, third_column_name]
            if reverse:
                names[0], names[2] = "Staging area", "Deleted changes"
            self.cols = tuple(names)
            return orig_sdz(
                first_column_name=first_column_name,
                second_column_name=second_column_name,
                third_column_name=third_column_name,
                reverse=reverse,
            )

        def pz(f1, f2, f3, a1=None, a2=None, a3=None):
            a1 = {} if a1 is None else a1
            a2 = {} if a2 is None else a2
            a3 = {} if a3 is None else a3
            orig_pz(f1, f2, f3, a1, a2, a3)
            self.zone_files = {"first": set(f1), "second": set(f2), "third": set(f3)}
            self.zone_arrows = {"first": set(a1), "second": set(a2), "third": set(a3)}

        scene.setup_and_draw_zones = sdz
        scene.populate_zones = pz

    # after construct -------------------------------------------------------
    def commits(self):
        return {k: v.get_center() for k, v in self.scene.drawnCommits.items()}

    def nearest_commit(self, point, tol=1.9):
        # Arrows are shortened by 0.75 (horizontal) or 1.5 (diagonal) per end.
        best, dist = None, tol
        for sha, c in self.commits().items():
            d = float(np.linalg.norm(c[:2] - np.asarray(point)[:2]))
            if d < dist:
                best, dist = sha, d
        return best

    def refs(self):
        """ref name -> sha of the commit whose column it sits above."""
        out = {}
        for name, mob in self.scene.drawnRefs.items():
            if mob not in self.scene.mobjects and not any(
                mob in top.get_family() for top in self.scene.mobjects
            ):
                continue  # removed from the scene (e.g. tag -d)
            center = mob.get_center()
            best, dx = None, 0.6
            for sha, c in self.commits().items():
                if abs(c[0] - center[0]) < dx and center[1] > c[1]:
                    best, dx = sha, abs(c[0] - center[0])
            out[name] = best
        return out

    def edges(self):
        from git_sim.render.shapes import Line, CurvedArrow

        found = set()
        seen = set()
        for top in self.scene.mobjects:
            for mob in top.get_family():
                if id(mob) in seen:
                    continue
                seen.add(id(mob))
                if isinstance(mob, CurvedArrow) or (
                    isinstance(mob, Line)
                    and mob.tip is not None
                    and mob.get_length() > 0
                ):
                    a = self.nearest_commit(mob.get_start())
                    b = self.nearest_commit(mob.get_end())
                    if a and b and a != b:
                        found.add((a, b))
        return found

    def texts(self):
        out = []
        for top in self.scene.mobjects:
            for mob in top.get_family():
                if hasattr(mob, "text") and getattr(mob, "layout", None) is not None:
                    out.append(mob)
        return out

    def text_values(self):
        return [t.text for t in self.texts()]

    def column_texts(self, which):
        group = getattr(self.scene, f"{which}ColumnFiles", None)
        if group is None:
            return []
        live = [
            t
            for t in group
            if any(t in top.get_family() for top in self.scene.mobjects)
        ]
        return [(t.text, t.strikethrough) for t in live]


def reset_settings(**overrides):
    for k, v in DEFAULTS.items():
        setattr(settings, k, v)
    settings.auto_open = False
    for k, v in overrides.items():
        setattr(settings, k, v)


def _short(sha_):
    return sha_[:6] if isinstance(sha_, str) else sha_


def _debug(cap):
    refs = {k: _short(v) for k, v in cap.refs().items()}
    raw_refs = {
        k: (np.round(v.get_center()[:2], 2).tolist())
        for k, v in cap.scene.drawnRefs.items()
    }
    edges = sorted((_short(a), _short(b)) for a, b in cap.edges())
    frame = cap.scene.camera.frame
    commits = {_short(s): np.round(c[:2], 2).tolist() for s, c in cap.commits().items()}
    return (
        f"refs={refs} ref_pos={raw_refs} commits={commits} edges={edges} zones={cap.zone_files} "
        f"frame_center={np.round(frame.get_center()[:2], 2).tolist()} frame_w={frame.get_width():.2f}"
    )


def run_case(name, repo, make_scene, checks, expect_exit=False, **setting_overrides):
    """Construct the scene in repo, capture, run checks (list of (label, fn) -> fn(cap) truthy).

    expect_exit: the scene is supposed to refuse (print an error and exit)."""
    import re

    reset_settings(**setting_overrides)
    cwd = os.getcwd()
    os.chdir(repo)
    status = "PASS"
    notes = []
    exited = False
    try:
        try:
            scene = make_scene()
        except SystemExit as e:
            exited = True
            notes.append(f"exited at init (code {e.code})")
            raise
        cap = Capture(scene)
        scene.construct()
        try:
            safe = re.sub(r"[^\w.-]+", "_", name)
            scene.render_image(str(OUT / f"{safe}.png"), fmt="png")
        except Exception as e:  # rendering problems are their own finding
            notes.append(f"render failed: {e}")
        failed = False
        for label, fn in checks:
            try:
                ok = fn(cap)
            except Exception as e:
                ok = False
                label += f" [check raised {type(e).__name__}: {e}]"
            if not ok:
                failed = True
                notes.append(label)
        if failed:
            status = "FAIL"
            notes.append(_debug(cap))
        if expect_exit:
            status = "FAIL"
            notes.append("expected the scene to refuse, but it ran")
    except SystemExit as e:
        if not exited:
            notes.append(f"exited during construct (code {e.code})")
        status = "PASS" if expect_exit else "EXIT"
    except Exception:
        status = "CRASH"
        notes.append(traceback.format_exc().strip().splitlines()[-1])
    finally:
        os.chdir(cwd)
    RESULTS.append((name, status, "; ".join(notes)))


def head(repo):
    return git.Repo(repo).head.commit


def sha(repo, rev):
    return git.Repo(repo).commit(rev).hexsha


# ----------------------------------------------------------------------------
# cases
# ----------------------------------------------------------------------------
def case_log():
    from git_sim.log import Log

    repo = fresh()
    ctx = SimpleNamespace(parent=SimpleNamespace(params={"n": 5, "all": False}))
    r = git.Repo(repo)
    exp = expected_commits(repo, r.head.commit, 5, False)
    run_case(
        "log",
        repo,
        lambda: Log(ctx=ctx, n=None, all=False),
        [
            (
                "drawn commits == depth-5 ancestry incl. both merge parents",
                lambda c: set(c.commits()) == exp,
            ),
            (
                "HEAD and main labels sit above HEAD commit",
                lambda c: c.refs().get("HEAD") == r.head.commit.hexsha
                and c.refs().get("main") == r.head.commit.hexsha,
            ),
            (
                "branch1 label above branch1 tip",
                lambda c: c.refs().get("branch1") == r.heads["branch1"].commit.hexsha,
            ),
            (
                "every drawn parent link has an arrow child->parent",
                lambda c: all(
                    (cm.hexsha, p.hexsha) in c.edges()
                    for cm in map(r.commit, c.commits())
                    for p in cm.parents
                    if p.hexsha in c.commits()
                ),
            ),
            ("title is 'git log'", lambda c: c.scene.cmd == "git log"),
        ],
    )
    ctx3 = SimpleNamespace(parent=SimpleNamespace(params={"n": 5, "all": False}))
    exp3 = expected_commits(repo, r.head.commit, 3, False)
    run_case(
        "log -n 3",
        repo,
        lambda: Log(ctx=ctx3, n=3, all=False),
        [
            ("drawn commits == depth-3 ancestry", lambda c: set(c.commits()) == exp3),
            ("title", lambda c: c.scene.cmd == "git log -n 3"),
        ],
    )
    ctxa = SimpleNamespace(parent=SimpleNamespace(params={"n": 5, "all": False}))
    tips = {r.heads[b].commit.hexsha for b in ("branch2", "branch3")}
    run_case(
        "log --all",
        repo,
        lambda: Log(ctx=ctxa, n=None, all=True),
        [
            ("branch2 and branch3 tips drawn", lambda c: tips <= set(c.commits())),
            (
                "their labels sit above their tips",
                lambda c: c.refs().get("branch2") == r.heads["branch2"].commit.hexsha
                and c.refs().get("branch3") == r.heads["branch3"].commit.hexsha,
            ),
        ],
    )


def case_reset():
    from git_sim.reset import Reset

    for mode, flag, col in (
        ("mixed", {}, "second"),
        ("soft", {"soft": True}, "third"),
        ("hard", {"hard": True}, "first"),
    ):
        repo = fresh(dirty)
        r = git.Repo(repo)
        target = r.commit("HEAD~2")
        touched = set()
        for cm in r.iter_commits("HEAD~2..HEAD"):
            touched |= set(cm.stats.files)
        st = repo_status(repo)
        if mode == "hard":
            expected = touched | st["modified"] | st["staged"]
        elif mode == "mixed":
            expected = touched | st["modified"] | st["staged"]
        else:
            expected = touched | st["staged"]
        kwargs = dict(
            commit="HEAD~2", mode=ResetMode.DEFAULT, soft=False, mixed=False, hard=False
        )
        kwargs.update(flag)
        run_case(
            f"reset HEAD~2 --{mode}",
            repo,
            lambda: Reset(**kwargs),
            [
                (
                    "HEAD and main labels moved above target",
                    lambda c: c.refs().get("HEAD") == target.hexsha
                    and c.refs().get("main") == target.hexsha,
                ),
                (
                    f"{col} column lists files from undone commits (+ dirty)",
                    lambda c: c.zone_files.get(col) == expected,
                ),
                (
                    "other columns follow git semantics",
                    lambda c: (
                        (
                            mode == "soft"
                            and c.zone_files["second"] == st["modified"]
                            and not c.zone_files["first"]
                        )
                        or (
                            mode == "mixed"
                            and not c.zone_files["first"]
                            and not c.zone_files["third"]
                        )
                        or (
                            mode == "hard"
                            and not c.zone_files["second"]
                            and not c.zone_files["third"]
                        )
                    ),
                ),
                (
                    "title names the mode",
                    lambda c: (
                        c.scene.cmd == f"git reset --{mode} HEAD~2"
                        if mode != "mixed"
                        else c.scene.cmd == "git reset HEAD~2"
                    ),
                ),
            ],
            hide_first_tag=True,
        )


def case_commit():
    from git_sim.commit import Commit

    repo = fresh(dirty)
    r = git.Repo(repo)
    h = r.head.commit.hexsha
    st = repo_status(repo)
    run_case(
        "commit -m",
        repo,
        lambda: Commit(message="Add feature", amend=False),
        [
            (
                "new commit abcdef drawn with arrow to old HEAD",
                lambda c: "abcdef" in c.commits() and ("abcdef", h) in c.edges(),
            ),
            (
                "HEAD and main labels above abcdef",
                lambda c: c.refs().get("HEAD") == "abcdef"
                and c.refs().get("main") == "abcdef",
            ),
            ("message text drawn", lambda c: "Add feature" in c.text_values()),
            (
                "staged files flow staged -> new commit",
                lambda c: c.zone_files["second"] == st["staged"]
                and c.zone_files["third"] == st["staged"]
                and c.zone_arrows["second"] == st["staged"],
            ),
            (
                "modified-only files stay in working directory column",
                lambda c: c.zone_files["first"] == st["modified"],
            ),
            (
                "column titles",
                lambda c: c.cols == ("Working directory", "Staged files", "New commit"),
            ),
        ],
        hide_first_tag=True,
    )

    repo2 = fresh()
    r2 = git.Repo(repo2)
    old_parents = {p.hexsha for p in r2.head.commit.parents}
    run_case(
        "commit --amend -m",
        repo2,
        lambda: Commit(message="Amended message", amend=True),
        [
            (
                "old HEAD commit is no longer drawn",
                lambda c: r2.head.commit.hexsha not in c.commits(),
            ),
            (
                "amended commit keeps HEAD's parents (real amend semantics)",
                lambda c: any(
                    sha_ != "abcdef"
                    and {p.hexsha for p in r2.commit(sha_).parents} == old_parents
                    for sha_ in c.commits()
                    if sha_ not in {p for p in old_parents}
                ),
            ),
            (
                "HEAD and main labels above the amended commit",
                lambda c: c.refs().get("HEAD") is not None
                and c.refs().get("HEAD") == c.refs().get("main")
                and c.refs()["HEAD"] not in old_parents,
            ),
            ("amended message drawn", lambda c: "Amended message" in c.text_values()),
        ],
        hide_first_tag=True,
    )


def case_merge():
    from git_sim.merge import Merge

    repo = fresh()
    r = git.Repo(repo)
    h, b2 = r.head.commit.hexsha, r.heads["branch2"].commit.hexsha
    run_case(
        "merge branch2 (true merge)",
        repo,
        lambda: Merge(branch="branch2", no_ff=False, message="Merge commit"),
        [
            (
                "merge commit abcdef with edges to both parents",
                lambda c: {("abcdef", h), ("abcdef", b2)} <= c.edges(),
            ),
            (
                "HEAD and main above abcdef; branch2 stays",
                lambda c: c.refs().get("HEAD") == "abcdef"
                and c.refs().get("main") == "abcdef"
                and c.refs().get("branch2") == b2,
            ),
        ],
    )
    repo_ff = fresh(behind_branch)
    rf = git.Repo(repo_ff)
    main_tip = rf.heads["main"].commit.hexsha
    run_case(
        "merge main (fast-forward)",
        repo_ff,
        lambda: Merge(branch="main", no_ff=False, message="Merge commit"),
        [
            ("no new commit for a fast-forward", lambda c: "abcdef" not in c.commits()),
            (
                "HEAD and behind labels moved to main tip",
                lambda c: c.refs().get("HEAD") == main_tip
                and c.refs().get("behind") == main_tip,
            ),
        ],
    )
    repo_noff = fresh(behind_branch)
    rn = git.Repo(repo_noff)
    run_case(
        "merge main --no-ff",
        repo_noff,
        lambda: Merge(branch="main", no_ff=True, message="Merge commit"),
        [
            ("merge commit abcdef created", lambda c: "abcdef" in c.commits()),
            (
                "abcdef points at main tip and (curved) at old HEAD",
                lambda c: ("abcdef", rn.heads["main"].commit.hexsha) in c.edges()
                and ("abcdef", rn.head.commit.hexsha) in c.edges(),
            ),
            (
                "HEAD/behind above abcdef",
                lambda c: c.refs().get("HEAD") == "abcdef"
                and c.refs().get("behind") == "abcdef",
            ),
        ],
    )
    repo_c = fresh(conflict_branches)
    run_case(
        "merge hot (conflict)",
        repo_c,
        lambda: Merge(branch="hot", no_ff=False, message="Merge commit"),
        [
            (
                "conflicted file listed in middle column",
                lambda c: c.zone_files.get("second") == {"main.1"}
                and c.cols[1] == "Conflicted files",
            ),
            ("no merge commit drawn", lambda c: "abcdef" not in c.commits()),
        ],
    )
    repo_e = fresh()
    run_case(
        "merge branch1 (already merged -> refuses)",
        repo_e,
        lambda: Merge(branch="branch1", no_ff=False, message="x"),
        [],
        expect_exit=True,
    )


def case_rebase():
    from git_sim.rebase import Rebase

    repo = fresh()
    r = git.Repo(repo)
    real = set(r.git.rev_list("--all").split())
    to_rebase = list(r.iter_commits("branch2..HEAD", first_parent=True))
    n_copies = min(len(to_rebase), 5)
    b2 = r.heads["branch2"].commit.hexsha
    run_case(
        "rebase branch2",
        repo,
        lambda: Rebase(branch="branch2"),
        [
            (
                f"{n_copies} replayed copies, each with a dotted arrow from its original",
                lambda c: (
                    len([s for s in c.commits() if s not in real]) == n_copies
                    and len([e for e in c.edges() if e[0] in real and e[1] not in real])
                    == n_copies
                ),
            ),
            (
                "first copy is a child of branch2 tip",
                lambda c: any(e[1] == b2 and e[0] not in real for e in c.edges()),
            ),
            (
                "HEAD and main labels above a replayed copy (not an original)",
                lambda c: c.refs().get("HEAD") not in real
                and c.refs().get("HEAD") == c.refs().get("main"),
            ),
            (
                "branch2 label stays on branch2 tip",
                lambda c: c.refs().get("branch2") == b2,
            ),
        ],
    )


def case_cherry_pick():
    from git_sim.cherrypick import CherryPick

    repo = fresh()
    r = git.Repo(repo)
    h, b2 = r.head.commit.hexsha, r.heads["branch2"].commit.hexsha
    msg = r.heads["branch2"].commit.message.strip()
    run_case(
        "cherry-pick branch2",
        repo,
        lambda: CherryPick(commit="branch2", edit=None),
        [
            (
                "abcdef after HEAD with dotted arrow from picked commit",
                lambda c: ("abcdef", h) in c.edges() and (b2, "abcdef") in c.edges(),
            ),
            (
                "HEAD/main above abcdef",
                lambda c: c.refs().get("HEAD") == "abcdef"
                and c.refs().get("main") == "abcdef",
            ),
            (
                "copied message drawn",
                lambda c: any(msg[:20] in t for t in c.text_values()),
            ),
        ],
    )
    run_case(
        "cherry-pick branch2 -e",
        fresh(),
        lambda: CherryPick(commit="branch2", edit="Edited msg"),
        [
            ("edited message drawn", lambda c: "Edited msg" in c.text_values()),
        ],
    )


def case_revert():
    from git_sim.revert import Revert

    repo = fresh()
    r = git.Repo(repo)
    target = r.commit("HEAD~1")
    run_case(
        "revert HEAD~1",
        repo,
        lambda: Revert(commit="HEAD~1"),
        [
            (
                "abcdef after HEAD",
                lambda c: ("abcdef", r.head.commit.hexsha) in c.edges(),
            ),
            (
                "HEAD/main above abcdef",
                lambda c: c.refs().get("HEAD") == "abcdef"
                and c.refs().get("main") == "abcdef",
            ),
            (
                "message 'Revert <sha>'",
                lambda c: any(
                    t.startswith("Revert " + target.hexsha[:6]) for t in c.text_values()
                ),
            ),
            (
                "reverted files listed",
                lambda c: c.zone_files.get("second") == set(target.stats.files)
                and c.cols[1] == "Changes reverted from",
            ),
        ],
        hide_first_tag=True,
    )


def case_branch_tag():
    from git_sim.branch import Branch
    from git_sim.tag import Tag

    repo = fresh()
    r = git.Repo(repo)
    h = r.head.commit.hexsha
    run_case(
        "branch new_branch",
        repo,
        lambda: Branch(name="new_branch"),
        [
            ("new label above HEAD commit", lambda c: c.refs().get("new_branch") == h),
            ("title", lambda c: c.scene.cmd == "git branch new_branch"),
        ],
    )
    run_case(
        "tag v1",
        fresh(),
        lambda: Tag(name="v1", commit=None, d=False),
        [
            ("tag label above HEAD", lambda c: c.refs().get("v1") == h),
            ("title", lambda c: c.scene.cmd == "git tag v1"),
        ],
    )
    target = sha(repo, "HEAD~2")
    run_case(
        "tag v1 HEAD~2",
        fresh(),
        lambda: Tag(name="v1", commit="HEAD~2", d=False),
        [
            ("tag label above HEAD~2", lambda c: c.refs().get("v1") == target),
            (
                "title shows the commit argument",
                lambda c: c.scene.cmd == "git tag v1 HEAD~2",
            ),
        ],
    )

    def tagged(p):
        g(p, "tag", "v9", "HEAD~1")

    run_case(
        "tag -d v9",
        fresh(tagged),
        lambda: Tag(name="v9", commit=None, d=True),
        [
            (
                "deleted tag no longer drawn",
                lambda c: "v9" not in c.refs() or c.refs().get("v9") is None,
            ),
            ("title", lambda c: c.scene.cmd == "git tag -d v9"),
        ],
    )


def case_checkout_switch():
    from git_sim.checkout import Checkout
    from git_sim.switch import Switch

    repo = fresh()
    r = git.Repo(repo)
    h, b2 = r.head.commit.hexsha, r.heads["branch2"].commit.hexsha
    run_case(
        "checkout branch2",
        repo,
        lambda: Checkout(branch="branch2", b=False),
        [
            (
                "HEAD label moves above branch2 tip",
                lambda c: c.refs().get("HEAD") == b2,
            ),
            ("main label stays above old HEAD", lambda c: c.refs().get("main") == h),
        ],
    )
    run_case(
        "checkout -b feature",
        fresh(),
        lambda: Checkout(branch="feature", b=True),
        [
            (
                "new branch label above HEAD",
                lambda c: c.refs().get("feature") == h and c.refs().get("HEAD") == h,
            ),
        ],
    )
    behind = fresh(behind_branch)
    rb = git.Repo(behind)
    run_case(
        "checkout main (from behind branch, ancestor case)",
        behind,
        lambda: Checkout(branch="main", b=False),
        [
            (
                "HEAD label above main tip",
                lambda c: c.refs().get("HEAD") == rb.heads["main"].commit.hexsha,
            ),
            (
                "behind label stays on its commit",
                lambda c: c.refs().get("behind") == rb.head.commit.hexsha,
            ),
        ],
    )
    run_case(
        "switch branch2",
        fresh(),
        lambda: Switch(branch="branch2", c=False, detach=False),
        [
            (
                "HEAD above branch2 tip; main stays",
                lambda c: c.refs().get("HEAD") == b2 and c.refs().get("main") == h,
            ),
        ],
    )
    run_case(
        "switch -c feature",
        fresh(),
        lambda: Switch(branch="feature", c=True, detach=False),
        [
            ("new label above HEAD", lambda c: c.refs().get("feature") == h),
        ],
    )
    target = sha(repo, "HEAD~2")
    run_case(
        "switch --detach HEAD~2",
        fresh(),
        lambda: Switch(branch="HEAD~2", c=False, detach=True),
        [
            ("HEAD label above HEAD~2", lambda c: c.refs().get("HEAD") == target),
            # The range HEAD~2..HEAD counts the merged-in lineage too, so the scene
            # takes its "target not reached" path and draws only the target's
            # ancestry; old HEAD and main are out of frame by design.
            (
                "frame is finite (no NaN geometry)",
                lambda c: np.isfinite(c.scene.camera.frame.get_center()).all(),
            ),
        ],
    )


def case_zones():
    from git_sim.add import Add
    from git_sim.status import Status
    from git_sim.restore import Restore
    from git_sim.rm import Rm
    from git_sim.mv import Mv
    from git_sim.clean import Clean
    from git_sim.stash import Stash

    repo = fresh(dirty)
    st = repo_status(repo)
    run_case(
        "status",
        repo,
        lambda: Status(),
        [
            (
                "columns = untracked / modified / staged",
                lambda c: c.zone_files
                == {
                    "first": st["untracked"],
                    "second": st["modified"],
                    "third": st["staged"],
                },
            ),
            (
                "titles",
                lambda c: c.cols
                == ("Untracked files", "Modified files", "Staged files"),
            ),
        ],
        hide_first_tag=True,
        allow_no_commits=True,
    )
    run_case(
        "add (no files)",
        fresh(dirty),
        lambda: Add(files=[]),
        [
            (
                "nothing moves without arguments",
                lambda c: c.zone_files["third"] == st["staged"]
                and not c.zone_arrows["first"]
                and not c.zone_arrows["second"],
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "add untracked.txt main.3",
        fresh(dirty),
        lambda: Add(files=["untracked.txt", "main.3"]),
        [
            (
                "both files arrive in staged column",
                lambda c: {"untracked.txt", "main.3"} <= c.zone_files["third"],
            ),
            (
                "arrows from untracked and modified columns",
                lambda c: c.zone_arrows["first"] == {"untracked.txt"}
                and c.zone_arrows["second"] == {"main.3"},
            ),
            ("title", lambda c: c.scene.cmd == "git add untracked.txt main.3"),
        ],
        hide_first_tag=True,
    )
    run_case(
        "add nope.txt (refuses)",
        fresh(dirty),
        lambda: Add(files=["nope.txt"]),
        [],
        expect_exit=True,
        hide_first_tag=True,
    )
    run_case(
        "restore main.3",
        fresh(dirty),
        lambda: Restore(files=["main.3"], staged=False),
        [
            (
                "modified file moves to 'Deleted changes'",
                lambda c: "main.3" in c.zone_files["third"]
                and c.zone_arrows["second"] == {"main.3"},
            ),
            (
                "titles reversed",
                lambda c: c.cols
                == ("Staging area", "Modified files", "Deleted changes"),
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "restore --staged main.4",
        fresh(dirty),
        lambda: Restore(files=["main.4"], staged=True),
        [
            (
                "staged file moves back to modified column",
                lambda c: "main.4" in c.zone_files["second"]
                and c.zone_arrows["first"] == {"main.4"},
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "rm main.1",
        fresh(dirty),
        lambda: Rm(files=["main.1"]),
        [
            (
                "working dir -> removed, struck through",
                lambda c: c.zone_files["first"] == {"main.1"}
                and c.zone_files["third"] == {"main.1"}
                and all(strike for _, strike in c.column_texts("third")),
            ),
            (
                "titles",
                lambda c: c.cols
                == ("Working directory", "Staging area", "Removed files"),
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "rm main.4 (staged file)",
        fresh(dirty),
        lambda: Rm(files=["main.4"]),
        [
            (
                "comes from staging column",
                lambda c: c.zone_files["second"] == {"main.4"}
                and c.zone_arrows["second"] == {"main.4"},
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "rm nope.txt (refuses)",
        fresh(dirty),
        lambda: Rm(files=["nope.txt"]),
        [],
        expect_exit=True,
        hide_first_tag=True,
    )
    run_case(
        "mv main.1 main.100",
        fresh(dirty),
        lambda: Mv(file="main.1", new_file="main.100"),
        [
            (
                "old name in working dir column, new name shown in renamed column",
                lambda c: c.zone_files["first"] == {"main.1"}
                and "main.100" in c.text_values(),
            ),
            (
                "old name no longer shown in renamed column",
                lambda c: not any(t == "main.1" for t, _ in c.column_texts("third")),
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "mv nope.txt x (should refuse)",
        fresh(dirty),
        lambda: Mv(file="nope.txt", new_file="x"),
        [],
        expect_exit=True,
        hide_first_tag=True,
    )
    run_case(
        "clean",
        fresh(dirty),
        lambda: Clean(),
        [
            (
                "untracked -> deleted with arrows",
                lambda c: c.zone_files["first"] == st["untracked"]
                and c.zone_files["third"] == st["untracked"]
                and c.zone_arrows["first"] == st["untracked"],
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "stash",
        fresh(dirty),
        lambda: Stash(files=[], command=None, stash_index="0"),
        [
            (
                "modified and staged both stashed",
                lambda c: c.zone_files["third"] == st["modified"] | st["staged"]
                and c.zone_files["first"] == st["modified"]
                and c.zone_files["second"] == st["staged"],
            ),
            (
                "titles",
                lambda c: c.cols
                == ("Working directory", "Staging area", "Stashed changes"),
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "stash push main.3",
        fresh(dirty),
        lambda: Stash(files=["main.3"], command=StashSubCommand.PUSH, stash_index="0"),
        [
            (
                "only main.3 stashed",
                lambda c: c.zone_files["third"] == {"main.3"}
                and c.zone_arrows["first"] == {"main.3"},
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "stash pop",
        fresh(with_stash),
        lambda: Stash(files=[], command=StashSubCommand.POP, stash_index="0"),
        [
            (
                "stash entry files return to working dir, struck through in stash column",
                lambda c: c.zone_files["third"] == {"main.5"}
                and c.zone_files["first"] == {"main.5"}
                and all(s for _, s in c.column_texts("third")),
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "stash apply",
        fresh(with_stash),
        lambda: Stash(files=[], command=StashSubCommand.APPLY, stash_index="0"),
        [
            (
                "same files, not struck through",
                lambda c: c.zone_files["third"] == {"main.5"}
                and not any(s for _, s in c.column_texts("third")),
            ),
        ],
        hide_first_tag=True,
    )
    run_case(
        "stash pop 3 (missing index, should refuse)",
        fresh(with_stash),
        lambda: Stash(files=[], command=StashSubCommand.POP, stash_index="3"),
        [],
        expect_exit=True,
        hide_first_tag=True,
    )


def case_remote_ops():
    from git_sim.push import Push
    from git_sim.fetch import Fetch
    from git_sim.pull import Pull
    from git_sim.clone import Clone

    repo = fresh(local_ahead, name="pushrepo")
    r = git.Repo(repo)
    h = r.head.commit.hexsha
    run_case(
        "push (local ahead)",
        repo,
        lambda: Push(remote=None, branch=None, set_upstream=False),
        [
            (
                "origin/main label ends up above local HEAD",
                lambda c: c.refs().get("origin/main") == h,
            ),
            (
                "main and HEAD also above local HEAD",
                lambda c: c.refs().get("main") == h and c.refs().get("HEAD") == h,
            ),
        ],
    )
    repo_b = fresh(lambda p: remote_ahead(p, 1), name="pushbehind")
    run_case(
        "push (remote ahead -> rejected)",
        repo_b,
        lambda: Push(remote=None, branch=None, set_upstream=False),
        [
            (
                "explains the rejection",
                lambda c: any("failed" in t for t in c.text_values()),
            ),
        ],
    )
    repo_f = fresh(lambda p: remote_ahead(p, 2), name="fetchrepo")
    rf = git.Repo(repo_f)
    local_head = rf.head.commit.hexsha
    remote_tip = git.Repo(
        repo_f.parent / (repo_f.name + "_remote.git")
    ).head.commit.hexsha
    run_case(
        "fetch (remote ahead by 2)",
        repo_f,
        lambda: Fetch(remote=None, branch=None),
        [
            ("remote-only commits drawn", lambda c: remote_tip in c.commits()),
            (
                "origin/main above remote tip, main above local head",
                lambda c: c.refs().get("origin/main") == remote_tip
                and c.refs().get("main") == local_head,
            ),
        ],
    )
    repo_p = fresh(lambda p: remote_ahead(p, 2), name="pullrepo")
    remote_tip_p = git.Repo(
        repo_p.parent / (repo_p.name + "_remote.git")
    ).head.commit.hexsha
    run_case(
        "pull (fast-forward)",
        repo_p,
        lambda: Pull(remote=None, branch=None),
        [
            (
                "HEAD and main above the pulled remote tip",
                lambda c: c.refs().get("HEAD") == remote_tip_p
                and c.refs().get("main") == remote_tip_p,
            ),
        ],
    )
    repo_pc = fresh(lambda p: remote_ahead(p, 1, conflict=True), name="pullconf")
    run_case(
        "pull (conflict)",
        repo_pc,
        lambda: Pull(remote=None, branch=None),
        [
            (
                "conflicted file listed",
                lambda c: c.zone_files.get("second") == {"main.1"},
            ),
        ],
    )
    remote = with_remote(fresh(name="clonesrc"))
    run_case(
        "clone <bare path>",
        ROOT,
        lambda: Clone(url=str(remote).replace("\\", "/"), path="."),
        [
            ("cloned repo commits drawn", lambda c: len(c.commits()) >= 5),
            (
                "success text",
                lambda c: any("Successfully cloned" in t for t in c.text_values()),
            ),
        ],
        max_branches_per_commit=2,
    )


def case_meta():
    from git_sim.init import Init
    from git_sim.config import Config
    from git_sim.remote import Remote

    empty = ROOT / "empty_dir"
    empty.mkdir(exist_ok=True)
    run_case(
        "init (in a non-repo dir)",
        empty,
        lambda: Init(),
        [
            (
                "draws HEAD and .git/ entries",
                lambda c: "HEAD" in c.text_values() and ".git/" in c.text_values(),
            ),
        ],
    )
    run_case(
        "config --list",
        fresh(),
        lambda: Config(l=True, settings=None),
        [
            ("shows [core] section", lambda c: "[core]" in c.text_values()),
        ],
    )
    run_case(
        "config user.name Foo",
        fresh(),
        lambda: Config(l=False, settings=["user.name", "Foo"]),
        [
            (
                "shows section and option",
                lambda c: "[user]" in c.text_values()
                and "name = Foo" in c.text_values(),
            ),
        ],
    )
    remoted = fresh(with_remote)
    run_case(
        "remote (list)",
        remoted,
        lambda: Remote(command=None, remote=None, url_or_path=None),
        [
            (
                'shows [remote "origin"]',
                lambda c: '[remote "origin"]' in c.text_values(),
            ),
        ],
    )
    run_case(
        "remote add upstream url",
        fresh(with_remote),
        lambda: Remote(
            command=RemoteSubCommand.ADD,
            remote="upstream",
            url_or_path="https://x/y.git",
        ),
        [
            (
                "new section drawn",
                lambda c: '[remote "upstream"]' in c.text_values()
                and "url = https://x/y.git" in c.text_values(),
            ),
        ],
    )
    run_case(
        "remote rename origin up",
        fresh(with_remote),
        lambda: Remote(
            command=RemoteSubCommand.RENAME, remote="origin", url_or_path="up"
        ),
        [
            ("renamed section drawn", lambda c: '[remote "up"]' in c.text_values()),
        ],
    )
    run_case(
        "remote remove origin",
        fresh(with_remote),
        lambda: Remote(
            command=RemoteSubCommand.REMOVE, remote="origin", url_or_path=None
        ),
        [
            (
                "origin section struck through",
                lambda c: any(
                    t.text == '[remote "origin"]' and t.strikethrough for t in c.texts()
                ),
            ),
        ],
    )
    run_case(
        "remote get-url origin",
        fresh(with_remote),
        lambda: Remote(
            command=RemoteSubCommand.GET_URL, remote="origin", url_or_path=None
        ),
        [
            ("renders", lambda c: True),
        ],
    )

    def many_remotes(p):
        with_remote(p)
        for i in range(8):
            g(p, "remote", "add", f"mirror{i}", f"https://example.com/mirror{i}.git")

    run_case(
        "remote (list, 9 remotes -> box must grow)",
        fresh(many_remotes),
        lambda: Remote(command=None, remote=None, url_or_path=None),
        [
            (
                "all remote sections drawn",
                lambda c: all(
                    f'[remote "mirror{i}"]' in c.text_values() for i in range(8)
                ),
            ),
            (
                "box tall enough to contain the last line",
                lambda c: c.scene.project_root.get_bottom()[1]
                < min(
                    t.get_bottom()[1] for t in c.texts() if t.text.startswith("[remote")
                ),
            ),
        ],
    )
    run_case(
        "remote set-url origin newurl",
        fresh(with_remote),
        lambda: Remote(
            command=RemoteSubCommand.SET_URL,
            remote="origin",
            url_or_path="https://new/url.git",
        ),
        [
            ("new url drawn", lambda c: "url = https://new/url.git" in c.text_values()),
        ],
    )


for fn in (
    case_log,
    case_reset,
    case_commit,
    case_merge,
    case_rebase,
    case_cherry_pick,
    case_revert,
    case_branch_tag,
    case_checkout_switch,
    case_zones,
    case_remote_ops,
    case_meta,
):
    try:
        fn()
    except Exception:
        RESULTS.append(
            (fn.__name__, "HARNESS", traceback.format_exc().strip().splitlines()[-1])
        )

width = max(len(n) for n, _, _ in RESULTS)
counts = {}
for name, status, notes in RESULTS:
    counts[status] = counts.get(status, 0) + 1
    print(f"{status:6} {name.ljust(width)}  {notes}")
print("\nsummary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
print("images:", OUT)
print("fixtures:", ROOT)
