import subprocess, os
from pathlib import Path
from shlex import split

import pytest

import utils


@pytest.fixture(scope="session")
def tmp_repo(tmp_path_factory):
    """Create a copy of the sample repo, which we can run all tests against.

    Returns: path to tmp dir containing sample test repository.
    """

    tmp_repo_dir = tmp_path_factory.mktemp("sample_repo")

    # To see where tmp_repo_dir is located, run pytest with the `-s` flag.
    print(f"\n\nTemp repo directory:\n  {tmp_repo_dir}\n")

    # Create the sample repo for testing.
    os.chdir(tmp_repo_dir)

    # When defining cmd, as_posix() is required for Windows compatibility.
    git_dummy_path = utils.get_venv_path() / "git-dummy"
    cmd = f"{git_dummy_path.as_posix()} --commits=10 --branches=4 --merge=1 --constant-sha --name=sample_repo --diverge-at=2"
    cmd_parts = split(cmd)
    subprocess.run(cmd_parts)

    return tmp_repo_dir / "sample_repo"
