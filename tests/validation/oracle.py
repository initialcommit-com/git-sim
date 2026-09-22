"""Ground truth from git itself, so the tests compare what git-sim drew with
what git would do, instead of with numbers typed into the test."""

from __future__ import annotations

import subprocess
from typing import Dict, List


def git(repo, *args, check=True, keep_space=False) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    # porcelain records start with a space for an unstaged change, so they
    # must not be stripped
    return proc.stdout.rstrip("\n") if keep_space else proc.stdout.strip()


def rev_parse(repo, ref) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")


def parents(repo, ref) -> List[str]:
    return git(repo, "rev-parse", f"{ref}^@").split()


def is_ancestor(repo, a, b) -> bool:
    proc = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", a, b], capture_output=True)
    return proc.returncode == 0


def count(repo, spec) -> int:
    return int(git(repo, "rev-list", "--count", *spec.split()))


def head_branch(repo):
    out = git(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False)
    return out or None


def only_reachable_from(repo, ref) -> List[str]:
    """Commits reachable from ref and from no other ref: what deleting or
    moving ref would orphan."""
    others = [
        r for r in git(repo, "for-each-ref", "--format=%(refname)").split()
        if r not in (ref, f"refs/heads/{ref}", f"refs/tags/{ref}", f"refs/remotes/{ref}")
    ]
    args = ["rev-list", ref, "--not", *others]
    out = git(repo, *args)
    return out.split() if out else []


def status(repo) -> Dict[str, List[str]]:
    """Files by zone, from `git status --porcelain`."""
    res = {"staged": [], "modified": [], "untracked": [], "conflicts": []}
    for rec in git(repo, "status", "--porcelain", "-z", check=False, keep_space=True).split("\0"):
        if len(rec) < 4:
            continue
        x, y, path = rec[0], rec[1], rec[3:]
        if "U" in (x, y) or (x == y and x in "AD"):
            res["conflicts"].append(path)
        elif rec[:2] == "??":
            res["untracked"].append(path)
        else:
            if x != " ":
                res["staged"].append(path)
            if y != " ":
                res["modified"].append(path)
    return res


def stash_count(repo) -> int:
    out = git(repo, "stash", "list", check=False)
    return len(out.splitlines()) if out else 0


def reflog_count(repo) -> int:
    out = git(repo, "reflog", "show", "--format=%H", "HEAD", check=False)
    return len(out.splitlines()) if out else 0


def branches(repo) -> List[str]:
    return git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()


def tags(repo) -> List[str]:
    return git(repo, "tag").split()


def remotes(repo) -> List[str]:
    out = git(repo, "remote", check=False)
    return out.split() if out else []


def tracked(repo) -> List[str]:
    return git(repo, "ls-files").split("\n") if git(repo, "ls-files") else []
