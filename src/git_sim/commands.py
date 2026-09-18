from __future__ import annotations

import inspect

import typer

from typing import List

from git_sim.settings import settings
from git_sim.enums import (
    ResetMode,
    StashSubCommand,
    RemoteSubCommand,
    SubmoduleSubCommand,
    WorktreeSubCommand,
)


def handle_animations(scene) -> None:
    from git_sim.animations import handle_animations as _handle_animations

    # The calling typer command's name (e.g. "cherry_pick") names the output file.
    command_name = inspect.stack()[1].function
    with settings.font_context:
        return _handle_animations(scene, command_name)


def add(
    files: List[str] = typer.Argument(
        default=None,
        help="The names of one or more files to add to Git's staging area",
    )
):
    from git_sim.add import Add

    scene = Add(files=files)
    handle_animations(scene=scene)


def branch(
    name: str = typer.Argument(
        ...,
        help="The branch to create, delete (-d/-D) or rename (-m)",
    ),
    new_name: str = typer.Argument(
        default=None,
        help="With -m: the new name for the branch",
    ),
    d: bool = typer.Option(
        False, "-d", "--delete", help="Delete the branch (refused if unmerged)"
    ),
    D: bool = typer.Option(
        False, "-D", help="Force-delete the branch even if unmerged"
    ),
    m: bool = typer.Option(False, "-m", "--move", help="Rename the branch to NEW_NAME"),
):
    from git_sim.branch import Branch

    scene = Branch(name=name, new_name=new_name, delete=d, force_delete=D, move=m)
    handle_animations(scene=scene)


def checkout(
    branch: str = typer.Argument(
        ...,
        help="The name of the branch to checkout",
    ),
    b: bool = typer.Option(
        False,
        "-b",
        help="Create the specified branch if it doesn't already exist",
    ),
):
    from git_sim.checkout import Checkout

    scene = Checkout(branch=branch, b=b)
    handle_animations(scene=scene)


def cherry_pick(
    commit: str = typer.Argument(
        ...,
        help="The ref (branch/tag), commit ID, or range A..B to simulate cherry-picking onto the active branch",
    ),
    edit: str = typer.Option(
        None,
        "--edit",
        "-e",
        help="Specify a new commit message for the cherry-picked commit",
    ),
    no_commit: bool = typer.Option(
        False,
        "--no-commit",
        "-n",
        help="Apply the changes to the index and working tree without committing",
    ),
):
    from git_sim.cherrypick import CherryPick

    scene = CherryPick(commit=commit, edit=edit, no_commit=no_commit)
    handle_animations(scene=scene)


def clean(
    force: bool = typer.Option(
        False, "-f", "--force", help="Actually delete (git refuses without -f or -n)"
    ),
    dry_run: bool = typer.Option(
        False, "-n", "--dry-run", help="Show what would be deleted"
    ),
    d: bool = typer.Option(False, "-d", help="Also remove untracked directories"),
    x: bool = typer.Option(False, "-x", help="Also remove ignored files"),
):
    from git_sim.clean import Clean

    scene = Clean(force=force, dry_run=dry_run, directories=d, ignored=x)
    handle_animations(scene=scene)


def clone(
    url: str = typer.Argument(
        ...,
        help="The web URL or filesystem path of the Git repo to clone",
    ),
    path: str = typer.Argument(
        default=".",
        help="The web URL or filesystem path of the Git repo to clone",
    ),
):
    from git_sim.clone import Clone

    scene = Clone(url=url, path=path)
    handle_animations(scene=scene)


def commit(
    message: str = typer.Option(
        "New commit",
        "--message",
        "-m",
        help="The commit message of the new commit",
    ),
    amend: bool = typer.Option(
        default=False,
        help="Replace the last commit (with --message, or --no-edit to keep its message)",
    ),
    no_edit: bool = typer.Option(
        False,
        "--no-edit",
        help="With --amend: keep the existing commit message",
    ),
    all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Automatically stage modified and deleted tracked files before committing",
    ),
):
    from git_sim.commit import Commit

    scene = Commit(message=message, amend=amend, no_edit=no_edit, all=all)
    handle_animations(scene=scene)


def config(
    l: bool = typer.Option(
        False,
        "-l",
        "--list",
        help="List existing local repo config settings",
    ),
    settings: List[str] = typer.Argument(
        default=None,
        help="The names and values of one or more config settings to set",
    ),
):
    from git_sim.config import Config

    scene = Config(l=l, settings=settings)
    handle_animations(scene=scene)


def fetch(
    remote: str = typer.Argument(
        default=None,
        help="The name of the remote to fetch from",
    ),
    branch: str = typer.Argument(
        default=None,
        help="The name of the branch to fetch",
    ),
):
    from git_sim.fetch import Fetch

    scene = Fetch(remote=remote, branch=branch)
    handle_animations(scene=scene)


