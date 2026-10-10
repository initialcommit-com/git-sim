"""Sanity-test git-sim on real open-source repositories, before a release.

Not part of the normal test run (pytest never collects it): run it when asked.

    python tests/sanity/sanity.py clone              # once: fetch the repositories
    python tests/sanity/sanity.py run                # every repository, a few at a time
    python tests/sanity/sanity.py run flask git -j 2
    python tests/sanity/sanity.py run express --scenario "merge: conflict"
    python tests/sanity/sanity.py report             # the summary of the last run
    python tests/sanity/sanity.py list               # the repositories and scenarios

Run it with git-sim's environment (the Python that has git_sim installed).
Everything it writes goes under tests/sanity/.work (git-ignored), or --dir.

For each repository and scenario it sets up a situation on the repository's
own files, runs git-sim exactly as a user would, reads the drawing back
(tests/validation/svgmodel.py), asks pre-flight for its facts where the
command is risky, runs the real git command, and compares what git-sim
predicted with what git did. See "The sanity run" in docs/testing.md.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GIT_SIM = HERE.parents[1]  # the git-sim checkout
sys.path.insert(0, str(GIT_SIM / "tests" / "validation"))
import svgmodel  # noqa: E402

# The repositories, simplest first. Clones are full (every branch), as the
# scenarios merge and rebase the projects' own branches.
REPOS = {
    "hello-world": "https://github.com/octocat/Hello-World.git",             # 5 commits, one merge
    "hellogitworld": "https://github.com/githubtraining/hellogitworld.git",  # small, many branches, 4 roots
    "itsdangerous": "https://github.com/pallets/itsdangerous.git",           # a small real project
    "flask": "https://github.com/pallets/flask.git",                         # thousands of merges, many tags
    "express": "https://github.com/expressjs/express.git",                   # long history, maintenance branches
    "git": "https://github.com/git/git.git",                                 # 85k commits, octopus and criss-cross merges, a submodule
}

TIMEOUT = 300  # seconds for one git-sim run
SLOW = 60      # seconds: flagged as slow

# set by configure()
PY = sys.executable
WORKDIR = SRC = WORK = MEDIA = RESULTS = LOGS = None
ENV = {}


def configure(workdir):
    """Point every path at one working folder, and give git and git-sim a
    private, predictable environment (no user git config, no git_sim_*
    settings)."""
    global WORKDIR, SRC, WORK, MEDIA, RESULTS, LOGS
    WORKDIR = Path(workdir).resolve()
    SRC, WORK, MEDIA = WORKDIR / "src", WORKDIR / "work", WORKDIR / "media"
    RESULTS, LOGS = WORKDIR / "results", WORKDIR / "logs"
    WORKDIR.mkdir(parents=True, exist_ok=True)
    cfg = WORKDIR / "gitconfig"
    cfg.write_text(
        "[user]\n\tname = Sanity Tester\n\temail = sanity@example.com\n"
        "[init]\n\tdefaultBranch = main\n[core]\n\tautocrlf = false\n\tlongpaths = true\n"
        "[advice]\n\tdetachedHead = false\n[pull]\n\trebase = false\n[commit]\n\tgpgsign = false\n"
        "[merge]\n\tautoStash = false\n[rebase]\n\tautoStash = false\n",
        encoding="utf-8",
    )
    ENV.clear()
    ENV.update({k: v for k, v in os.environ.items() if not k.lower().startswith("git_sim_")})
    ENV.update(GIT_CONFIG_GLOBAL=str(cfg), GIT_CONFIG_NOSYSTEM="1", GIT_EDITOR="true", GIT_TERMINAL_PROMPT="0",
               GIT_MERGE_AUTOEDIT="no", PYTHONIOENCODING="utf-8")


# ---------------------------------------------------------------------------
# git, git-sim
# ---------------------------------------------------------------------------
def g(repo, *args, check=True, env=None, stdin=None):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env or ENV, input=stdin)
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)} -> {p.returncode}: {(p.stderr or p.stdout).strip()[-400:]}")
    return p


def out(repo, *args):
    return g(repo, *args).stdout.strip()


def sha(repo, rev):
    return out(repo, "rev-parse", "--verify", rev + "^{commit}")


def gitsim(repo, args, fmt="svg"):
    MEDIA.mkdir(parents=True, exist_ok=True)
    cmd = [PY, "-m", "git_sim", "-d", "--img-format", fmt, "--output-only-path", "--media-dir", str(MEDIA), *args]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=ENV, timeout=TIMEOUT)
        rc, text = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        rc, text = "timeout", str(e.stdout or "")[-2000:]
    secs = round(time.time() - t0, 2)
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    path = next((l for l in reversed(lines) if l.lower().endswith("." + fmt) and Path(l).exists()), None)
    refused = next((l.split("git-sim error:", 1)[1].strip() for l in lines if "git-sim error:" in l), None)
    return {"rc": rc, "secs": secs, "path": path, "traceback": "Traceback (most recent call last)" in text,
            "refused": refused, "tail": "\n".join(lines[-12:])}


def preflight(repo, command):
    p = subprocess.run([PY, "-m", "git_sim", "preflight", "--json", "--", *command.split()], cwd=repo,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=TIMEOUT)
    txt = p.stdout
    try:
        return json.loads(txt[txt.index("{"):])
    except Exception:
        return {"error": "unparseable", "tail": (txt + p.stderr)[-600:], "traceback": "Traceback" in (txt + p.stderr)}


# ---------------------------------------------------------------------------
# the repository under test
# ---------------------------------------------------------------------------
TEXT_EXT = (".py", ".md", ".rst", ".txt", ".js", ".c", ".h", ".sh", ".json", ".yml", ".yaml", ".toml", ".cfg", ".html", ".css", ".java", ".adoc")


class Ctx:
    def __init__(self, name):
        self.name = name
        self.src = SRC / name
        self.repo = WORK / name
        self.default = out(self.src, "symbolic-ref", "--short", "HEAD")
        if self.repo.exists():
            shutil.rmtree(self.repo, onerror=_writable)
        WORK.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(self.src), str(self.repo)],
                       check=True, env=ENV)
        g(self.repo, "checkout", "-q", self.default)
        g(self.repo, "fetch", "-q", str(self.src), "+refs/remotes/origin/*:refs/remotes/origin/*")
        self.files = self._text_files()
        # too few editable files (a tiny repository): add some, once, on the base
        if len(self.files) < 10:
            for k in range(10 - len(self.files)):
                name = f"sanity_{k}.txt"
                (self.repo / name).write_text("".join(f"line {n}\n" for n in range(40)), encoding="utf-8", newline="\n")
                self.files.append(name)
            g(self.repo, "add", "-A")
            g(self.repo, "commit", "-q", "-m", "Add files for the sanity scenarios")
        self.base = sha(self.repo, "HEAD")

    def _text_files(self):
        found = []
        for f in out(self.repo, "ls-files").splitlines():
            if not f.lower().endswith(TEXT_EXT) or "/" in f and f.count("/") > 3:
                continue
            p = self.repo / f
            try:
                data = p.read_bytes()
            except OSError:
                continue
            if b"\0" in data or len(data) > 150_000 or data.count(b"\n") < 14:
                continue
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            found.append(f)
        return sorted(found, key=lambda f: (f.count("/"), len(f), f))[:40]

    def reset(self):
        r = self.repo
        for op in (["merge", "--abort"], ["rebase", "--abort"], ["cherry-pick", "--abort"], ["revert", "--abort"],
                   ["bisect", "reset"]):
            g(r, *op, check=False)
        for wt in out(r, "worktree", "list", "--porcelain").splitlines():
            if wt.startswith("worktree ") and "sanity-wt" in wt:
                g(r, "worktree", "remove", "--force", wt.split(" ", 1)[1], check=False)
        g(r, "worktree", "prune", check=False)
        g(r, "checkout", "-q", "-f", self.default)
        g(r, "reset", "-q", "--hard", self.base)
        g(r, "clean", "-q", "-fdx")
        g(r, "stash", "clear")
        for b in out(r, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines():
            if b != self.default:
                g(r, "branch", "-q", "-D", b)
        for t in out(r, "tag", "-l", "sanity-*").splitlines():
            g(r, "tag", "-d", t)
        g(r, "reflog", "expire", "--expire=now", "--all", check=False)

    # -- building a situation ------------------------------------------------
    def file(self, i):
        """A real text file of the repository (the i-th), or a new one when the
        repository has too few."""
        if i < len(self.files):
            return self.files[i]
        name = f"sanity_{i}.txt"
        p = self.repo / name
        if not p.exists():
            p.write_text("".join(f"line {n}\n" for n in range(40)), encoding="utf-8", newline="\n")
            g(self.repo, "add", name)
            g(self.repo, "commit", "-q", "-m", f"Add {name}")
        return name

    def edit(self, path, line, text):
        p = self.repo / path
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("".join(f"line {n}\n" for n in range(40)), encoding="utf-8", newline="\n")
        data = p.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in data else "\n"
        lines = data.split(nl)
        while len(lines) <= line:
            lines.append("")
        lines[line] = text
        p.write_bytes(nl.join(lines).encode("utf-8"))

    def commit(self, msg, *paths):
        g(self.repo, "add", *(paths or ["-A"]))
        g(self.repo, "commit", "-q", "-m", msg)
        return sha(self.repo, "HEAD")

    def branch(self, name, start="HEAD"):
        g(self.repo, "switch", "-q", "-c", name, start)

    def switch(self, name):
        g(self.repo, "switch", "-q", name)

    def dirty(self):
        """One staged, one modified, one untracked file."""
        self.edit(self.file(0), 3, "sanity: staged edit")
        g(self.repo, "add", self.file(0))
        self.edit(self.file(1), 4, "sanity: unstaged edit")
        (self.repo / "sanity_untracked.txt").write_text("untracked\n", encoding="utf-8")


def _writable(func, path, _exc):
    os.chmod(path, 0o666)
    func(path)


def snapshot(ctx):
    r = ctx.repo
    st = {"staged": [], "modified": [], "untracked": [], "conflicts": []}
    raw = g(r, "status", "--porcelain", "-z", "--untracked-files=all", check=False).stdout
    for rec in raw.split("\0"):
        if len(rec) < 4:
            continue
        x, y, path = rec[0], rec[1], rec[3:]
        if "U" in (x, y) or (x == y and x in "AD"):
            st["conflicts"].append(path)
        elif rec[:2] == "??":
            st["untracked"].append(path)
        else:
            if x != " ":
                st["staged"].append(path)
            if y != " ":
                st["modified"].append(path)
    refs = dict(line.split(" ", 1)[::-1] for line in out(r, "for-each-ref", "--format=%(objectname) %(refname)",
                                                         "refs/heads", "refs/tags", "refs/stash", "refs/remotes").splitlines() if line)
    return {"head": sha(r, "HEAD"), "branch": out(r, "branch", "--show-current") or None, "status": st, "refs": refs,
            "stash": len(out(r, "stash", "list").splitlines())}


def new_commits(ctx, before):
    """Commits reachable from HEAD now and from no ref (or HEAD) before."""
    olds = set(before["refs"].values()) | {before["head"]}
    lst = g(ctx.repo, "rev-list", "HEAD", "--stdin", stdin="--not\n" + "\n".join(olds) + "\n").stdout.strip()
    return lst.split() if lst else []


def orphaned(ctx, before):
    """Commits reachable from the old HEAD that nothing reaches now."""
    now = [v for v in snapshot(ctx)["refs"].values()] + [sha(ctx.repo, "HEAD")]
    lst = g(ctx.repo, "rev-list", before["head"], "--stdin", stdin="--not\n" + "\n".join(now) + "\n").stdout.strip()
    return lst.split() if lst else []


# ---------------------------------------------------------------------------
# what the drawing says
# ---------------------------------------------------------------------------
def after_commits(model):
    return svgmodel.commits_by_phase(model, "after")


def removed_commits(model):
    return svgmodel.commits_by_phase(model, "removed")


def files(model, column, phase=None):
    return set(svgmodel.files_in(model, column, phase))


def same_files(label, drawn, real):
    drawn = {Path(f).as_posix() for f in drawn}
    real = {Path(f).as_posix() for f in real}
    if drawn == real:
        return []
    # the drawing may name a folder where git lists its files
    norm = lambda s: {f.split("/")[0] for f in s}
    if norm(drawn) == norm(real):
        return []
    return [f"{label}: drawn {sorted(drawn)[:8]} but git says {sorted(real)[:8]}"]


# ---------------------------------------------------------------------------
# scenarios: setup(ctx) -> info; sim(ctx, info) -> git-sim args;
# real(ctx, info) -> the git command run afterwards; check(...) -> problems
# ---------------------------------------------------------------------------
SCENARIOS = []


def scenario(name, cat, sim, setup=None, real=None, check=None, pf=None, refuse=False, only=None, fmt="svg"):
    SCENARIOS.append(dict(name=name, cat=cat, setup=setup, sim=sim, real=real, check=check, pf=pf, refuse=refuse,
                          only=only, fmt=fmt))


def topic(ctx, name, n, fileno=5, line=6, start="HEAD"):
    """A branch with n commits on its own file, then back to the default branch."""
    ctx.branch(name, start)
    shas = []
    for i in range(n):
        ctx.edit(ctx.file(fileno), line + 6 * i, f"sanity: {name} change {i}")
        shas.append(ctx.commit(f"{name}: change {i}"))
    ctx.switch(ctx.default)
    return shas


def conflict_pair(ctx, fileno=2, line=8):
    """main and topic both change the same line of the same file."""
    ctx.branch("conflict-topic")
    ctx.edit(ctx.file(fileno), line, "sanity: the topic's version of this line")
    ctx.commit("Topic edits a shared line")
    ctx.switch(ctx.default)
    ctx.edit(ctx.file(fileno), line, "sanity: main's version of this line")
    ctx.commit("Main edits the same line")
    return {"file": ctx.file(fileno)}


# -- history and inspection --------------------------------------------------------------
scenario("log", "history", lambda c, i: ["log"])
scenario("log --all", "history", lambda c, i: ["--all", "log"])
scenario("log -n 30 --all", "history", lambda c, i: ["--all", "-n", "30", "log"])
scenario("log at a root commit", "history", setup=lambda c: g(c.repo, "checkout", "-q", out(c.repo, "rev-list", "--max-parents=0", "HEAD").split()[-1]),
         sim=lambda c, i: ["log"])
scenario("log at an octopus merge", "history", only=["git"],
         setup=lambda c: g(c.repo, "checkout", "-q", out(c.repo, "rev-list", "--min-parents=3", "-1", "--all")),
         sim=lambda c, i: ["log"],
         check=lambda c, i, m, *_: [] if any(len(x["parents"]) >= 3 for x in m["commits"].values()) else ["the octopus merge is not drawn with its 3+ parents"])
scenario("log across the most recent merges", "history", setup=lambda c: g(c.repo, "checkout", "-q", out(c.repo, "rev-list", "--merges", "-1", "HEAD") or "HEAD"),
         sim=lambda c, i: ["-n", "20", "log"])
scenario("status on a dirty tree", "inspect", setup=lambda c: c.dirty(), sim=lambda c, i: ["status"],
         check=lambda c, i, m, pre, b, a, rc: same_files("staged", files(m, "Staged"), b["status"]["staged"])
         + same_files("modified", files(m, "Modified"), b["status"]["modified"])
         + same_files("untracked", files(m, "Untracked"), b["status"]["untracked"]))
scenario("show HEAD", "inspect", lambda c, i: ["show"])
scenario("show a merge commit", "inspect", lambda c, i: ["show", out(c.repo, "rev-list", "--merges", "-1", "HEAD") or "HEAD"])
scenario("show a file at a past revision", "inspect", lambda c, i: ["show", "HEAD~1:" + out(c.repo, "ls-tree", "--name-only", "HEAD~1").splitlines()[0]])
scenario("diff HEAD~3 HEAD", "inspect", lambda c, i: ["diff", "HEAD~3", "HEAD"] if int(out(c.repo, "rev-list", "--count", "--first-parent", "HEAD")) > 3 else ["diff", "HEAD~1", "HEAD"])
scenario("diff --staged", "inspect", setup=lambda c: c.dirty(), sim=lambda c, i: ["diff", "--staged"])
scenario("blame a file", "inspect", lambda c, i: ["blame", c.file(0)])
scenario("reflog", "inspect", setup=lambda c: (topic(c, "reflog-topic", 2), c.switch("reflog-topic"), c.switch(c.default)), sim=lambda c, i: ["reflog"])

# -- working tree --------------------------------------------------------------------------
scenario("add", "tree", setup=lambda c: c.dirty(), sim=lambda c, i: ["add", c.file(1), "sanity_untracked.txt"],
         real=lambda c, i: ["add", c.file(1), "sanity_untracked.txt"],
         check=lambda c, i, m, pre, b, a, rc: same_files("staged after add", files(m, "Staged"), a["status"]["staged"]))
scenario("restore --staged", "tree", setup=lambda c: c.dirty(), sim=lambda c, i: ["restore", "--staged", c.file(0)],
         real=lambda c, i: ["restore", "--staged", c.file(0)])
scenario("restore (discard an edit)", "tree", setup=lambda c: c.dirty(), sim=lambda c, i: ["restore", c.file(1)],
         real=lambda c, i: ["restore", c.file(1)], pf=lambda c, i: f"restore {c.file(1)}",
         check=lambda c, i, m, pre, b, a, rc: [] if pre.get("risk") == "destructive" else [f"pre-flight rates discarding an edit {pre.get('risk')}"])
scenario("rm", "tree", sim=lambda c, i: ["rm", c.file(3)], real=lambda c, i: ["rm", "-q", c.file(3)])
scenario("mv", "tree", sim=lambda c, i: ["mv", c.file(3), "sanity_moved" + Path(c.file(3)).suffix],
         real=lambda c, i: ["mv", c.file(3), "sanity_moved" + Path(c.file(3)).suffix])
scenario("clean -fd", "tree", setup=lambda c: (c.dirty(), (c.repo / "sanity_dir").mkdir(), (c.repo / "sanity_dir" / "x.txt").write_text("x\n")),
         sim=lambda c, i: ["clean", "-f", "-d"], real=lambda c, i: ["clean", "-f", "-d"], pf=lambda c, i: "clean -fd",
         check=lambda c, i, m, pre, b, a, rc: same_files("deleted", files(m, "Deleted"), b["status"]["untracked"])
         + ([] if pre.get("risk") == "destructive" else [f"pre-flight rates clean -fd {pre.get('risk')}"]))
scenario("stash", "tree", setup=lambda c: c.dirty(), sim=lambda c, i: ["stash"], real=lambda c, i: ["stash", "-q"],
         check=lambda c, i, m, pre, b, a, rc: same_files("stashed", files(m, "Stashed"), b["status"]["staged"] + b["status"]["modified"]))
scenario("stash -u", "tree", setup=lambda c: c.dirty(), sim=lambda c, i: ["stash", "push", "--include-untracked"], real=lambda c, i: ["stash", "-q", "-u"],
         check=lambda c, i, m, pre, b, a, rc: same_files("stashed", files(m, "Stashed"), b["status"]["staged"] + b["status"]["modified"] + b["status"]["untracked"]))
scenario("stash pop", "tree", setup=lambda c: (c.dirty(), g(c.repo, "stash", "-q")), sim=lambda c, i: ["stash", "pop"], real=lambda c, i: ["stash", "pop", "-q"])

# -- commits -----------------------------------------------------------------------------------
scenario("commit", "commit", setup=lambda c: c.dirty(), sim=lambda c, i: ["commit", "-m", "Sanity commit"], real=lambda c, i: ["commit", "-q", "-m", "Sanity commit"],
         check=lambda c, i, m, pre, b, a, rc: [] if len(after_commits(m)) == len(new_commits(c, b)) == 1 else [f"drew {len(after_commits(m))} new commit(s), git made {len(new_commits(c, b))}"])
scenario("commit --amend", "commit", setup=lambda c: c.dirty(), sim=lambda c, i: ["commit", "--amend", "--no-edit"], real=lambda c, i: ["commit", "-q", "--amend", "--no-edit"],
         pf=lambda c, i: "commit --amend --no-edit",
         check=lambda c, i, m, pre, b, a, rc: [] if len(after_commits(m)) == 1 else [f"drew {len(after_commits(m))} replacement commits for an amend"])
scenario("revert HEAD", "commit", setup=lambda c: (c.edit(c.file(5), 12, "sanity: to revert"), c.commit("A commit to revert")),
         sim=lambda c, i: ["revert", "HEAD"], real=lambda c, i: ["revert", "--no-edit", "HEAD"],
         check=lambda c, i, m, pre, b, a, rc: [] if rc != 0 or len(after_commits(m)) == len(new_commits(c, b)) else [f"drew {len(after_commits(m))} revert commit(s), git made {len(new_commits(c, b))}"])
scenario("revert a merge (-m 1)", "commit", setup=lambda c: c.__dict__.update(merge=out(c.repo, "rev-list", "--merges", "-1", "HEAD")),
         sim=lambda c, i: ["revert", "-m", "1", c.merge] if c.merge else ["revert", "HEAD"],
         real=lambda c, i: ["revert", "--no-edit", "-m", "1", c.merge] if c.merge else ["revert", "--no-edit", "HEAD"])
scenario("cherry-pick one commit", "commit", setup=lambda c: {"picks": topic(c, "pick-topic", 3)},
         sim=lambda c, i: ["cherry-pick", "pick-topic~1"], real=lambda c, i: ["cherry-pick", "pick-topic~1"],
         check=lambda c, i, m, pre, b, a, rc: [] if len(after_commits(m)) == len(new_commits(c, b)) else [f"drew {len(after_commits(m))}, git made {len(new_commits(c, b))}"])
scenario("cherry-pick a range", "commit", setup=lambda c: {"picks": topic(c, "range-topic", 4)},
         sim=lambda c, i: ["cherry-pick", "range-topic~3..range-topic"], real=lambda c, i: ["cherry-pick", "range-topic~3..range-topic"],
         check=lambda c, i, m, pre, b, a, rc: [] if len(after_commits(m)) == len(new_commits(c, b)) else [f"drew {len(after_commits(m))} picked commits, git made {len(new_commits(c, b))}"])
scenario("cherry-pick that conflicts", "conflict", setup=lambda c: conflict_pair(c),
         sim=lambda c, i: ["cherry-pick", "conflict-topic"], real=lambda c, i: ["cherry-pick", "conflict-topic"],
         check=lambda c, i, m, pre, b, a, rc: ([] if rc != 0 else ["git applied the pick cleanly; the setup meant a conflict"])
         + ([] if svgmodel.has_text(m, "conflict") else ["git stops on a conflict but the drawing does not mention one"]))

# -- branches ------------------------------------------------------------------------------------
scenario("branch", "branch", sim=lambda c, i: ["branch", "sanity-new"], real=lambda c, i: ["branch", "sanity-new"])
scenario("switch -c", "branch", sim=lambda c, i: ["switch", "-c", "sanity-new"], real=lambda c, i: ["switch", "-q", "-c", "sanity-new"])
scenario("checkout a tag (detached)", "branch", setup=lambda c: c.__dict__.update(tag=(out(c.repo, "describe", "--tags", "--abbrev=0") if out(c.repo, "tag") else None)),
         sim=lambda c, i: ["checkout", c.tag] if c.tag else ["checkout", "HEAD~1"], real=lambda c, i: ["checkout", "-q", c.tag or "HEAD~1"])
scenario("switch with a dirty tree", "branch", setup=lambda c: (topic(c, "dirty-topic", 1), c.dirty()),
         sim=lambda c, i: ["switch", "dirty-topic"], pf=lambda c, i: "switch dirty-topic")
scenario("branch -D unmerged", "branch", setup=lambda c: {"picks": topic(c, "doomed", 3)}, sim=lambda c, i: ["branch", "-D", "doomed"],
         real=lambda c, i: ["branch", "-D", "doomed"], pf=lambda c, i: "branch -D doomed",
         check=lambda c, i, m, pre, b, a, rc: ([] if pre.get("risk") == "destructive" else [f"pre-flight rates branch -D of 3 unmerged commits {pre.get('risk')}"])
         + ([] if len(orphaned_branch(c, b, "doomed")) == 3 else ["setup did not orphan 3 commits"]))
scenario("branch -d refuses an unmerged branch", "branch", setup=lambda c: topic(c, "unmerged", 2), sim=lambda c, i: ["branch", "-d", "unmerged"], refuse=True)
scenario("tag", "branch", sim=lambda c, i: ["tag", "sanity-v1"], real=lambda c, i: ["tag", "sanity-v1"])
scenario("worktree add", "branch", sim=lambda c, i: ["worktree", "add", "../sanity-wt-" + c.name, "-b", "sanity-wt-branch"],
         real=lambda c, i: ["worktree", "add", "-q", "-b", "sanity-wt-branch", str(WORK / ("sanity-wt-" + c.name))])

# -- merges ----------------------------------------------------------------------------------------
def merge_check(kind):
    def check(c, i, m, pre, b, a, rc):
        probs, made = [], new_commits(c, b)
        drawn_merges = [x for x in after_commits(m).values() if len(x["parents"]) >= 2]
        if kind == "ff":
            if made:
                probs.append(f"git made {len(made)} commit(s) on a fast-forward")
            if drawn_merges:
                probs.append("drew a merge commit for a fast-forward")
        elif kind == "merge":
            if rc != 0:
                probs.append("git did not merge cleanly")
            real_merge = [x for x in made if len(out(c.repo, "rev-list", "--parents", "-n1", x).split()) >= 3]
            if len(drawn_merges) != len(real_merge):
                probs.append(f"drew {len(drawn_merges)} merge commit(s), git made {len(real_merge)}")
            elif drawn_merges:
                want = out(c.repo, "rev-list", "--parents", "-n1", real_merge[0]).split()[1:]
                got = drawn_merges[0]["parents"]
                if [p[:7] for p in got] != [p[:7] for p in want]:
                    probs.append(f"merge parents drawn {[p[:7] for p in got]}, git's {[p[:7] for p in want]}")
                git_msg = out(c.repo, "log", "-1", "--format=%s", real_merge[0])
                drawn_msg = drawn_merges[0]["message"]
                if not (drawn_msg == git_msg or (len(drawn_msg) >= 40 and git_msg.startswith(drawn_msg))):
                    probs.append(f"merge message drawn {drawn_msg!r}, git wrote {git_msg!r}")
        elif kind == "conflict":
            if rc == 0:
                probs.append("git merged cleanly; the setup meant a conflict")
            probs += same_files("conflicted", files(m, "Conflicted"), a["status"]["conflicts"])
        elif kind == "squash":
            if made:
                probs.append("git committed on --squash")
            probs += same_files("staged by --squash", files(m, "Staging", "after") or files(m, "Staged"), a["status"]["staged"])
        return probs
    return check


scenario("merge: fast-forward", "merge", setup=lambda c: (topic(c, "ff-topic", 3)), sim=lambda c, i: ["merge", "ff-topic"],
         real=lambda c, i: ["merge", "-q", "ff-topic"], check=merge_check("ff"))
scenario("merge: --no-ff", "merge", setup=lambda c: topic(c, "noff-topic", 2), sim=lambda c, i: ["merge", "--no-ff", "noff-topic"],
         real=lambda c, i: ["merge", "-q", "--no-ff", "--no-edit", "noff-topic"], check=merge_check("merge"))
scenario("merge: diverged, clean (three-way)", "merge",
         setup=lambda c: (topic(c, "div-topic", 2, fileno=5), c.edit(c.file(6), 2, "sanity: main moves on"), c.commit("Main moves on")),
         sim=lambda c, i: ["merge", "div-topic"], real=lambda c, i: ["merge", "-q", "--no-edit", "div-topic"], check=merge_check("merge"))
scenario("merge: conflict", "conflict", setup=lambda c: conflict_pair(c), sim=lambda c, i: ["merge", "conflict-topic"],
         real=lambda c, i: ["merge", "--no-edit", "conflict-topic"], check=merge_check("conflict"), pf=lambda c, i: "merge conflict-topic")
scenario("merge: conflict in two files", "conflict",
         setup=lambda c: (conflict_pair(c, 2, 8), g(c.repo, "switch", "-q", "conflict-topic"), c.edit(c.file(3), 9, "sanity: topic line two"), c.commit("Topic edits another shared line"),
                          c.switch(c.default), c.edit(c.file(3), 9, "sanity: main line two"), c.commit("Main edits it too")),
         sim=lambda c, i: ["merge", "conflict-topic"], real=lambda c, i: ["merge", "--no-edit", "conflict-topic"], check=merge_check("conflict"))
scenario("merge: modify/delete conflict", "conflict",
         setup=lambda c: (c.branch("del-topic"), g(c.repo, "rm", "-q", c.file(4)), c.commit("Topic deletes a file"), c.switch(c.default),
                          c.edit(c.file(4), 5, "sanity: main edits the file the topic deletes"), c.commit("Main edits it")),
         sim=lambda c, i: ["merge", "del-topic"], real=lambda c, i: ["merge", "--no-edit", "del-topic"], check=merge_check("conflict"))
scenario("merge: rename on one side, edit on the other", "merge",
         setup=lambda c: (c.branch("ren-topic"), g(c.repo, "mv", c.file(4), "sanity_renamed" + Path(c.file(4)).suffix), c.commit("Topic renames a file"),
                          c.switch(c.default), c.edit(c.file(4), 5, "sanity: main edits the renamed file"), c.commit("Main edits it")),
         sim=lambda c, i: ["merge", "ren-topic"], real=lambda c, i: ["merge", "-q", "--no-edit", "ren-topic"], check=merge_check("merge"))
scenario("merge: --squash", "merge", setup=lambda c: topic(c, "sq-topic", 3), sim=lambda c, i: ["merge", "--squash", "sq-topic"],
         real=lambda c, i: ["merge", "-q", "--squash", "sq-topic"], check=merge_check("squash"))
scenario("merge: criss-cross (two merge bases)", "merge",
         setup=lambda c: criss_cross(c), sim=lambda c, i: ["merge", "cc-b"], real=lambda c, i: ["merge", "-q", "--no-edit", "cc-b"], check=merge_check("merge"))
scenario("merge: unrelated histories are refused", "merge",
         setup=lambda c: (g(c.repo, "switch", "-q", "--orphan", "island"), g(c.repo, "read-tree", "--empty"), g(c.repo, "clean", "-q", "-fdx"), (c.repo / "island.txt").write_text("island\n"),
                          c.commit("An unrelated root"), c.switch(c.default)),
         sim=lambda c, i: ["merge", "island"], real=lambda c, i: ["merge", "--no-edit", "island"],
         check=lambda c, i, m, pre, b, a, rc: ([] if rc != 0 else ["git merged unrelated histories without --allow-unrelated-histories"])
         + ([] if "refuses" in (pre.get("summary") or "") else [f"pre-flight: {pre.get('summary')}"]), refuse=True, pf=lambda c, i: "merge island")
scenario("merge: --ff-only (fast-forward)", "merge", setup=lambda c: topic(c, "ffo-topic", 2), sim=lambda c, i: ["merge", "--ff-only", "ffo-topic"],
         real=lambda c, i: ["merge", "-q", "--ff-only", "ffo-topic"], check=merge_check("ff"))
scenario("merge: --ff-only (diverged) is refused", "merge",
         setup=lambda c: (topic(c, "ffd-topic", 2, fileno=5), c.edit(c.file(6), 2, "sanity: main moves on"), c.commit("Main moves on")),
         sim=lambda c, i: ["merge", "--ff-only", "ffd-topic"], real=lambda c, i: ["merge", "--ff-only", "ffd-topic"], refuse=True,
         pf=lambda c, i: "merge --ff-only ffd-topic",
         check=lambda c, i, m, pre, b, a, rc: ([] if rc != 0 else ["git fast-forwarded"]) + ([] if "refuses" in (pre.get("summary") or "") else [f"pre-flight: {pre.get('summary')}"]))
scenario("merge: --allow-unrelated-histories", "merge",
         setup=lambda c: (g(c.repo, "switch", "-q", "--orphan", "island"), g(c.repo, "read-tree", "--empty"), g(c.repo, "clean", "-q", "-fdx"), (c.repo / "island.txt").write_text("island\n"),
                          c.commit("An unrelated root"), c.switch(c.default)),
         sim=lambda c, i: ["merge", "--allow-unrelated-histories", "island"], real=lambda c, i: ["merge", "-q", "--no-edit", "--allow-unrelated-histories", "island"],
         check=merge_check("merge"))
scenario("merge: a diverged remote-tracking branch", "merge",
         setup=lambda c: (g(c.repo, "switch", "-q", "-c", "behind", f"origin/{c.default}~1"), c.edit(c.file(5), 30, "sanity: local work"), c.commit("Local work")),
         sim=lambda c, i: ["merge", f"origin/{c.default}"], real=lambda c, i: ["merge", "--no-edit", f"origin/{c.default}"],
         check=lambda c, i, m, pre, b, a, rc: merge_check("conflict" if rc else "merge")(c, i, m, pre, b, a, rc))
scenario("merge --abort (stopped merge)", "resume", setup=lambda c: (conflict_pair(c), g(c.repo, "merge", "conflict-topic", check=False)),
         sim=lambda c, i: ["merge", "--abort"], real=lambda c, i: ["merge", "--abort"])
scenario("merge --continue (resolved)", "resume",
         setup=lambda c: (conflict_pair(c), g(c.repo, "merge", "conflict-topic", check=False), g(c.repo, "checkout", "--ours", "--", c.file(2)), g(c.repo, "add", c.file(2))),
         sim=lambda c, i: ["merge", "--continue"], real=lambda c, i: ["commit", "-q", "--no-edit"],
         check=lambda c, i, m, pre, b, a, rc: [] if sum(len(x["parents"]) >= 2 for x in after_commits(m).values()) == 1 else ["no merge commit drawn for merge --continue"])

# -- rebases ----------------------------------------------------------------------------------------
def rebase_setup(c, n=3, conflict=False):
    topic(c, "rb-topic", n, fileno=5)
    c.edit(c.file(6), 2, "sanity: main moves on")
    c.commit("Main moves on")
    if conflict:
        c.edit(c.file(5), 6, "sanity: main's own version")
        c.commit("Main edits the topic's line")
    c.switch("rb-topic")


def rebase_check(c, i, m, pre, b, a, rc):
    made = new_commits(c, b)
    if rc != 0:
        return ["git's rebase stopped"]
    drawn = len(after_commits(m))
    return [] if drawn == len(made) else [f"drew {drawn} replayed commit(s), git made {len(made)}"]


scenario("rebase: clean", "rebase", setup=lambda c: rebase_setup(c), sim=lambda c, i: ["rebase", c.default],
         real=lambda c, i: ["rebase", "-q", c.default], check=rebase_check, pf=lambda c, i: f"rebase {c.default}")
scenario("rebase: already up to date", "rebase", setup=lambda c: topic(c, "utd", 2) and c.switch("utd"), sim=lambda c, i: ["rebase", c.default],
         real=lambda c, i: ["rebase", "-q", c.default], refuse=True)
scenario("rebase: conflict", "conflict", setup=lambda c: rebase_setup(c, conflict=True), sim=lambda c, i: ["rebase", c.default],
         real=lambda c, i: ["rebase", c.default],
         check=lambda c, i, m, pre, b, a, rc: ([] if rc != 0 else ["git rebased cleanly; the setup meant a conflict"])
         + ([] if (files(m, "Unmerged") or svgmodel.has_text(m, "conflict")) else ["git stops on a conflict but the drawing does not show one"])
         + (same_files("unmerged", files(m, "Unmerged"), a["status"]["conflicts"]) if files(m, "Unmerged") else []))
scenario("rebase --onto", "rebase",
         setup=lambda c: (topic(c, "onto-base", 2, fileno=5), c.switch("onto-base"), topic(c, "onto-topic", 2, fileno=6, start="onto-base"), c.switch("onto-topic")),
         sim=lambda c, i: ["rebase", "--onto", c.default, "onto-base"], real=lambda c, i: ["rebase", "-q", "--onto", c.default, "onto-base"], check=rebase_check)
scenario("rebase -i (reorder, squash, drop)", "rebase", setup=lambda c: interactive_setup(c),
         sim=lambda c, i: ["rebase", "-i", c.default, "--todo", str(c.todo)], real=lambda c, i: ["rebase", "-q", "-i", c.default],
         check=rebase_check)
scenario("rebase a branch with merges", "rebase",
         setup=lambda c: (topic(c, "side", 1, fileno=7), c.branch("with-merges"), c.edit(c.file(5), 3, "sanity: w1"), c.commit("w1"),
                          g(c.repo, "merge", "-q", "--no-ff", "--no-edit", "side"), c.edit(c.file(5), 4, "sanity: w2"), c.commit("w2"),
                          c.switch(c.default), c.edit(c.file(6), 2, "sanity: main moves on"), c.commit("Main moves on"), c.switch("with-merges")),
         sim=lambda c, i: ["rebase", c.default], real=lambda c, i: ["rebase", "-q", c.default], check=rebase_check)
scenario("rebase --abort (stopped rebase)", "resume", setup=lambda c: (rebase_setup(c, conflict=True), g(c.repo, "rebase", c.default, check=False)),
         sim=lambda c, i: ["rebase", "--abort"], real=lambda c, i: ["rebase", "--abort"])
scenario("rebase --skip (stopped rebase)", "resume", setup=lambda c: (rebase_setup(c, conflict=True), g(c.repo, "rebase", c.default, check=False)),
         sim=lambda c, i: ["rebase", "--skip"], real=lambda c, i: ["rebase", "--skip"])
scenario("rebase --continue (resolved)", "resume",
         setup=lambda c: (rebase_setup(c, conflict=True), g(c.repo, "rebase", c.default, check=False), g(c.repo, "checkout", "--theirs", "--", c.file(5)), g(c.repo, "add", c.file(5))),
         sim=lambda c, i: ["rebase", "--continue"], real=lambda c, i: ["-c", "core.editor=true", "rebase", "--continue"])

# -- resets --------------------------------------------------------------------------------------------
def reset_setup(c):
    topic(c, "keep", 0)
    for k in range(3):
        c.edit(c.file(5), 20 + k, f"sanity: local commit {k}")
        c.commit(f"Local commit {k}")
    c.dirty()


scenario("reset --soft HEAD~2", "reset", setup=reset_setup, sim=lambda c, i: ["reset", "--soft", "HEAD~2"], real=lambda c, i: ["reset", "-q", "--soft", "HEAD~2"],
         pf=lambda c, i: "reset --soft HEAD~2",
         check=lambda c, i, m, pre, b, a, rc: same_files("staged after reset --soft", files(m, "Staged"), a["status"]["staged"]))
scenario("reset --mixed HEAD~2", "reset", setup=reset_setup, sim=lambda c, i: ["reset", "--mixed", "HEAD~2"], real=lambda c, i: ["reset", "-q", "--mixed", "HEAD~2"])
scenario("reset --hard HEAD~3 (dirty)", "reset", setup=reset_setup, sim=lambda c, i: ["reset", "--hard", "HEAD~3"], real=lambda c, i: ["reset", "-q", "--hard", "HEAD~3"],
         pf=lambda c, i: "reset --hard HEAD~3",
         check=lambda c, i, m, pre, b, a, rc: ([] if pre.get("risk") == "destructive" else [f"pre-flight rates reset --hard on a dirty tree {pre.get('risk')}"])
         + ([] if all(Path(f).name in json.dumps(pre.get("would_lose")) for f in [c.file(0), c.file(1)]) else ["pre-flight does not list the uncommitted work it would lose"])
         + ([] if len(orphaned(c, b)) == 3 else [f"git orphaned {len(orphaned(c, b))} commits"])
         + (["pre-flight's count of lost commits differs from git's"] if "3 commit" not in json.dumps(pre) else []))
scenario("reset --hard to another branch", "reset", setup=lambda c: topic(c, "elsewhere", 2), sim=lambda c, i: ["reset", "--hard", "elsewhere"],
         real=lambda c, i: ["reset", "-q", "--hard", "elsewhere"])

# -- remotes -----------------------------------------------------------------------------------------------
scenario("fetch (already up to date)", "remote", sim=lambda c, i: ["fetch"], real=lambda c, i: ["fetch", "-q"])
scenario("pull: fast-forward", "remote", setup=lambda c: g(c.repo, "reset", "-q", "--hard", "HEAD~2"), sim=lambda c, i: ["pull"],
         real=lambda c, i: ["pull", "-q"], check=merge_check("ff"))
scenario("pull: diverged (merge)", "remote",
         setup=lambda c: (g(c.repo, "reset", "-q", "--hard", "HEAD~2"), c.edit(c.file(6), 2, "sanity: local work"), c.commit("Local work")),
         sim=lambda c, i: ["pull"], real=lambda c, i: ["pull", "-q", "--no-rebase", "--no-edit"], check=merge_check("merge"))
scenario("pull --rebase: diverged", "remote",
         setup=lambda c: (g(c.repo, "reset", "-q", "--hard", "HEAD~2"), c.edit(c.file(6), 2, "sanity: local work"), c.commit("Local work")),
         sim=lambda c, i: ["pull", "--rebase"], real=lambda c, i: ["pull", "-q", "--rebase"], check=rebase_check)
scenario("push (sim only)", "remote", setup=lambda c: (c.edit(c.file(6), 2, "sanity: to push"), c.commit("To push")),
         sim=lambda c, i: ["push", "origin", f"HEAD:refs/heads/sanity-push"], pf=lambda c, i: "push --force origin HEAD")

# -- whole branches of the real project -----------------------------------------------------------------
REAL_MERGES = {  # (branch to be on, what to merge in)
    "hellogitworld": ("origin/master", "origin/feature_division"),
    "itsdangerous": ("origin/stable", "origin/main"),
    "flask": ("origin/stable", "origin/main"),
    "express": ("origin/4.x", "origin/5.x"),
    "git": ("origin/master", "origin/next"),
}
scenario("merge two of the project's own branches", "real-branches", only=list(REAL_MERGES),
         setup=lambda c: g(c.repo, "switch", "-q", "-c", "sanity-real", REAL_MERGES[c.name][0]),
         sim=lambda c, i: ["merge", REAL_MERGES[c.name][1]], real=lambda c, i: ["merge", "--no-edit", REAL_MERGES[c.name][1]],
         check=lambda c, i, m, pre, b, a, rc: merge_check("conflict" if rc else "merge")(c, i, m, pre, b, a, rc) if new_commits(c, b) or rc else merge_check("ff")(c, i, m, pre, b, a, rc),
         pf=lambda c, i: f"merge {REAL_MERGES[c.name][1]}")
scenario("rebase onto another of the project's branches", "real-branches", only=list(REAL_MERGES),
         setup=lambda c: (g(c.repo, "switch", "-q", "-c", "sanity-real", REAL_MERGES[c.name][0] + "~5"),
                          [c.edit(c.file(5), 30 + k, f"sanity: {k}") or c.commit(f"Local {k}") for k in range(3)]),
         sim=lambda c, i: ["rebase", REAL_MERGES[c.name][0]], real=lambda c, i: ["rebase", "-q", REAL_MERGES[c.name][0]], check=rebase_check)

# -- submodules, bisect ---------------------------------------------------------------------------------
scenario("submodule status", "special", only=["git"], sim=lambda c, i: ["submodule"])
scenario("bisect start bad good", "special",
         sim=lambda c, i: ["bisect", "start", "HEAD", "HEAD~8"] if int(out(c.repo, "rev-list", "--count", "HEAD")) > 8 else ["bisect", "start", "HEAD", "HEAD~1"])
scenario("html page renders (log --all)", "render", sim=lambda c, i: ["--all", "log"], fmt="html")


def orphaned_branch(c, before, name):
    others = [v for k, v in before["refs"].items() if not k.endswith("/" + name)] + [before["head"]]
    lst = g(c.repo, "rev-list", before["refs"].get(f"refs/heads/{name}", "HEAD"), "--stdin", stdin="--not\n" + "\n".join(others) + "\n").stdout.strip()
    return lst.split() if lst else []


def criss_cross(c):
    topic(c, "cc-a", 1, fileno=5)
    topic(c, "cc-b", 1, fileno=6)
    c.switch("cc-a")
    g(c.repo, "merge", "-q", "--no-edit", "cc-b~0")
    a_merge = sha(c.repo, "HEAD")
    c.switch("cc-b")
    g(c.repo, "merge", "-q", "--no-edit", "cc-a~1")
    c.edit(c.file(7), 3, "sanity: cc-b moves on")
    c.commit("cc-b moves on")
    c.switch("cc-a")
    c.edit(c.file(8), 3, "sanity: cc-a moves on")
    c.commit("cc-a moves on")
    bases = out(c.repo, "merge-base", "--all", "cc-a", "cc-b").split()
    return {"bases": len(bases), "a_merge": a_merge}


def interactive_setup(c):
    shas = topic(c, "ri-topic", 4, fileno=5)
    c.switch("ri-topic")
    s = [out(c.repo, "rev-parse", "--short", x) for x in shas]
    todo = f"pick {s[1]} x\npick {s[0]} x\nsquash {s[2]} x\ndrop {s[3]} x\n"
    c.todo = WORK / f"todo-{c.name}.txt"
    c.todo.write_text(todo, encoding="utf-8", newline="\n")
    # the real rebase takes the same list from its sequence editor
    ENV["GIT_SEQUENCE_EDITOR"] = f'cp "{c.todo.as_posix()}"'
    return {"todo": todo}


# ---------------------------------------------------------------------------
# running one repository (in its own process: `run` starts several)
# ---------------------------------------------------------------------------
def run_repo(name, only=()):
    ctx = Ctx(name)
    results = []
    for sc in SCENARIOS:
        if only and sc["name"] not in only:
            continue
        if sc["only"] and name not in sc["only"]:
            continue
        rec = {"repo": name, "scenario": sc["name"], "category": sc["cat"], "problems": []}
        try:
            ctx.reset()
            info = sc["setup"](ctx) if sc["setup"] else None
            before = snapshot(ctx)
            args = sc["sim"](ctx, info)
            rec["args"] = " ".join(args)
            r = gitsim(ctx.repo, args, sc["fmt"])
            rec.update({k: r[k] for k in ("rc", "secs", "refused", "traceback")})
            if r["traceback"]:
                rec["problems"].append("TRACEBACK: " + r["tail"][-600:])
            if r["rc"] == "timeout":
                rec["problems"].append(f"timed out after {TIMEOUT}s")
            elif isinstance(r["secs"], float) and r["secs"] > SLOW:
                rec["problems"].append(f"slow: {r['secs']}s")
            if sc["refuse"]:
                if not r["refused"]:
                    rec["problems"].append("expected a refusal, git-sim drew it")
            elif r["refused"]:
                rec["problems"].append("refused: " + r["refused"])
            elif not r["path"] and r["rc"] != "timeout":
                rec["problems"].append("no output file: " + r["tail"][-400:])
            model = svgmodel.parse(r["path"]) if r["path"] and sc["fmt"] == "svg" else {"commits": {}, "files": [], "texts": [], "notes": [], "refs": {}}
            rec["drawn"] = {"commits": len(model["commits"]), "after": len(after_commits(model)), "removed": len(removed_commits(model))}
            pre = {}
            if sc["pf"]:
                pre = preflight(ctx.repo, sc["pf"](ctx, info))
                rec["preflight"] = {k: pre.get(k) for k in ("risk", "summary", "would_lose", "error")}
                if pre.get("traceback"):
                    rec["problems"].append("TRACEBACK in pre-flight: " + pre.get("tail", ""))
            rc = None
            if sc["real"]:
                rc = g(ctx.repo, *sc["real"](ctx, info), check=False).returncode
                rec["real_rc"] = rc
            after = snapshot(ctx)
            if sc["check"] and (sc["refuse"] or (r["path"] and not r["refused"])):
                try:
                    rec["problems"] += sc["check"](ctx, info, model, pre, before, after, rc)
                except Exception as e:  # a check that cannot run is itself worth seeing
                    rec["problems"].append(f"check error: {type(e).__name__}: {e}")
        except Exception as e:
            rec["problems"].append(f"setup/harness error: {type(e).__name__}: {str(e)[:300]}")
        rec["ok"] = not rec["problems"]
        results.append(rec)
        print(f"{'ok ' if rec['ok'] else 'BAD'} {name:<13} {sc['name']:<45} {rec.get('secs', '')}s  {'; '.join(rec['problems'])[:200]}", flush=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    ctx.reset()


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_clone(names, update=False):
    SRC.mkdir(parents=True, exist_ok=True)
    for name in names:
        dest = SRC / name
        t0 = time.time()
        if dest.exists():
            if not update:
                print(f"{name:<14} already cloned (--update fetches)")
                continue
            subprocess.run(["git", "-C", str(dest), "fetch", "-q", "--all", "--tags", "--prune"], check=True, env=ENV)
            subprocess.run(["git", "-C", str(dest), "merge", "-q", "--ff-only"], check=False, env=ENV)
            what = "updated"
        else:
            subprocess.run(["git", "clone", "-q", "--no-single-branch", REPOS[name], str(dest)], check=True, env=ENV)
            what = "cloned"
        count = out(dest, "rev-list", "--all", "--count")
        print(f"{name:<14} {what}: {count} commits ({time.time() - t0:.0f}s)")


def cmd_run(names, jobs, scenarios):
    missing = [n for n in names if not (SRC / n).exists()]
    if missing:
        sys.exit(f"not cloned yet: {', '.join(missing)} (python tests/sanity/sanity.py clone)")
    LOGS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    for n in names:
        stale = RESULTS / f"{n}.json"
        if stale.exists():
            stale.unlink()
    pending, running, t0 = list(names), {}, time.time()
    while pending or running:
        while pending and len(running) < jobs:
            n = pending.pop(0)
            log = open(LOGS / f"{n}.log", "w", encoding="utf-8")
            args = [PY, str(Path(__file__).resolve()), "--dir", str(WORKDIR), "_one", n]
            for s in scenarios:
                args += ["--scenario", s]
            running[n] = (subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env=ENV), log)
            print(f"started  {n}", flush=True)
        for n, (proc, log) in list(running.items()):
            if proc.poll() is not None:
                log.close()
                del running[n]
                status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}, see logs/{n}.log"
                print(f"finished {n} ({status})", flush=True)
        time.sleep(1)
    print(f"all done in {(time.time() - t0) / 60:.1f} min\n")
    cmd_report()


def cmd_report():
    rows = []
    for f in sorted(RESULTS.glob("*.json")):
        rows += json.loads(f.read_text(encoding="utf-8"))
    if not rows:
        sys.exit("no results yet (python tests/sanity/sanity.py run)")
    by_repo = {}
    for r in rows:
        by_repo.setdefault(r["repo"], []).append(r)
    bad = [r for r in rows if not r["ok"]]
    lines = ["# git-sim sanity run", "", f"{len(rows) - len(bad)} of {len(rows)} scenario runs match git; {len(bad)} to look at.",
             "", "| repository | scenarios | problems |", "| --- | ---: | ---: |"]
    for repo in REPOS:
        if repo in by_repo:
            rs = by_repo[repo]
            lines.append(f"| {repo} | {len(rs)} | {sum(not r['ok'] for r in rs)} |")
    if bad:
        lines += ["", "## Problems", ""]
        for r in bad:
            detail = "; ".join(p.replace("\n", " ")[:300] for p in r["problems"])
            lines.append(f"- **{r['repo']}** {r['scenario']} (`git-sim {r.get('args', '')}`): {detail}")
    timed = sorted((r for r in rows if isinstance(r.get("secs"), (int, float))), key=lambda r: -r["secs"])[:8]
    lines += ["", "## Slowest", ""] + [f"- {r['secs']:.1f}s  {r['repo']}: {r['scenario']}" for r in timed]
    report = "\n".join(lines) + "\n"
    (WORKDIR / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"(also in {WORKDIR / 'report.md'}; per-scenario detail in {RESULTS})")


def cmd_list():
    print("repositories: " + ", ".join(REPOS))
    print(f"\n{len(SCENARIOS)} scenarios:")
    for sc in SCENARIOS:
        only = f"  (only {', '.join(sc['only'])})" if sc["only"] else ""
        print(f"  {sc['cat']:<14} {sc['name']}{only}")


def main():
    ap = argparse.ArgumentParser(description="Sanity-test git-sim on real open-source repositories.")
    ap.add_argument("--dir", default=os.environ.get("GIT_SIM_SANITY_DIR", str(HERE / ".work")),
                    help="working folder for clones, results and logs (default: tests/sanity/.work)")
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("clone", help="clone the repositories (once; --update fetches)")
    c.add_argument("repos", nargs="*", help="default: all")
    c.add_argument("--update", action="store_true")
    r = sub.add_parser("run", help="run the scenarios, several repositories at a time, then report")
    r.add_argument("repos", nargs="*", help="default: all")
    r.add_argument("-j", "--jobs", type=int, default=3, help="repositories run in parallel (default 3)")
    r.add_argument("--scenario", action="append", default=[], help="only this scenario (repeatable)")
    sub.add_parser("report", help="summarize the last run")
    sub.add_parser("list", help="list the repositories and scenarios")
    one = sub.add_parser("_one", help=argparse.SUPPRESS)
    one.add_argument("repo")
    one.add_argument("--scenario", action="append", default=[])
    a = ap.parse_args()
    configure(a.dir)
    names = getattr(a, "repos", None) or ([a.repo] if a.command == "_one" else list(REPOS))
    unknown = [n for n in names if n not in REPOS]
    if unknown:
        sys.exit(f"unknown repositories: {', '.join(unknown)} (known: {', '.join(REPOS)})")
    if a.command == "clone":
        cmd_clone(names, a.update)
    elif a.command == "run":
        cmd_run(names, max(1, a.jobs), a.scenario)
    elif a.command == "report":
        cmd_report()
    elif a.command == "list":
        cmd_list()
    elif a.command == "_one":
        run_repo(a.repo, a.scenario)


if __name__ == "__main__":
    main()
