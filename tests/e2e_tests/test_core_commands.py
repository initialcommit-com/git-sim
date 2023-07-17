"""Tests for the core commands implemented in git-sim.

All test runs use the -d flag to prevent images from opening automatically.

To induce failure, include a call to `run_git_reset()` in one of the
  test functions.
"""

import os, subprocess
from pathlib import Path

from utils import get_cmd_parts, compare_images, run_git_reset

import pytest


simple_commands = [
    "git-sim add",
    "git-sim log",
    "git-sim clean",
    "git-sim commit",
    "git-sim restore",
    "git-sim stash",
    "git-sim status",
]

@pytest.mark.parametrize("raw_cmd", simple_commands)
def test_simple_command(tmp_repo, raw_cmd):
    """Test a simple git-sim command.

    This function works for any command of the form
      `git-sim <command>`
    """
    cmd_parts = get_cmd_parts(raw_cmd)
    filename_element = raw_cmd.replace(" ", "-")

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / f"reference_files/{filename_element}.png"

    assert filename_element in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_add(tmp_repo):
    """Test a simple `git-sim add` command."""
    raw_cmd = "git-sim add"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-add.png"

    assert "git-sim-add" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_branch(tmp_repo):
    """Test a simple `git-sim branch` command."""
    raw_cmd = "git-sim branch new_branch"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-branch.png"

    assert "git-sim-branch" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_checkout(tmp_repo):
    """Test a simple `git-sim checkout` command."""
    raw_cmd = "git-sim checkout branch2"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-checkout.png"

    assert "git-sim-checkout" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_cherrypick(tmp_repo):
    """Test a simple `git-sim cherry-pick` command."""
    raw_cmd = "git-sim cherry-pick branch2"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-cherry_pick.png"

    assert "git-sim-cherry_pick" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_clean(tmp_repo):
    """Test a simple `git-sim clean` command."""
    raw_cmd = "git-sim clean"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-clean.png"

    assert "git-sim-clean" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_commit(tmp_repo):
    """Test a simple `git-sim commit` command."""
    raw_cmd = "git-sim commit"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-commit.png"

    assert "git-sim-commit" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_log(tmp_repo):
    """Test a simple `git-sim log` command."""
    raw_cmd = "git-sim log"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-log.png"

    assert "git-sim-log" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_merge(tmp_repo):
    """Test a simple `git-sim merge` command."""
    raw_cmd = "git-sim merge branch2"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-merge.png"

    assert "git-sim-merge" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_mv(tmp_repo):
    """Test a simple `git-sim mv` command."""
    raw_cmd = "git-sim mv main.1 main.100"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-mv.png"

    assert "git-sim-mv" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_rebase(tmp_repo):
    """Test a simple `git-sim rebase` command."""
    raw_cmd = "git-sim rebase branch2"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-rebase.png"

    assert "git-sim-rebase" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_reset(tmp_repo):
    """Test a simple `git-sim reset` command."""
    raw_cmd = "git-sim reset HEAD^"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-reset.png"

    assert "git-sim-reset" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_restore(tmp_repo):
    """Test a simple `git-sim restore` command."""
    raw_cmd = "git-sim restore"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-restore.png"

    assert "git-sim-restore" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_revert(tmp_repo):
    """Test a simple `git-sim revert` command."""
    raw_cmd = "git-sim revert HEAD^"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-revert.png"

    assert "git-sim-revert" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_rm(tmp_repo):
    """Test a simple `git-sim rm` command."""
    raw_cmd = "git-sim rm main.1"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-rm.png"

    assert "git-sim-rm" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_stash(tmp_repo):
    """Test a simple `git-sim stash` command."""
    raw_cmd = "git-sim stash"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-stash.png"

    assert "git-sim-stash" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_status(tmp_repo):
    """Test a simple `git-sim status` command."""
    raw_cmd = "git-sim status"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-status.png"

    assert "git-sim-status" in str(fp_generated)
    compare_images(fp_generated, fp_reference)

def test_switch(tmp_repo):
    """Test a simple `git-sim switch` command."""
    raw_cmd = "git-sim switch branch2"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-switch.png"

    assert "git-sim-switch" in str(fp_generated)
    compare_images(fp_generated, fp_reference)


def test_tag(tmp_repo):
    """Test a simple `git-sim tag` command."""
    raw_cmd = "git-sim tag new_tag"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-tag.png"

    assert "git-sim-tag" in str(fp_generated)
    compare_images(fp_generated, fp_reference)
