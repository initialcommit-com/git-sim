"""Pre-tool-use hook: automatic git-sim pre-flight checks for AI coding agents.

Installed as ``git-sim-hook``, this program reads the hook payload an agent
sends on stdin before running a shell command, and when the command contains
a git operation the pre-flight engine rates risky, answers with the
deterministic facts — what would be lost, and how to undo it — plus a
rendered git-sim image of the operation.

It speaks the hook dialects of Claude Code, Codex CLI, Cursor, GitHub
Copilot CLI, Gemini CLI and VS Code's agent hooks (which read Copilot CLI
hook files, so the two share one). The agent is taken from ``--agent <name>``
when the installer put it in the config, and detected from the payload shape
otherwise. Agents whose hooks can ask the user (Claude Code, Cursor, Copilot,
VS Code) get an "ask" decision; agents whose hooks can only allow or deny
(Codex, Gemini) get a deny whose reason carries the facts and tells the
agent how to proceed once the user has approved.

The hook fails open: any internal error results in no output (exit 0), which
leaves the agent's normal permission flow untouched.

Environment variables:
    GIT_SIM_HOOK_ASK_ON  "caution" (default) or "destructive" — minimum risk
                         level that triggers a decision.
    GIT_SIM_HOOK_MODE    "ask" (default): prompt the user, or deny with
                         instructions where the agent cannot prompt.
                         "deny": deny risky commands outright (unattended runs).
                         "warn": allow, but attach the facts as a message.
    GIT_SIM_HOOK_RENDER  "0" to skip rendering the simulation (facts only).
    GIT_SIM_HOOK_OPEN    "always" (default): open the simulation in the
                         browser as the approval prompt appears.
                         Where: GIT_SIM_HOOK_OPEN_IN below.
                         "never": don't render or open it (facts only).
                         "ask": a small dialog asks whether to see it before
                         the approval prompt appears.
    GIT_SIM_HOOK_OPEN_IN "hosted" (default): the git-sim viewer at
                         initialcommit.com, everything in the link's #fragment
                         (no query string), so nothing reaches the server.
                         "local": the saved .html file. Defaults to git-sim's
                         own setting, so git_sim_open_in=local covers both.
    GIT_SIM_HOOK_TEXT    "1" to add the plain-text commit graph to the reason.
    GIT_SIM_HOOK_AGENT   force the agent dialect (same values as --agent).
    GIT_SIM_HOOK_REPORT_SAFE
                         "1": also answer for git commands the engine rated
                         below the threshold, with an "allow" that carries a
                         one-line "SAFE" (or "CAUTION") note, so the user sees
                         the level every time. Default "1" inside VS Code,
                         "0" elsewhere (where it would only add noise).

The simulation is git-sim's interactive page. Inside VS Code (its agent hooks,
or any agent running in its terminal) the hook leaves a note in
git-sim_media/inbox for the git-sim extension, which opens the page in an
editor tab; when no extension picks the note up, it goes on as anywhere else.

Approval override: a command prefixed with ``GIT_SIM_APPROVE=1`` (or
``$env:GIT_SIM_APPROVE=1;`` in PowerShell) is let through without a
prompt. Agents that cannot ask are told to re-run that way after the user
approves.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from typing import List, Optional, Tuple

from git_sim.preflight import (
    RISKY_SUBCOMMANDS,
    PreflightReport,
    Risk,
    analyze,
    parse_command,
)

# Cheap pre-filter so the vast majority of shell commands exit immediately
# without touching GitPython: the word "git" (not "git-sim") plus one of the
# subcommands that has an analyzer. This only gates the expensive work; the
# per-command check below decides what is actually analyzed.
GIT_WORD = re.compile(r"\bgit(?!-)\b")
RISKY_WORDS = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in sorted(RISKY_SUBCOMMANDS)) + r")\b"
)

SHELL_SEPARATORS = re.compile(r"&&|\|\||;|\||\n")
APPROVAL_OVERRIDE = re.compile(r"GIT_SIM_APPROVE\s*=\s*['\"]?1")

# Agent dialects. ``asks`` says whether the agent's hook protocol has a decision
# that prompts the user; without it the hook can only allow or deny.
AGENTS = {
    "claude": {"label": "Claude Code", "asks": True},
    "codex": {"label": "Codex CLI", "asks": False},
    "cursor": {"label": "Cursor", "asks": True},
    "copilot": {"label": "GitHub Copilot CLI", "asks": True},
    "gemini": {"label": "Gemini CLI", "asks": False},
    "vscode": {"label": "VS Code", "asks": True},
}
SHELL_TOOLS = {
    "bash",
    "powershell",
    "shell",
    "run_shell_command",
    "run_terminal_cmd",
    "runterminalcommand",  # VS Code agent hooks
    "run_in_terminal",
}
VSCODE_TOOLS = {"runterminalcommand", "run_in_terminal"}


def extract_git_commands(shell_command: str) -> List[str]:
    """Pull individual git invocations out of a (possibly compound) shell command."""
    git_commands = []
    for segment in SHELL_SEPARATORS.split(shell_command):
        tokens = segment.strip().split()
        # Skip leading env assignments (VAR=x git ...).
        while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
            tokens = tokens[1:]
        if tokens and tokens[0] == "git":
            git_commands.append(" ".join(tokens))
    return git_commands


def _subcommand(git_command: str) -> str:
    """The git subcommand, skipping global options such as -C <path> or -c k=v."""
    try:
        tokens = parse_command(git_command)
    except ValueError:
        tokens = git_command.split()[1:]
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        return token
    return ""


def risky_git_commands(shell_command: str) -> List[str]:
    """The git invocations in a shell command whose own subcommand can discard
    something. `git add x && git commit -m 'reset branch'` yields only the
    commit, and a filename like reset.py never counts."""
    return [
        cmd
        for cmd in extract_git_commands(shell_command)
        if _subcommand(cmd) in RISKY_SUBCOMMANDS
    ]


CD_COMMANDS = {"cd", "chdir", "set-location", "sl", "pushd", "push-location"}
POPD_COMMANDS = {"popd", "pop-location"}


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        return token[1:-1]
    return token


def _resolve_dir(target: str, current: Optional[str]) -> Optional[str]:
    """Where `cd target` lands from `current`, or None when it can't be told
    without running the shell (variables, `cd -`, a relative path from an
    unknown place)."""
    target = os.path.expandvars(os.path.expanduser(_unquote(target)))
    if "$" in target or "%" in target or target == "-":
        return None
    # Git Bash spells C:\x as /c/x.
    m = re.match(r"^/([A-Za-z])(/.*)?$", target) if os.name == "nt" else None
    if m:
        target = f"{m.group(1)}:{m.group(2) or '/'}"
    if os.path.isabs(target):
        return os.path.normpath(target)
    if current is None:
        return None
    return os.path.normpath(os.path.join(current, target))


def _strip_global_options(tokens: List[str], where: Optional[str]):
    """`git -C dir -c k=v reset ...` -> (["git", "reset", ...], dir). Global
    options before the subcommand are dropped; -C moves the directory like
    git does (relative to the previous one)."""
    out, i = [tokens[0]], 1
    while i < len(tokens) and tokens[i].startswith("-"):
        opt = tokens[i]
        if opt == "-C" and i + 1 < len(tokens):
            where = _resolve_dir(tokens[i + 1], where)
            i += 2
        elif opt in ("-c", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(tokens):
            if opt == "--work-tree":
                where = _resolve_dir(tokens[i + 1], where)
            i += 2
        elif opt.startswith("--work-tree="):
            where = _resolve_dir(opt.split("=", 1)[1], where)
            i += 1
        else:
            i += 1
    return out + tokens[i:], where


def located_git_commands(shell_command: str, cwd: str) -> List[Tuple[str, Optional[str]]]:
    """The risky git invocations in a shell command, each with the directory
    it runs in: the hook's cwd, moved by any cd / Set-Location / pushd / popd
    before it and by git's own -C. The directory is None when it can't be
    worked out, so the command is not judged against the wrong repository."""
    located = []
    where: Optional[str] = cwd
    stack: List[Optional[str]] = []
    for segment in SHELL_SEPARATORS.split(shell_command):
        segment = segment.strip().lstrip("(").rstrip(")")
        try:
            tokens = shlex.split(segment, posix=False)  # keeps C:\ paths intact
        except ValueError:
            tokens = segment.split()
        while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
            tokens = tokens[1:]
        if not tokens:
            continue
        word = tokens[0].lower()
        if word in CD_COMMANDS:
            args = [t for t in tokens[1:] if t.lower() not in ("-path", "-literalpath")]
            if word in ("pushd", "push-location"):
                stack.append(where)
            if args:
                where = _resolve_dir(args[0], where)
            elif word in ("cd", "chdir"):
                where = os.path.expanduser("~")
            continue
        if word in POPD_COMMANDS:
            where = stack.pop() if stack else None
            continue
        if tokens[0] != "git":
            continue
        command = " ".join(tokens)
        if _subcommand(command) not in RISKY_SUBCOMMANDS:
            continue
        stripped, target = _strip_global_options(tokens, where)
        located.append((" ".join(stripped), target))
    return located


def _risk_triggers(risk: Risk, threshold: str) -> bool:
    if threshold == "destructive":
        return risk == Risk.DESTRUCTIVE
    return risk in (Risk.CAUTION, Risk.DESTRUCTIVE)


def _open_file(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def in_vscode(agent: Optional[str], hook_input: dict) -> bool:
    """Whether this hook call comes from VS Code: its own agent dialect, its
    terminal tool in the payload (the shared Copilot hook file runs there too),
    or VS Code's process environment around us."""
    tool = str(hook_input.get("tool_name") or "").lower()
    return (
        agent == "vscode" or tool in VSCODE_TOOLS or bool(os.environ.get("VSCODE_PID"))
    )


