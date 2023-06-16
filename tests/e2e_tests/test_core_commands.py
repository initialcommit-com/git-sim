"""Tests for the core commands implemented in git-sim.

All test runs use the -d flag to prevent images from opening automatically.

To induce failure, include a call to `run_git_reset()` in one of the
  test functions.
"""

import os, subprocess
from pathlib import Path

from utils import get_cmd_parts, compare_images, run_git_reset


def test_log(tmp_repo):
    """Test a simple `git-sim log` command."""
    raw_cmd = "git-sim log"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-log.png"

    assert compare_images(fp_generated, fp_reference)


def test_status(tmp_repo):
    """Test a simple `git-sim status` command."""
    raw_cmd = "git-sim status"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-status.png"

    assert compare_images(fp_generated, fp_reference)


def test_merge(tmp_repo):
    """Test a simple `git-sim merge` command."""
    raw_cmd = "git-sim merge branch2"
    cmd_parts = get_cmd_parts(raw_cmd)

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / "reference_files/git-sim-merge.png"

    assert compare_images(fp_generated, fp_reference)
