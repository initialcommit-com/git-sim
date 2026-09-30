from __future__ import annotations

import inspect

import typer

from typing import List

from git_sim.settings import settings
from git_sim.enums import (
    BisectSubCommand,
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


def _resume(operation: str, cont: bool, abort: bool, skip: bool, *others) -> bool:
    """--continue / --abort / --skip: run instead of the command, which then
    takes no other arguments. Returns whether one was given (and handled)."""
    actions = [a for a, on in (("continue", cont), ("abort", abort), ("skip", skip)) if on]
    if not actions:
        return False
    if len(actions) > 1 or any(others):
        print(f"git-sim error: git {operation} --{actions[0]} takes no other arguments or options")
        raise typer.Exit(1)
    from git_sim.resume import Resume

    scene = Resume(operation=operation, action=actions[0])
    with settings.font_context:
        from git_sim.animations import handle_animations as _handle_animations

        _handle_animations(scene, operation.replace("-", "_"))
    return True


def _need(value, what: str):
    if not value:
        print(f"git-sim error: {what}")
        raise typer.Exit(1)


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
        None,
        help="The branch to create, delete (-d/-D), rename (-m) or set the upstream of (-u; default: the current branch). Without one, the branches are listed. With --merged/--no-merged: the commit to compare with",
    ),
    new_name: str = typer.Argument(
        default=None,
        help="With -m: the new name for the branch. Otherwise the commit the new branch starts at (default: HEAD), e.g. a deleted branch's tip from the reflog",
    ),
    d: bool = typer.Option(
        False, "-d", "--delete", help="Delete the branch (refused if unmerged)"
    ),
    D: bool = typer.Option(
        False, "-D", help="Force-delete the branch even if unmerged"
    ),
    m: bool = typer.Option(False, "-m", "--move", help="Rename the branch to NEW_NAME"),
    all: bool = typer.Option(
        False, "-a", "--all", help="List the remote-tracking branches too"
    ),
    verbose: int = typer.Option(
        0,
        "-v",
        "--verbose",
        count=True,
        help="List each branch's last commit; twice (-vv) also its upstream and how far ahead or behind it is",
    ),
    merged: bool = typer.Option(
        False,
        "--merged",
        help="List the branches whose tips are in the history of the commit given as NAME (default: HEAD)",
    ),
    no_merged: bool = typer.Option(
        False,
        "--no-merged",
        help="List the branches whose tips are not in the history of the commit given as NAME (default: HEAD)",
    ),
    set_upstream_to: str = typer.Option(
        None,
        "-u",
        "--set-upstream-to",
        help="Set the upstream of the branch (default: the current one) to this remote-tracking or local branch",
    ),
):
    from git_sim.branch import Branch

    # git branch --merged [<commit>]: the commit is optional, so it arrives
    # as the positional argument (typer options can't take an optional value)
    commit = None
    if merged or no_merged:
        commit, name = name or "HEAD", None
        if new_name:
            print("git-sim error: --merged and --no-merged take at most one commit")
            raise typer.Exit(1)
    scene = Branch(
        name=name,
        new_name=new_name,
        delete=d,
        force_delete=D,
        move=m,
        all=all,
        verbose=verbose,
        merged=commit if merged else None,
        no_merged=commit if no_merged else None,
        set_upstream_to=set_upstream_to,
    )
    handle_animations(scene=scene)


def checkout(
    branch: List[str] = typer.Argument(
        default=None,
        help="The name of the branch to checkout, or after -- the files whose changes to discard (git checkout -- <paths>)",
    ),
    b: bool = typer.Option(
        False,
        "-b",
        help="Create the specified branch if it doesn't already exist",
    ),
):
    import sys

    from git_sim.checkout import Checkout, CheckoutFiles, args_after_dashes, split_checkout_args

    # click drops the --, so it is looked for on the command line itself
    after = args_after_dashes(sys.argv[1:]) if "checkout" in sys.argv else None
    if b and after is None:  # -b names a new branch, which is no file
        revisions, paths = list(branch or []), []
    else:
        revisions, paths = split_checkout_args(branch, after)
    if paths:
        if b:
            print("git-sim error: -b creates a branch; it takes no paths")
            raise typer.Exit(1)
        if revisions:
            print(
                f"git-sim error: git checkout {revisions[0]} -- <paths> isn't simulated; "
                f"git-sim restore --source {revisions[0]} <paths> draws the files arriving in the working directory"
            )
            raise typer.Exit(1)
        scene = CheckoutFiles(paths=paths)
    else:
        _need(revisions, "name the branch to check out, or the files after --")
        if len(revisions) > 1:
            print("git-sim error: git checkout takes one branch or commit")
            raise typer.Exit(1)
        scene = Checkout(branch=revisions[0], b=b)
    handle_animations(scene=scene)