def post_to_inbox(page_path: str, report: PreflightReport, cwd: str) -> Optional[str]:
    """Leave a note for the VS Code extension about an interactive page just
    written, so it can open it in an editor tab. Written to a temporary name
    and renamed, so a watcher never reads a half-written file."""
    from git_sim.paths import inbox_dir

    try:
        inbox = inbox_dir()
        inbox.mkdir(parents=True, exist_ok=True)
        stamp = time.time_ns()
        record = {
            "page": page_path,
            "command": report.command,  # already starts with "git"
            "risk": report.risk.value,
            "repo": cwd,
            "time": stamp,
        }
        tmp = inbox / f".{os.getpid()}-{stamp}.tmp"
        final = inbox / f"{stamp}.json"
        tmp.write_text(json.dumps(record), encoding="utf-8")
        tmp.replace(final)
        return str(final)
    except Exception:
        return None


def _plural(text: str) -> str:
    """The engine writes "2 commit(s)"; a prompt reads better as "2 commits"."""
    text = re.sub(r"\b1 ((?:[a-z]+ )?\w+?)\(s\)", r"1 \1", text)  # "1 untracked path"
    return re.sub(r"(\w)\(s\)", r"\1s", text)  # "2 of the replayed commits" too


def _headline(report: PreflightReport) -> str:
    line = f"git-sim preflight: {report.risk.value.upper()} — {report.command}"
    elsewhere = getattr(report, "elsewhere", None)
    if elsewhere:
        line += f"  (in {elsewhere})"
    return line


