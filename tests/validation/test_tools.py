"""The commands that are not simulations: pre-flight, live in its one-shot
mode, aliases, and the installer's dry run."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

import oracle as o


def run_cli(gitsim, cwd, *args, timeout=120):
    proc = subprocess.run([sys.executable, "-m", "git_sim", *args], cwd=str(cwd), capture_output=True, env=gitsim.env(), timeout=timeout)
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    assert "Traceback" not in err, err[-2000:]
    return proc.returncode, out, err


# ---- preflight ---------------------------------------------------------------------------------


def test_preflight_reports_a_destructive_reset(shapes, gitsim):
    repo = shapes.get("classic").path
    code, out, err = run_cli(gitsim, repo, "preflight", "reset", "--hard", "HEAD~2")
    assert code == 0, err
    text = (out + err).lower()
    assert "risk" in text
    for sha in o.git(repo, "rev-list", "HEAD~2..HEAD").split():
        assert sha[:7] in out, f"the commits that would become unreachable are named ({sha[:7]})"


def test_preflight_json_has_the_facts(shapes, gitsim):
    repo = shapes.get("classic").path
    code, out, _ = run_cli(gitsim, repo, "preflight", "--json", "branch", "-D", "branch2")
    assert code == 0
    data = json.loads(out)
    assert data.get("risk") or data.get("level") or "risk" in json.dumps(data).lower()
    dumped = json.dumps(data)
    for sha in o.only_reachable_from(repo, "branch2"):
        assert sha[:7] in dumped, "the orphaned commits are listed"


def test_preflight_markdown(shapes, gitsim):
    code, out, _ = run_cli(gitsim, shapes.get("diverged").path, "preflight", "--markdown", "push", "--force", "origin", "main")
    assert code == 0
    assert "#" in out or "|" in out or "**" in out, "markdown markup present"
    assert "force" in out.lower()


def test_preflight_safe_command(shapes, gitsim):
    code, out, err = run_cli(gitsim, shapes.get("classic").path, "preflight", "status")
    assert code == 0
    text = (out + err).lower()
    assert "safe" in text and "only reads" in text


def test_preflight_repo_option(shapes, gitsim, tmp_path):
    repo = shapes.get("classic").path
    code, out, _ = run_cli(gitsim, tmp_path, "preflight", "-C", str(repo), "--json", "reset", "--hard", "HEAD~1")
    assert code == 0
    assert json.loads(out)


def test_preflight_dirty_worktree_notes_losses(shapes, gitsim):
    repo = shapes.get("messy").path
    code, out, _ = run_cli(gitsim, repo, "preflight", "--json", "reset", "--hard")
    assert code == 0
    dumped = json.loads(out)
    text = json.dumps(dumped)
    assert "README.md" in text or "models.py" in text, "uncommitted work at risk is named"


# ---- live ----------------------------------------------------------------------------------------


def test_live_once_json(shapes, gitsim):
    repo = shapes.get("history").path
    code, out, err = run_cli(gitsim, repo, "live", "--json", "--once", "-C", str(repo), timeout=180)
    assert code == 0, err
    lines = [l for l in out.splitlines() if l.strip().startswith("{")]
    assert lines, f"expected JSON lines, got:\n{out[-800:]}"
    for line in lines:
        json.loads(line)


def test_live_sessions_lists(shapes, gitsim):
    repo = shapes.get("history").path
    code, out, err = run_cli(gitsim, repo, "live", "--sessions", "--json", "-C", str(repo))
    assert code == 0, err


def test_live_print_page(shapes, gitsim):
    repo = shapes.get("history").path
    code, out, err = run_cli(gitsim, repo, "live", "--print-page", "-C", str(repo))
    assert code == 0, err
    assert "<html" in out.lower()


# ---- aliases and install ----------------------------------------------------------------------


def test_aliases_local(shapes, gitsim):
    repo = shapes.get("classic").path
    code, out, err = run_cli(gitsim, repo, "aliases", "--local")
    assert code == 0, err
    assert o.git(repo, "config", "--get", "alias.preflight", check=False)
    code, out, err = run_cli(gitsim, repo, "aliases", "--local", "--remove")
    assert code == 0, err
    assert not o.git(repo, "config", "--get", "alias.preflight", check=False)


def test_install_dry_run_touches_nothing(shapes, gitsim, tmp_path):
    code, out, err = run_cli(gitsim, tmp_path, "install", "--dry-run", "--all")
    assert code == 0, err
    assert out.strip(), "the dry run reports what it would do"
    assert not list(tmp_path.iterdir()), "nothing written"


def test_uninstall_dry_run(shapes, gitsim, tmp_path):
    code, out, err = run_cli(gitsim, tmp_path, "uninstall", "--dry-run", "--all")
    assert code == 0, err