def cherry_pick(
    commit: str = typer.Argument(
        None,
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
    cont: bool = typer.Option(
        False, "--continue", help="After resolving a conflict: carry on with the cherry-pick in progress"
    ),
    abort: bool = typer.Option(
        False, "--abort", help="Call off the cherry-pick in progress and go back to where it started"
    ),
    skip: bool = typer.Option(
        False, "--skip", help="Drop the commit that stopped the cherry-pick, and carry on"
    ),
):
    if _resume("cherry-pick", cont, abort, skip, commit, edit, no_commit):
        return
    _need(commit, "name the commit to cherry-pick")
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
        help="The directory to clone into (default: one named after the repo)",
    ),
    depth: int = typer.Option(
        None,
        "--depth",
        min=1,
        help="Shallow clone: only the last DEPTH commits, the oldest cut off from its parents",
    ),
    branch: str = typer.Option(
        None,
        "--branch",
        "-b",
        help="Check out this branch (or tag) instead of the one the remote's HEAD points at",
    ),
):
    from git_sim.clone import Clone

    scene = Clone(url=url, path=path, depth=depth, branch=branch)
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
    glob: bool = typer.Option(
        False,
        "--global",
        help="Read or write your own settings file (~/.gitconfig), used by every repository of yours",
    ),
    settings: List[str] = typer.Argument(
        default=None,
        help="The names and values of one or more config settings to set",
    ),
):
    from git_sim.config import Config

    scene = Config(l=l, settings=settings, glob=glob)
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
    prune: bool = typer.Option(
        False,
        "--prune",
        "-p",
        help="Remove remote-tracking branches whose branch is gone from the remote",
    ),
    all: bool = typer.Option(
        False,
        "--all",
        help="Fetch every remote, not just one",
    ),
):
    from git_sim.fetch import Fetch

    scene = Fetch(remote=remote, branch=branch, prune=prune, all=all)
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
    paths: List[str] = typer.Argument(
        default=None,
        help="Only the commits that changed these files (git log -- <file>)",
    ),
    oneline: bool = typer.Option(
        False, "--oneline", help="One line per commit (the drawing is the same; it shows in the title)"
    ),
    graph: bool = typer.Option(
        False, "--graph", help="Draw the history as a graph (it always is; it shows in the title)"
    ),
    patch: bool = typer.Option(
        False, "-p", "--patch", help="Also show the newest listed commit's patch"
    ),
    follow: bool = typer.Option(
        False, "--follow", help="With one file: carry its history back past renames"
    ),
    search: str = typer.Option(
        None, "-S", help="Only the commits that added or removed this text"
    ),
    author: str = typer.Option(
        None, "--author", help="Only the commits whose author matches this name or email"
    ),
    since: str = typer.Option(
        None, "--since", "--after", help="Only the commits newer than this date, e.g. 2024-03-01 or '2 weeks ago'"
    ),
    until: str = typer.Option(
        None, "--until", "--before", help="Only the commits older than this date"
    ),
):
    from git_sim.log import Log

    scene = Log(
        ctx=ctx,
        n=n,
        all=all,
        oneline=oneline,
        graph=graph,
        paths=paths,
        patch=patch,
        follow=follow,
        search=search,
        author=author,
        since=since,
        until=until,
    )
    handle_animations(scene=scene)