def _summary(report: PreflightReport) -> str:
    """The summary on one line. A summary ending in a colon introduces a list
    in the facts (the commits a branch deletion abandons); the first few go
    on the same line."""
    summary = report.summary.strip()
    if summary.endswith(":"):
        items = [f.strip() for f in report.facts if f.startswith("  ")]
        summary = summary[:-1]
        if items:
            more = f" and {len(items) - 3} more" if len(items) > 3 else ""
            summary += ": " + ", ".join(items[:3]) + more
        summary += "."
    return summary


def _losses(report: PreflightReport) -> Optional[str]:
    if not report.would_lose:
        return None
    shown = report.would_lose[:4]
    more = f"; and {len(report.would_lose) - 4} more" if len(report.would_lose) > 4 else ""
    return "Loses: " + "; ".join(shown) + more


def _warnings(report: PreflightReport) -> List[str]:
    """Warnings that add something: "can't be recovered" goes without saying
    once a loss is already marked NOT recoverable."""
    unrecoverable = any("NOT recoverable" in loss for loss in report.would_lose)
    kept = [
        w
        for w in report.warnings
        if not (unrecoverable and re.search(r"cannot be recovered|permanent", w, re.I))
    ]
    return [f"Warning: {w}" for w in kept[:2]]


CLAIM_SECONDS = 30


