from __future__ import annotations

import typer

from typing import List, TYPE_CHECKING

from git_sim.enums import ResetMode, StashSubCommand
from git_sim.settings import settings

if TYPE_CHECKING:
    from manim import Scene


def handle_animations(scene: Scene) -> None:
    from git_sim.animations import handle_animations as _handle_animations

    return _handle_animations(scene)


def add(
    files: List[str] = typer.Argument(
        default=None,
        help="The names of one or more files to add to Git's staging area",
    )
):
    from git_sim.add import Add

    settings.hide_first_tag = True
    scene = Add(files=files)
    handle_animations(scene=scene)


def branch(
    name: str = typer.Argument(
        ...,
        help="The name of the new branch",
    )
):
    from git_sim.branch import Branch

    scene = Branch(name=name)
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
        help="The ref (branch/tag), or commit ID to simulate cherry-pick onto active branch",
    ),
    edit: str = typer.Option(
        None,
        "--edit",
        "-e",
        help="Specify a new commit message for the cherry-picked commit",
    ),
):
    from git_sim.cherrypick import CherryPick

    scene = CherryPick(commit=commit, edit=edit)
    handle_animations(scene=scene)


def clone(
    url: str = typer.Argument(
        ...,
        help="The web URL or filesystem path of the Git repo to clone",
    ),
):
    from git_sim.clone import Clone

    scene = Clone(url=url)
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
        help="Amend the last commit message, must be used with the --message flag",
    ),
):
    from git_sim.commit import Commit

    settings.hide_first_tag = True
    scene = Commit(message=message, amend=amend)
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
):
    from git_sim.push import Push

    scene = Push(remote=remote, branch=branch)
    handle_animations(scene=scene)


def rebase(
    branch: str = typer.Argument(
        ...,
        help="The branch to simulate rebasing the checked-out commit onto",
    )
):
    from git_sim.rebase import Rebase

    scene = Rebase(branch=branch)
    handle_animations(scene=scene)


def reset(
    commit: str = typer.Argument(
        default="HEAD",
        help="The ref (branch/tag), or commit ID to simulate reset to",
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

    settings.hide_first_tag = True
    scene = Reset(commit=commit, mode=mode, soft=soft, mixed=mixed, hard=hard)
    handle_animations(scene=scene)


def restore(
    files: List[str] = typer.Argument(
        default=None,
        help="The names of one or more files to restore",
    )
):
    from git_sim.restore import Restore

    settings.hide_first_tag = True
    scene = Restore(files=files)
    handle_animations(scene=scene)


def revert(
    commit: str = typer.Argument(
        default="HEAD",
        help="The ref (branch/tag), or commit ID to simulate revert",
    )
):
    from git_sim.revert import Revert

    settings.hide_first_tag = True
    scene = Revert(commit=commit)
    handle_animations(scene=scene)


def stash(
    command: StashSubCommand = typer.Argument(
        default=None,
        help="Stash subcommand (push, pop, apply)",
    ),
    files: List[str] = typer.Argument(
        default=None,
        help="The name of the file to stash changes for",
    ),
):
    from git_sim.stash import Stash

    settings.hide_first_tag = True
    scene = Stash(files=files, command=command)
    handle_animations(scene=scene)


def status():
    from git_sim.status import Status

    settings.hide_first_tag = True
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
):
    from git_sim.switch import Switch

    scene = Switch(branch=branch, c=c)
    handle_animations(scene=scene)


def tag(
    name: str = typer.Argument(
        ...,
        help="The name of the new tag",
    )
):
    from git_sim.tag import Tag

    scene = Tag(name=name)
    handle_animations(scene=scene)