def shortlog(
    rev: str = typer.Argument(
        default=None,
        help="The commits to count: a branch, tag, commit or range A..B (default HEAD)",
    ),
    summary: bool = typer.Option(
        False, "-s", "--summary", help="Only the counts, not each author's commit subjects"
    ),
    numbered: bool = typer.Option(
        False, "-n", "--numbered", help="Most commits first, rather than by name"
    ),
    email: bool = typer.Option(False, "-e", "--email", help="Show each author's email address"),
):
    from git_sim.shortlog import Shortlog

    scene = Shortlog(rev=rev, summary=summary, numbered=numbered, email=email)
    handle_animations(scene=scene)


def grep(
    pattern: str = typer.Argument(..., help="The text (a regular expression) to search for"),
    args: List[str] = typer.Argument(
        default=None,
        help="A commit, branch or tag to search instead of the working tree, and/or paths to search in",
    ),
    line_number: bool = typer.Option(
        False, "-n", "--line-number", help="Show the line number of each match"
    ),
    ignore_case: bool = typer.Option(
        False, "-i", "--ignore-case", help="Match regardless of upper and lower case"
    ),
):
    from git_sim.grep import Grep

    scene = Grep(pattern=pattern, args=args, line_number=line_number, ignore_case=ignore_case)
    handle_animations(scene=scene)


def describe(
    commit: str = typer.Argument(
        default=None,
        help="The commit to name after its nearest tag (default HEAD)",
    ),
    tags: bool = typer.Option(
        False, "--tags", help="Count lightweight tags too, not only annotated ones"
    ),
):
    from git_sim.describe import Describe

    scene = Describe(commit=commit, tags=tags)
    handle_animations(scene=scene)


def merge(
    branch: str = typer.Argument(
        None,
        help="The name of the branch to merge into the active checked-out branch",
    ),
    no_ff: bool = typer.Option(
        False,
        "--no-ff",
        help="Simulate creation of a merge commit in all cases, even when the merge could instead be resolved as a fast-forward",
    ),
    message: str = typer.Option(
        None,
        "--message",
        "-m",
        help="The commit message of the new merge commit (default: the one git writes, e.g. Merge branch 'feature')",
    ),
    squash: bool = typer.Option(
        False,
        "--squash",
        help="Stage the branch's changes as one set, without committing or recording a merge",
    ),
    ff_only: bool = typer.Option(
        False,
        "--ff-only",
        help="Merge only if it can fast-forward; git refuses otherwise",
    ),
    allow_unrelated_histories: bool = typer.Option(
        False,
        "--allow-unrelated-histories",
        help="Merge a branch that shares no commit with this one (git refuses without it)",
    ),
    cont: bool = typer.Option(
        False, "--continue", help="After resolving a conflict: carry on with the merge in progress"
    ),
    abort: bool = typer.Option(
        False, "--abort", help="Call off the merge in progress and go back to where it started"
    ),
):
    if _resume("merge", cont, abort, False, branch, no_ff, squash, ff_only, allow_unrelated_histories):
        return
    _need(branch, "name the branch to merge")
    from git_sim.merge import Merge

    scene = Merge(
        branch=branch,
        no_ff=no_ff,
        message=message,
        squash=squash,
        ff_only=ff_only,
        allow_unrelated_histories=allow_unrelated_histories,
    )
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
    rebase: bool = typer.Option(
        False,
        "--rebase",
        "-r",
        help="Replay your local commits on top of the fetched branch instead of merging",
    ),
):
    from git_sim.pull import Pull

    scene = Pull(remote=remote, branch=branch, rebase=rebase)
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
        "-u",
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
    delete: bool = typer.Option(
        False,
        "--delete",
        "-d",
        help="Delete the branch on the remote",
    ),
    tags: bool = typer.Option(
        False,
        "--tags",
        help="Push every tag the remote doesn't have (and no branches)",
    ),
):
    from git_sim.push import Push

    scene = Push(
        remote=remote,
        branch=branch,
        set_upstream=set_upstream,
        force=force,
        force_with_lease=force_with_lease,
        delete=delete,
        tags=tags,
    )
    handle_animations(scene=scene)