def init():
    from git_sim.init import Init

    scene = Init()
    handle_animations(scene=scene)


def log(
    ctx: typer.Context,
    n: int = typer.Option(
        None,
        "-n",
        help="Number of commits to display from branch heads",
    ),
    all: bool = typer.Option(
        False,
        "--all",
        help="Display all local branches in the log output",
    ),
):
    from git_sim.log import Log

    scene = Log(ctx=ctx, n=n, all=all)
    handle_animations(scene=scene)


def merge(
    branch: str = typer.Argument(
        ...,
        help="The name of the branch to merge into the active checked-out branch",
    ),
    no_ff: bool = typer.Option(
        False,
        "--no-ff",
        help="Simulate creation of a merge commit in all cases, even when the merge could instead be resolved as a fast-forward",
    ),
    message: str = typer.Option(
        "Merge commit",
        "--message",
        "-m",
        help="The commit message of the new merge commit",
    ),
):
    from git_sim.merge import Merge

    scene = Merge(branch=branch, no_ff=no_ff, message=message)
    handle_animations(scene=scene)


def mv(
    file: str = typer.Argument(
        default=None,
        help="The name of the file to change the name/path of",
    ),
    new_file: str = typer.Argument(
        default=None,
        help="The new name/path of the file",
    ),
):
    from git_sim.mv import Mv

    scene = Mv(file=file, new_file=new_file)
    handle_animations(scene=scene)


def pull(
    remote: str = typer.Argument(
        default=None,
        help="The name of the remote to pull from",
    ),
    branch: str = typer.Argument(
        default=None,
        help="The name of the branch to pull",
    ),
):
    from git_sim.pull import Pull

    scene = Pull(remote=remote, branch=branch)
    handle_animations(scene=scene)


def push(
    remote: str = typer.Argument(
        default=None,
        help="The name of the remote to push to",
    ),
    branch: str = typer.Argument(
        default=None,
        help="The name of the branch to push",
    ),
    set_upstream: bool = typer.Option(
        False,
        "--set-upstream",
        help="Map the local branch to the specified upstream branch",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite the remote branch even if it has commits you don't have",
    ),
    force_with_lease: bool = typer.Option(
        False,
        "--force-with-lease",
        help="Overwrite the remote branch only if it still matches your last fetch",
    ),
):
    from git_sim.push import Push

    scene = Push(
        remote=remote,
        branch=branch,
        set_upstream=set_upstream,
        force=force,
        force_with_lease=force_with_lease,
    )
    handle_animations(scene=scene)


def rebase(
    branch: str = typer.Argument(
        ...,
        help="The upstream to rebase the checked-out branch onto",
    ),
    onto: str = typer.Option(
        None,
        "--onto",
        help="Replay the commits onto this base instead of the upstream itself",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactive rebase: takes the todo list from --todo (default: pick everything)",
    ),
    todo: str = typer.Option(
        None,
        "--todo",
        help="With -i: path to a git rebase todo file (pick/reword/squash/fixup/drop <sha>)",
    ),
):
    from git_sim.rebase import Rebase

    scene = Rebase(branch=branch, onto=onto, interactive=interactive, todo=todo)
    handle_animations(scene=scene)


def remote(
    command: RemoteSubCommand = typer.Argument(
        default=None,
        help="Remote subcommand (add, rename, remove, get-url, set-url)",
    ),
    remote: str = typer.Argument(
        default=None,
        help="The name of the remote",
    ),
    url_or_path: str = typer.Argument(
        default=None,
        help="The url or path to the remote",
    ),
):
    from git_sim.remote import Remote

    scene = Remote(command=command, remote=remote, url_or_path=url_or_path)
    handle_animations(scene=scene)


def reset(
    commit: str = typer.Argument(
        default="HEAD",
        help="The ref (branch/tag), or commit ID to simulate reset to (or a path to unstage)",
    ),
    paths: List[str] = typer.Argument(
        default=None,
        help="Paths to unstage (git reset [<commit>] -- <paths>)",
    ),
    mode: ResetMode = typer.Option(
        default="mixed",
        help="Either mixed, soft, or hard",
    ),
    soft: bool = typer.Option(
        default=False,
        help="Simulate a soft reset, shortcut for --mode=soft",
    ),
    mixed: bool = typer.Option(
        default=False,
        help="Simulate a mixed reset, shortcut for --mode=mixed",
    ),
    hard: bool = typer.Option(
        default=False,
        help="Simulate a soft reset, shortcut for --mode=hard",
    ),
):
    from git_sim.reset import Reset

    scene = Reset(
        commit=commit, mode=mode, soft=soft, mixed=mixed, hard=hard, paths=paths
    )
    handle_animations(scene=scene)


