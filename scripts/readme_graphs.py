"""Render the README's graphs (docs/img) and, optionally, the site's demo copies.

    python scripts/readme_graphs.py [--docs <dir>] [--site <initialcommit repo>] [slug ...]

Builds two sample repositories with git-dummy 0.2.0 or later: "orders"
(branches, a tag, a remote we are ahead of, a dirty working tree, a stash,
some reflog) for most commands, and "orders-behind" (a remote that moved on)
for fetch and pull. Each command is rendered as an SVG twice: light for the
README, made to play by itself on a loop (scripts/animate_svg.py), and with
--site, dark for the tool page's ?demo= links. Without slugs, every command
is rendered.

Every render reads a sample global config, never this machine's own: the
config graph shows where a value comes from, and init the default branch.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from animate_svg import process as animate  # noqa: E402

try:
    from git_dummy import build
except ImportError:
    raise SystemExit("needs git-dummy 0.2.0 or later (its build() API): pip install -U git-dummy")

# slug -> (git-sim arguments, which repository)
COMMANDS = {
    "merge": (["merge", "feature/pagination"], "orders"),
    "rebase": (["rebase", "feature/pagination"], "orders"),
    "reset-hard": (["reset", "--hard", "HEAD~2"], "orders"),
    "cherry-pick": (["cherry-pick", "fix/order-totals"], "orders"),
    "stash": (["stash"], "orders"),
    "revert": (["revert", "HEAD"], "orders"),
    "switch-c": (["switch", "-c", "feature/search"], "orders"),
    "branch-d": (["branch", "-D", "fix/order-totals"], "orders"),
    "restore-staged": (["restore", "--staged", "app.py"], "orders"),
    "tag": (["tag", "v1.1.0"], "orders"),
    "commit-amend": (["commit", "--amend", "--no-edit"], "orders"),
    "clean": (["clean", "-fd"], "orders"),
    "checkout": (["checkout", "fix/order-totals"], "orders"),
    "push": (["push", "origin", "main"], "orders"),
    "add": (["add", "scratch.txt", "README.md"], "orders"),
    "branch": (["branch", "feature/search"], "orders"),
    "clone": (["clone", "https://github.com/initialcommit-com/git-dummy.git"], "work"),
    "commit": (["commit", "-m", "Ship the pagination fix"], "orders"),
    "config": (["config", "user.name", "Ada Lovelace"], "orders"),
    "fetch": (["fetch", "origin", "main"], "orders-behind"),
    "init": (["init"], "my-project"),
    "log": (["log", "--all"], "orders"),
    "mv": (["mv", "config.yaml", "settings.yaml"], "orders"),
    "pull": (["pull", "origin", "main"], "orders-behind"),
    "reflog": (["reflog"], "orders"),
    "remote": (["remote"], "orders"),
    "restore": (["restore", "README.md"], "orders"),
    "rm": (["rm", "utils.py"], "orders"),
    "stash-pop": (["stash", "pop"], "orders"),
    "status": (["status"], "orders"),
    "worktree": (["worktree", "add", "../hotfix", "fix/order-totals"], "orders"),
}

SAMPLE_GLOBAL = "[user]\n\tname = Grace Hopper\n\temail = grace@example.com\n[init]\n\tdefaultBranch = main\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--docs", default=os.path.join(os.path.dirname(HERE), "docs", "img"))
    parser.add_argument("--site", help="the initialcommit repository, for the dark ?demo= copies")
    parser.add_argument("slugs", nargs="*", help="commands to render (default: all)")
    opts = parser.parse_args()
    slugs = opts.slugs or list(COMMANDS)
    unknown = [s for s in slugs if s not in COMMANDS]
    if unknown:
        raise SystemExit(f"unknown: {', '.join(unknown)} (known: {', '.join(COMMANDS)})")

    for k in [k for k in os.environ if k.lower().startswith("git_sim_")]:
        del os.environ[k]
    os.environ["git_sim_auto_open"] = "false"
    work = tempfile.mkdtemp(prefix="gs-readme-")

    # On Windows the remotes are addressed through a substituted drive letter,
    # so nothing a render quotes (pull's merge message) carries a temp path.
    drive = None
    if os.name == "nt":
        drive = next(d for d in "RSTUVW" if not os.path.exists(f"{d}:\\"))
        subprocess.run(["subst", f"{drive}:", work], check=True, capture_output=True)
    try:
        common = dict(git_dir=work, style="realistic", seed=42, commits=6, constant_sha=False)
        a = build(name="orders", branches=3, diverge_at=4, branch_names=["feature/pagination", "fix/order-totals"],
                  tags=["v1.0.0"], remote=True, ahead=1, modified=1, staged=1, untracked=1, stashes=1, reflog=2, **common)
        b = build(name="orders-behind", remote=True, behind=2, **common)
        repos = {"orders": a["path"], "orders-behind": b["path"], "work": work}

        def origin(name):
            return f"{drive}:\\{name}.origin.git" if drive else os.path.join(work, f"{name}.origin.git")

        for name in ("orders", "orders-behind"):
            subprocess.run(["git", "-C", repos[name], "remote", "set-url", "origin", origin(name)], check=True)

        # git init's folder: a project with a few files, which move up to make room for .git/
        project = os.path.join(work, "my-project")
        os.makedirs(os.path.join(project, "docs"))
        for name, text in (("app.py", "print('orders')\n"), ("README.md", "# Orders\n"),
                           ("requirements.txt", "flask\n"), (os.path.join("docs", "index.md"), "# Docs\n")):
            with open(os.path.join(project, name), "w") as f:
                f.write(text)
        repos["my-project"] = project

        sample = os.path.join(work, "sample-gitconfig")
        with open(sample, "w") as f:
            f.write(SAMPLE_GLOBAL)
        os.environ["GIT_CONFIG_GLOBAL"] = sample
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

        def render(args, cwd, dark):
            r = subprocess.run([sys.executable, "-m", "git_sim", "-d", *(["--dark-mode"] if dark else []),
                                "--media-dir", work, "--img-format", "svg", "--output-only-path", *args],
                               cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
            path = lines[-1] if lines else ""
            if r.returncode != 0 or not path.endswith(".svg") or not os.path.exists(path):
                raise SystemExit(f"FAIL {' '.join(args)}: {(r.stdout + r.stderr).strip()[-300:]}")
            return path

        site_dirs = []
        if opts.site:
            site_dirs = [os.path.join(opts.site, *p, "static", "js", "tools")
                         for p in (("src", "main", "resources"), ("target", "classes"))]
            site_dirs = [d for d in site_dirs if os.path.isdir(d)]
        os.makedirs(opts.docs, exist_ok=True)
        for slug in slugs:
            args, where = COMMANDS[slug]
            cwd = repos[where]
            if slug == "remote":  # a remote with an address a reader would recognize
                subprocess.run(["git", "-C", cwd, "remote", "set-url", "origin", "https://github.com/example/orders.git"], check=True)
            light = render(args, cwd, dark=False)
            readme = os.path.join(opts.docs, f"{slug}.svg")
            shutil.copy(light, readme)
            note = animate(readme)
            dark = render(args, cwd, dark=True) if site_dirs else None
            for d in site_dirs:
                shutil.copy(dark, os.path.join(d, f"git-sim-demo-{slug}.svg"))
                if slug == "rebase":  # the tool page's default graph
                    shutil.copy(dark, os.path.join(d, "git-sim-demo.svg"))
            if slug == "remote":
                subprocess.run(["git", "-C", cwd, "remote", "set-url", "origin", origin("orders")], check=True)
            print(f"ok  {slug:<15} {' '.join(args)}  ({note})")
    finally:
        if drive:
            subprocess.run(["subst", f"{drive}:", "/d"], capture_output=True)


if __name__ == "__main__":
    main()