def rebase(
    branch: str = typer.Argument(
        None,
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
    cont: bool = typer.Option(
        False, "--continue", help="After resolving a conflict: carry on with the rebase in progress"
    ),
    abort: bool = typer.Option(
        False, "--abort", help="Call off the rebase in progress and go back to where it started"
    ),
    skip: bool = typer.Option(
        False, "--skip", help="Drop the commit that stopped the rebase, and carry on"
    ),
):
    if _resume("rebase", cont, abort, skip, branch, onto, interactive, todo):
        return
    _need(branch, "name the upstream to rebase onto")
    from git_sim.rebase import Rebase

    scene = Rebase(branch=branch, onto=onto, interactive=interactive, todo=todo)
    handle_animations(scene=scene)


def remote(
    command: RemoteSubCommand = typer.Argument(
        default=None,
        help="Remote subcommand (add, rename, remove, get-url, set-url, show)",
    ),
    remote: str = typer.Argument(
        default=None,
        help="The name of the remote",
    ),
    url_or_path: str = typer.Argument(
        default=None,
        help="The url or path to the remote",
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="With no subcommand: list each remote with its fetch and push URLs",
    ),
):
    from git_sim.remote import Remote

    scene = Remote(
        command=command, remote=remote, url_or_path=url_or_path, verbose=verbose
    )
    handle_animations(scene=scene)


def ls_remote(
    remote: str = typer.Argument(
        default=None,
        help="The remote (a name, or a URL or path) to list the refs of (default: the current branch's remote, else origin)",
    ),
    heads: bool = typer.Option(
        False,
        "--heads",
        "--branches",
        help="List only the remote's branches",
    ),
    tags: bool = typer.Option(
        False,
        "--tags",
        "-t",
        help="List only the remote's tags",
    ),
):
    from git_sim.lsremote import LsRemote

    scene = LsRemote(remote=remote, heads=heads, tags=tags)
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
        help="The files to restore: names, folders or . for every changed file",
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
        help="Take the files' content from this commit (default: the staging area, or HEAD with --staged)",
    ),
):
    from git_sim.restore import Restore

    scene = Restore(files=files, staged=staged, source=source)
    handle_animations(scene=scene)