def claim_simulation(hook_input: dict, command: str, cwd: str) -> bool:
    """Whether this hook run is the one to render and open the simulation.

    The hook can be registered more than once for the same agent (a global
    and a project settings file, say), and every copy runs for each command.
    The first to claim the tool call shows the simulation; the others only
    answer. A call is known by the agent's tool-call id, or failing that by
    its session, command and directory within CLAIM_SECONDS."""
    import hashlib
    import tempfile

    call = hook_input.get("tool_use_id") or hook_input.get("toolUseId") or ""
    session = hook_input.get("session_id") or hook_input.get("sessionId") or ""
    key = call or f"{session}\0{command}\0{cwd}"
    claims = os.path.join(tempfile.gettempdir(), "git-sim-hook-claims")
    try:
        os.makedirs(claims, exist_ok=True)
        now = time.time()
        for name in os.listdir(claims):  # forget old claims
            path = os.path.join(claims, name)
            try:
                if now - os.path.getmtime(path) > CLAIM_SECONDS:
                    os.remove(path)
            except OSError:
                pass
        name = hashlib.sha1(key.encode("utf-8")).hexdigest()
        os.close(os.open(os.path.join(claims, name), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False
    except OSError:
        return True  # can't tell: better twice than never


def picked_up(note: Optional[str], wait: float = 1.5) -> bool:
    """Whether the VS Code extension took the note from the inbox (it deletes
    each note it opens). A note still there after a moment means nothing is
    watching, so the note is withdrawn and the caller shows the page itself."""
    if not note:
        return False
    deadline = time.time() + wait
    while time.time() < deadline:
        if not os.path.exists(note):
            return True
        time.sleep(0.1)
    try:
        os.remove(note)
    except OSError:
        return not os.path.exists(note)
    return False


# --------------------------------------------------------------------------
# Asking the user whether to see the simulation
# --------------------------------------------------------------------------
# With GIT_SIM_HOOK_OPEN=ask. An agent's approval prompt offers approve or
# deny, nothing else, so the question "see it first?" is asked in a small
# dialog of the system's own, just before the prompt appears. It gives up
# after DIALOG_SECONDS as if the answer were no.

DIALOG_SECONDS = 60
DIALOG_TITLE = "git-sim preflight"


def can_show_dialog() -> bool:
    """A desktop to show a dialog on: not CI, not over SSH, and on Linux a
    display with zenity or kdialog."""
    import shutil

    if os.environ.get("CI") or os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    if sys.platform == "win32":
        return True
    if sys.platform == "darwin":
        return bool(shutil.which("osascript"))
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    return bool(shutil.which("zenity") or shutil.which("kdialog"))


def dialog_text(report: PreflightReport, agent: str) -> str:
    label = AGENTS.get(agent, {}).get("label", "Your agent")
    lines = [f"{label} wants to run:", f"    {report.command}", ""]
    lines.append(f"{report.risk.value.upper()}: {_summary(report)}".strip())
    losses = _losses(report)
    if losses:
        lines.append(losses)
    lines += ["", "Simulate it visually before you approve or deny it?"]
    return _plural("\n".join(lines))


def ask_to_simulate(text: str, seconds: int = DIALOG_SECONDS) -> bool:
    """Show the question; True when the user asks to see the simulation."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            # Yes/No, question icon, on top of other windows, brought forward.
            flags = 0x4 | 0x20 | 0x40000 | 0x10000
            box = getattr(user32, "MessageBoxTimeoutW", None)
            if box is not None:
                box.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                wintypes.UINT, wintypes.WORD, wintypes.DWORD]  # fmt: skip
                answer = box(None, text, DIALOG_TITLE, flags, 0, seconds * 1000)
            else:
                answer = user32.MessageBoxW(None, text, DIALOG_TITLE, flags)
            return answer == 6  # IDYES
        if sys.platform == "darwin":
            quote = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'  # noqa: E731
            script = (
                f"display dialog {quote(text)} with title {quote(DIALOG_TITLE)} "
                'buttons {"Skip", "Simulate"} default button "Simulate" '
                f'cancel button "Skip" giving up after {seconds} with icon caution'
            )
            done = subprocess.run(["osascript", "-e", script], capture_output=True,
                                  text=True, timeout=seconds + 5)  # fmt: skip
            return done.returncode == 0 and "button returned:Simulate" in done.stdout
        import shutil

        if shutil.which("zenity"):
            args = ["zenity", "--question", "--no-markup", f"--title={DIALOG_TITLE}",
                    f"--text={text}", "--ok-label=Simulate", "--cancel-label=Skip",
                    f"--timeout={seconds}"]  # fmt: skip
        else:
            args = ["kdialog", "--title", DIALOG_TITLE, "--yes-label", "Simulate",
                    "--no-label", "Skip", "--yesno", text]  # fmt: skip
        return subprocess.run(args, capture_output=True, timeout=seconds + 5).returncode == 0
    except Exception:
        return False


def safe_note(reports: List[PreflightReport]) -> str:
    """One line per analysed command that stayed below the threshold."""
    lines = []
    for report in reports:
        line = _headline(report)
        if report.summary:
            line += f" ({_summary(report).rstrip('.')})"
        lines.append(line)
    return _plural("\n".join(lines))


def brief(report: PreflightReport) -> List[str]:
    """What the command does and what it costs, in a few short lines."""
    lines = [_headline(report)]
    if report.location:
        lines.append(report.location)
    if report.summary:
        lines.append(_summary(report))
    losses = _losses(report)
    if losses:
        lines.append(losses)
    lines += _warnings(report)
    if report.recovery:
        undo = "; ".join(report.recovery)
        lines.append(undo if undo.lower().startswith("undo") else "Undo: " + undo)
    return lines


def format_reason(reports: List[PreflightReport]) -> str:
    """The text of the approval prompt: a few lines per flagged command (the
    plain-text graph too, with GIT_SIM_HOOK_TEXT=1). The simulation opens on
    its own, so the prompt doesn't point at it."""
    blocks = []
    for report in reports:
        lines = brief(report)
        if report.text_graph:
            lines += ["", report.text_graph]
        blocks.append("\n".join(lines))
    return _plural("\n\n".join(blocks).strip())


# --------------------------------------------------------------------------
# Agent dialects
# --------------------------------------------------------------------------


def _parse_args(value):
    """Copilot sends toolArgs as an object or a JSON string."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value or {}


def parse_hook_input(
    hook_input: dict, agent: Optional[str] = None
) -> Optional[Tuple[str, str, str]]:
    """Return (agent, shell command, cwd), or None when the payload is not a
    shell-command event we should look at.

    The agent comes from ``agent`` (``--agent`` / GIT_SIM_HOOK_AGENT) when
    given; otherwise it is inferred from the payload shape.
    """
    event = hook_input.get("hook_event_name") or hook_input.get("hookEventName") or ""
    cwd = hook_input.get("cwd") or os.getcwd()

    # Cursor: the command sits at the top level.
    if event == "beforeShellExecution" or (
        "command" in hook_input
        and "tool_name" not in hook_input
        and "toolName" not in hook_input
    ):
        command = hook_input.get("command") or ""
        return (agent or "cursor", command, cwd) if command else None

    # Copilot CLI (camelCase form).
    if "toolName" in hook_input or "toolArgs" in hook_input:
        tool = str(hook_input.get("toolName") or "").lower()
        if tool not in SHELL_TOOLS:
            return None
        args = _parse_args(hook_input.get("toolArgs"))
        command = args.get("command") or args.get("cmd") or ""
        return (agent or "copilot", command, cwd) if command else None

    # Claude Code, Codex, Gemini and Copilot's VS Code-compatible form all use
    # tool_name + tool_input.
    tool = str(hook_input.get("tool_name") or "")
    if tool.lower() not in SHELL_TOOLS:
        return None
    tool_input = _parse_args(hook_input.get("tool_input"))
    command = tool_input.get("command") or ""
    if not command:
        return None
    if agent:
        return agent, command, cwd
    if event == "BeforeTool" or tool == "run_shell_command":
        return "gemini", command, cwd
    if tool.lower() in VSCODE_TOOLS:
        return "vscode", command, cwd
    return "claude", command, cwd


def _decide(agent: str, mode: str) -> str:
    """Map the configured mode onto what this agent's protocol can express."""
    if mode == "warn":
        return "allow"
    if mode == "deny":
        return "deny"
    return "ask" if AGENTS.get(agent, AGENTS["claude"])["asks"] else "deny"


def _cannot_ask_note(agent: str) -> str:
    label = AGENTS.get(agent, {}).get("label", agent)
    return (
        f"\n\n{label} hooks cannot prompt the user, so this command was denied "
        "pending confirmation. Show the facts above to the user. If they approve, "
        "re-run the exact command prefixed with GIT_SIM_APPROVE=1 "
        "(PowerShell: $env:GIT_SIM_APPROVE=1; <command>) and it will run."
    )


def build_output(agent: str, decision: str, reason: str) -> dict:
    """The decision in the agent's own hook output schema."""
    if agent == "cursor":
        return {"permission": decision, "user_message": reason, "agent_message": reason}
    if agent in ("copilot", "vscode"):
        # Copilot CLI reads the decision at the top level; VS Code's agent hooks
        # read Copilot's hook files but take it under hookSpecificOutput. One
        # answer carries both, so the shared hook file works in either.
        output = {
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            },
        }
        if decision == "allow":
            output["systemMessage"] = reason  # VS Code shows this beside the call
        return output
    if agent == "gemini":
        output = {"decision": decision, "systemMessage": reason}
        if decision != "allow":
            output["reason"] = reason
        return output
    # Claude Code and Codex share the hookSpecificOutput schema.
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    if decision == "allow":
        output["systemMessage"] = reason
    return output


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------


RENDER_SECONDS = 45  # the hook itself has 120 seconds (see install.py)


def _simulate(report: PreflightReport, cwd: str, agent: str, vscode: bool, mode: str) -> Optional[str]:
    """Render the interactive page of the flagged command and show it: in a
    VS Code tab when the git-sim extension is watching, otherwise in the
    browser (after asking, with GIT_SIM_HOOK_OPEN=ask). Returns where it was
    shown: "vscode", "browser" or None."""
    from git_sim.simulate import render_simulation

    # Rendered first (a second or two), so the question is only asked about a
    # simulation that exists.
    page = render_simulation(report.command, cwd, img_format="html",
                             timeout=RENDER_SECONDS).get("image_path")  # fmt: skip
    if not page:
        return None
    if vscode and picked_up(post_to_inbox(page, report, cwd)):
        # The git-sim extension opened it in an editor tab. If it isn't
        # watching, carry on as anywhere else.
        return "vscode"
    if os.environ.get("GIT_SIM_HOOK_OPEN", "always").lower() == "ask":
        if not (mode == "ask" and can_show_dialog() and ask_to_simulate(dialog_text(report, agent))):
            return None
    show_page(page)
    return "browser"


def _open_url(url: str) -> None:
    from git_sim.render.scene import open_url

    open_url(url)


def show_page(page: str) -> None:
    """Open the saved page in the browser: in the git-sim viewer at
    initialcommit.com (default), or the file itself with
    GIT_SIM_HOOK_OPEN_IN=local (or git-sim's own git_sim_open_in=local). The
    viewer link has no query string; the graph, command and theme ride in its
    #fragment, which the browser never sends to the server."""
    from git_sim.settings import settings

    where = (os.environ.get("GIT_SIM_HOOK_OPEN_IN") or getattr(settings.open_in, "value", "hosted")).lower()
    if where != "local":
        from git_sim.render.html import hosted_link_for_page

        url = hosted_link_for_page(page, settings.viewer_url)
        if url:
            try:
                _open_url(url)
                return
            except Exception:
                pass
    _open_file(page)


def run_hook(hook_input: dict, agent: Optional[str] = None) -> Optional[dict]:
    """Core hook logic. Returns the hook output dict, or None to stay silent."""
    agent = agent or os.environ.get("GIT_SIM_HOOK_AGENT") or None
    parsed = parse_hook_input(hook_input, agent)
    if parsed is None:
        return None
    agent, command, cwd = parsed

    if not (GIT_WORD.search(command) and RISKY_WORDS.search(command)):
        return None
    if APPROVAL_OVERRIDE.search(command):
        return None  # the user already approved this exact command

    vscode = in_vscode(agent, hook_input)
    threshold = os.environ.get("GIT_SIM_HOOK_ASK_ON", "caution")
    render_text = os.environ.get("GIT_SIM_HOOK_TEXT", "0") == "1"
    analysed, flagged = [], []
    for git_command, where in located_git_commands(command, cwd):
        if where is None:
            continue  # somewhere the hook can't see; judging cwd would mislead
        report = analyze(git_command, where, render_text=render_text)
        if report.error is not None:
            continue
        if os.path.normcase(os.path.normpath(where)) != os.path.normcase(os.path.normpath(cwd)):
            report.elsewhere = os.path.basename(os.path.normpath(where)) or where
        analysed.append(report)
        if _risk_triggers(report.risk, threshold):
            flagged.append(report)
            if len(flagged) == 1:
                cwd = where  # the repository the render and the note are about

    if not flagged:
        # Below the threshold: silent by default, or an "allow" that still names
        # the level, so the user sees a verdict on every git command (VS Code).
        report_safe = os.environ.get("GIT_SIM_HOOK_REPORT_SAFE", "1" if vscode else "0")
        if analysed and report_safe != "0":
            return build_output(agent, "allow", safe_note(analysed))
        return None

    mode = os.environ.get("GIT_SIM_HOOK_MODE", "ask").lower()
    decision = _decide(agent, mode)
    show = os.environ.get("GIT_SIM_HOOK_RENDER", "1") != "0" and os.environ.get(
        "GIT_SIM_HOOK_OPEN", "always"
    ).lower() not in ("0", "never", "no", "false")
    if show and claim_simulation(hook_input, command, cwd):
        _simulate(flagged[0], cwd, agent, vscode, mode)
    reason = format_reason(flagged)
    if decision == "deny" and mode == "ask":
        reason += _cannot_ask_note(agent)
    return build_output(agent, decision, reason)


def _agent_from_argv(argv: List[str]) -> Optional[str]:
    for i, arg in enumerate(argv):
        if arg == "--agent" and i + 1 < len(argv):
            return argv[i + 1].lower()
        if arg.startswith("--agent="):
            return arg.split("=", 1)[1].lower()
    return None


def main() -> None:
    try:
        agent = _agent_from_argv(sys.argv[1:])
        # lstrip the BOM some Windows shells prepend when piping.
        hook_input = json.loads(sys.stdin.read().lstrip(chr(0xFEFF)))
        output = run_hook(hook_input, agent)
    except Exception:
        # Fail open: never break the agent's tool call because of the hook.
        return
    if output is not None:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
