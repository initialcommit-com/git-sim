import subprocess, sys, os, shutil
from pathlib import Path
from shlex import split

import pytest


@pytest.fixture(scope="session")
def tmp_repo(tmp_path_factory):
    """Create a copy of the sample repo, which we can run all tests against.

    Returns: path to tmp dir containing sample test repository.
    """

    tmp_repo_dir = tmp_path_factory.mktemp("sample_repo")

    # To see where tmp_repo_dir is located, run pytest with the `-s` flag.
    print(f"\n\nTemp repo directory:\n  {tmp_repo_dir}\n")

    # Copy the sample repo to the tmp dir.
    sample_repo_dir = Path(__file__).parent / "sample_repo"
    shutil.copytree(sample_repo_dir, tmp_repo_dir, dirs_exist_ok=True)

    # Rename the .git_not_a_submodule dir to .git.
    #   If the sample repo has a .git/ dir, it makes the overall project
    #   think the sample repo is a submodule. Headaches ensue.
    os.rename(f"{tmp_repo_dir}/.git_not_a_submodule", f"{tmp_repo_dir}/.git")

    return tmp_repo_dir
