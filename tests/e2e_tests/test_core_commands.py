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

complex_commands = [
    "git-sim branch new_branch",
    "git-sim checkout branch2",
    "git-sim cherry-pick branch2",
    "git-sim merge branch2",
    "git-sim mv main.1 main.100",
    "git-sim rebase branch2",
    "git-sim reset HEAD^",
    "git-sim revert HEAD^",
    "git-sim rm main.1",
    "git-sim switch branch2",
    "git-sim tag new_tag",
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


@pytest.mark.parametrize("raw_cmd", complex_commands)
def test_complex_command(tmp_repo, raw_cmd):
    """Test a complex git-sim command.

    This function works for any command of the form
      `git-sim <command> <arg>
    """
    cmd_parts = get_cmd_parts(raw_cmd)

    raw_cmd_parts = raw_cmd.split(" ")
    # This converts commands like `git-sim cherry-pick` to git-sim-cherry_pick.
    core_command = f"{raw_cmd_parts[0]} {raw_cmd_parts[1].replace('-', '_')}"
    filename_element = core_command.replace(" ", "-")

    os.chdir(tmp_repo)
    output = subprocess.run(cmd_parts, capture_output=True)

    fp_generated = Path(output.stdout.decode().strip())
    fp_reference = Path(__file__).parent / f"reference_files/{filename_element}.png"

    assert filename_element in str(fp_generated)
    compare_images(fp_generated, fp_reference)