def restore(
    files: List[str] = typer.Argument(
        default=None,
        help="The names of one or more files to restore",
    ),
    staged: bool = typer.Option(
        False,
        "--staged",
        help="Restore staged file to working directory",
    ),
    source: str = typer.Option(
        None,
        "--source",
        "-s",
        help="Restore the files' content from this commit instead of the index",
    ),
):
    from git_sim.restore import Restore

    scene = Restore(files=files, staged=staged, source=source)
    handle_animations(scene=scene)


def revert(
    commit: str = typer.Argument(
        default="HEAD",
        help="The ref (branch/tag), or commit ID to simulate revert",
    ),
    mainline: int = typer.Option(
        None,
        "--mainline",
        "-m",
        help="For a merge commit: the parent number (1-based) to keep",
    ),
    no_commit: bool = typer.Option(
        False,
        "--no-commit",
        "-n",
        help="Apply the reverse changes to the index and working tree without committing",
    ),
):
    from git_sim.revert import Revert

    scene = Revert(commit=commit, mainline=mainline, no_commit=no_commit)
    handle_animations(scene=scene)


def rm(
    files: List[str] = typer.Argument(
        default=None,
        help="The names of one or more files to remove from Git's index",
    )
):
    from git_sim.rm import Rm

    scene = Rm(files=files)
    handle_animations(scene=scene)


def stash(
    command: StashSubCommand = typer.Argument(
        default=None,
        help="Stash subcommand (push, pop, apply, drop, clear, list, show)",
    ),
    files: List[str] = typer.Argument(
        default=None,
        help="The name of the file to stash changes for",
    ),
    stash_index: str = typer.Argument(
        default="0",
        help="Stash index",
    ),
):
    from git_sim.stash import Stash

    scene = Stash(files=files, command=command, stash_index=stash_index)
    handle_animations(scene=scene)


def status():
    from git_sim.status import Status

    settings.allow_no_commits = True

    scene = Status()
    handle_animations(scene=scene)


def switch(
    branch: str = typer.Argument(
        ...,
        help="The name of the branch to switch to",
    ),
    c: bool = typer.Option(
        False,
        "-c",
        help="Create the specified branch if it doesn't already exist",
    ),
    detach: bool = typer.Option(
        False,
        "--detach",
        help="Allow switch resulting in detached HEAD state",
    ),
):
    from git_sim.switch import Switch

    scene = Switch(branch=branch, c=c, detach=detach)
    handle_animations(scene=scene)


def tag(
    name: str = typer.Argument(
        ...,
        help="The name of the tag",
    ),
    commit: str = typer.Argument(
        default=None,
        help="The commit to tag",
    ),
    d: bool = typer.Option(
        False,
        "-d",
        help="Delete the specified tag",
    ),
):
    from git_sim.tag import Tag

    scene = Tag(name=name, commit=commit, d=d)
    handle_animations(scene=scene)


def worktree(
    command: WorktreeSubCommand = typer.Argument(
        default=WorktreeSubCommand.LIST,
        help="Worktree subcommand (add, remove, list, prune)",
    ),
    path: str = typer.Argument(default=None, help="Worktree path (add/remove)"),
    branch: str = typer.Argument(
        default=None,
        help="With add: existing branch or commit to check out (default: a new branch named after the path)",
    ),
    new_branch: str = typer.Option(
        None,
        "-b",
        "--new-branch",
        help="With add: create this new branch and check it out",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="With remove: discard uncommitted changes"
    ),
):
    from git_sim.worktree import Worktree

    scene = Worktree(
        command=command, path=path, branch=branch, force=force, new_branch=new_branch
    )
    handle_animations(scene=scene)


def reflog(
    n: int = typer.Option(5, "-n", help="Number of HEAD reflog entries to show"),
):
    from git_sim.reflog import Reflog

    scene = Reflog(n=n)
    handle_animations(scene=scene)


def submodule(
    command: SubmoduleSubCommand = typer.Argument(
        default=SubmoduleSubCommand.STATUS,
        help="Submodule subcommand (add, update, init, status, deinit)",
    ),
    url_or_path: str = typer.Argument(
        default=None, help="With add: repository URL; with deinit: submodule path"
    ),
    path: str = typer.Argument(
        default=None, help="With add: where to place the submodule"
    ),
    init: bool = typer.Option(
        False, "--init", help="With update: also initialize new submodules"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="With deinit: discard local changes in the submodule",
    ),
):
    from git_sim.submodule import Submodule

    scene = Submodule(
        command=command, url_or_path=url_or_path, path=path, init=init, force=force
    )
    handle_animations(scene=scene)