def revert(
    commit: List[str] = typer.Argument(
        default=None,
        help="The commits to simulate reverting (default: HEAD): refs, commit IDs or ranges A..B",
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

    scene = Revert(commit=commit or ["HEAD"], mainline=mainline, no_commit=no_commit)
    handle_animations(scene=scene)


def rm(
    files: List[str] = typer.Argument(
        default=None,
        help="The names of one or more files to remove from Git's index",
    ),
    cached: bool = typer.Option(
        False,
        "--cached",
        help="Stop tracking the files but keep them on disk",
    ),
):
    from git_sim.rm import Rm

    scene = Rm(files=files, cached=cached)
    handle_animations(scene=scene)


def stash(
    command: StashSubCommand = typer.Argument(
        default=None,
        help="Stash subcommand (push, pop, apply, drop, clear, list, show, branch)",
    ),
    files: List[str] = typer.Argument(
        default=None,
        help="push: the files to stash changes for; branch: the new branch's name",
    ),
    stash_index: str = typer.Argument(
        default="0",
        help="Stash index",
    ),
    include_untracked: bool = typer.Option(
        False,
        "--include-untracked",
        "-u",
        help="push: stash untracked files too",
    ),
    message: str = typer.Option(
        None,
        "--message",
        "-m",
        help="push: the message the entry is saved with",
    ),
    patch: bool = typer.Option(
        False,
        "--patch",
        "-p",
        help="show: the entry's changes line by line, not just its files",
    ),
):
    from git_sim.stash import Stash

    # `stash push a.txt`: the last word lands in stash_index, since a trailing
    # positional wins over the variadic one. Anything that is not an index is
    # a file when the subcommand takes files.
    import re

    branch = None
    if command == StashSubCommand.BRANCH:
        # `stash branch topic [stash@{1}]`: the name, then the entry
        words = list(files or [])
        if words or stash_index != "0":  # a lone default "0" is no name
            words.append(stash_index)
        if not words:
            print("git-sim error: git stash branch needs the new branch's name")
            raise typer.Exit(1)
        if len(words) > 2:
            print("git-sim error: git stash branch takes a branch name and one stash entry")
            raise typer.Exit(1)
        branch = words[0]
        stash_index = words[1] if len(words) > 1 else "0"
        files = []
    elif (
        command
        in (StashSubCommand.PUSH, StashSubCommand.POP, StashSubCommand.APPLY, None)
        and stash_index is not None
        and not re.fullmatch(r"\d+|stash@\{\d+\}", stash_index)
    ):
        files = (files or []) + [stash_index]
        stash_index = "0"

    scene = Stash(
        files=files,
        command=command,
        stash_index=stash_index,
        include_untracked=include_untracked,
        message=message,
        patch=patch,
        branch=branch,
    )
    handle_animations(scene=scene)


def status():
    from git_sim.status import Status

    settings.allow_no_commits = True

    scene = Status()
    handle_animations(scene=scene)


def switch(
    branch: str = typer.Argument(
        ...,
        help="The name of the branch to switch to ('-' for the previous one); a name only a remote has (origin/NAME) makes a local branch tracking it",
    ),
    start_point: str = typer.Argument(
        None,
        help="With -c: the commit the new branch starts at (default: HEAD); a remote-tracking branch also becomes its upstream",
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

    scene = Switch(branch=branch, c=c, detach=detach, start_point=start_point)
    handle_animations(scene=scene)


def tag(
    name: str = typer.Argument(
        None,
        help="The name of the tag (with -l: a pattern such as 'v1.*' to list the matching tags)",
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
    annotate: bool = typer.Option(
        False,
        "-a",
        "--annotate",
        help="Make an annotated tag: a tag object with a tagger, a date and the message given with -m",
    ),
    message: str = typer.Option(
        None,
        "-m",
        "--message",
        help="The annotated tag's message (implies -a)",
    ),
    l: bool = typer.Option(
        False,
        "-l",
        "--list",
        help="List the tags, highlighting the ones matching NAME as a pattern",
    ),
):
    from git_sim.tag import Tag

    scene = Tag(name=name, commit=commit, d=d, annotate=annotate, message=message, list_tags=l)
    handle_animations(scene=scene)


def worktree(
    command: WorktreeSubCommand = typer.Argument(
        default=WorktreeSubCommand.LIST.value,  # the value: click validates the default against its choices
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


def show(
    revision: str = typer.Argument(
        "HEAD",
        help="The commit, branch or tag to show, or REV:PATH for one file as it was in REV",
    ),
):
    from git_sim.show import Show

    scene = Show(revision=revision)
    handle_animations(scene=scene)


def diff(
    args: List[str] = typer.Argument(
        default=None,
        help="Up to two commits (or A..B, A...B) to compare, and/or paths to limit the diff to",
    ),
    staged: bool = typer.Option(
        False,
        "--staged",
        "--cached",
        help="Compare the staging area with HEAD (or the given commit)",
    ),
    stat: bool = typer.Option(
        False,
        "--stat",
        help="Summarize: each changed file with its line counts, as git diff --stat prints them",
    ),
):
    from git_sim.diff import Diff

    scene = Diff(args=args, staged=staged, stat=stat)
    handle_animations(scene=scene)


def blame(
    file: str = typer.Argument(
        ...,
        help="The tracked file to blame",
    ),
    lines: str = typer.Option(
        None,
        "-L",
        help="Only these lines, as START,END or START,+COUNT",
    ),
):
    from git_sim.blame import Blame

    scene = Blame(file=file, lines=lines)
    handle_animations(scene=scene)


def check_ignore(
    paths: List[str] = typer.Argument(
        default=None,
        help="The paths to check against the ignore rules",
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Print the rule that matches each path, as git check-ignore -v does",
    ),
):
    from git_sim.check_ignore import CheckIgnore

    scene = CheckIgnore(paths=paths, verbose=verbose)
    handle_animations(scene=scene)


def bisect(
    command: BisectSubCommand = typer.Argument(
        ...,
        help="Bisect subcommand (start, bad, good, new, old, skip, reset)",
    ),
    revs: List[str] = typer.Argument(
        default=None,
        help="start: the bad commit, then good ones; bad/good/skip: the commit to mark (default HEAD); reset: where to return",
    ),
):
    from git_sim.bisect import Bisect

    scene = Bisect(command=command, revs=revs)
    handle_animations(scene=scene)


def submodule(
    command: SubmoduleSubCommand = typer.Argument(
        default=SubmoduleSubCommand.STATUS.value,  # the value: click validates the default against its choices
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
