"""Every subcommand and every option must be exercised by the matrix. A new
option that lands without a case fails here, which is the point."""

from __future__ import annotations

import click
import pytest
import typer

from cases import CASES

# Options that need an animation backend, a network, or a shell, and so are
# exercised elsewhere or deliberately left out of the matrix.
EXEMPT_GLOBAL = {
    "--animate", "--no-animate", "--low-quality", "--speed", "--video-format", "--logo", "--title",
    "--show-intro", "--no-show-intro", "--show-outro", "--no-show-outro", "--outro-top-text", "--outro-bottom-text",
    "--install-completion", "--show-completion", "--auto-open", "-d", "-v", "--version",
}
EXEMPT_COMMANDS = {"install", "uninstall", "aliases", "live", "preflight", "media-dir"}  # test_tools.py
EXEMPT_OPTIONS = {
    ("live", "--port"), ("live", "--interval"), ("live", "--zones"), ("live", "--no-zones"), ("live", "--replay"), ("live", "--session"),
}


def schema():
    from git_sim.__main__ import app

    group = typer.main.get_command(app)
    commands = {}
    for name, cmd in group.commands.items():
        opts = set()
        for p in cmd.params:
            if isinstance(p, click.Option):
                opts.update(p.opts)
                opts.update(p.secondary_opts)
        commands[name] = opts
    globals_ = set()
    for p in group.params:
        if isinstance(p, click.Option):
            globals_.update(p.opts)
            globals_.update(p.secondary_opts)
    return commands, globals_


def used_options():
    used = {}
    for case in CASES:
        cmd = case.args[0]
        used.setdefault(cmd, set())
        for a in case.args[1:]:
            if a.startswith("--"):
                used[cmd].add(a.split("=")[0])
            elif a.startswith("-") and len(a) > 1 and not a[1:].isdigit():
                # -fdx is -f, -d and -x
                for ch in a[1:]:
                    used[cmd].add(f"-{ch}")
    return used


def test_every_subcommand_has_cases():
    commands, _ = schema()
    used = used_options()
    missing = sorted(c for c in commands if c not in EXEMPT_COMMANDS and c not in used)
    assert not missing, f"subcommands without a case in the matrix: {missing}"


def test_every_subcommand_has_an_error_case():
    commands, _ = schema()
    with_error = {c.args[0] for c in CASES if c.error}
    # commands that cannot fail on their arguments alone
    no_error_possible = {"log", "status", "init", "reflog", "clean", "commit", "stash", "add", "restore"}
    missing = sorted(c for c in commands if c not in EXEMPT_COMMANDS and c not in no_error_possible and c not in with_error)
    assert not missing, f"subcommands without an error case: {missing}"


@pytest.mark.parametrize("command", sorted(schema()[0]))
def test_every_option_is_exercised(command):
    if command in EXEMPT_COMMANDS:
        pytest.skip("covered by test_tools.py")
    commands, _ = schema()
    used = used_options().get(command, set())
    # an option is exercised if any of its spellings appears in a case
    missing = []
    seen_groups = set()
    from git_sim.__main__ import app

    group = typer.main.get_command(app)
    for p in group.commands[command].params:
        if not isinstance(p, click.Option):
            continue
        spellings = set(p.opts) | set(p.secondary_opts)
        if (command, next(iter(p.opts))) in EXEMPT_OPTIONS:
            continue
        if not spellings & used:
            missing.append("/".join(sorted(spellings)))
    assert not missing, f"git-sim {command}: options never exercised by the matrix: {missing}"


def test_global_options_are_exercised():
    """The global flags are checked in test_options.py; this keeps that file
    honest when a global option is added."""
    import inspect
    import test_options

    source = inspect.getsource(test_options)
    _, globals_ = schema()
    missing = sorted(
        o for o in globals_
        if o not in EXEMPT_GLOBAL and o not in source and o.replace("--no-", "--") not in source
    )
    assert not missing, f"global options never exercised in test_options.py: {missing}"
