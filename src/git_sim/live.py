"""``git-sim live``: follow a repository and keep an animated graph of it.

The command watches one repository and redraws it after every change,
whatever caused it (a command in a terminal, a Source Control button, an AI
agent, another program). Each change is played as a before / after animation
the way a simulation is: the drawing from before the change and the one from
after it are merged (git_sim.render.merge) into one graph the interactive
viewer can scrub. Every change is kept, so the page can step back through
the session or replay it end to end, and each one is also saved as a
standalone page under the media folder.

Two front ends share the engine:

- a browser: ``git-sim live`` serves the live page on localhost and pushes
  changes to it (server-sent events);
- VS Code: ``git-sim live --json`` prints one JSON line per change (with the
  paths of the graph and page it wrote) for the extension to feed its own
  copy of the page.

What changed is read from git itself, not from the file system: the refs,
HEAD, the status of the working tree and index, and the stash list are
compared between polls, so a poll never fires on the noise inside .git, and
the HEAD reflog names the command that ran (commit, reset, checkout, merge,
rebase, ...). Changes that leave no reflog entry (a branch or tag created or
deleted, files staged or edited, a stash) are described from the diff of
those readings.
"""

import hashlib
import http.server
import json
import os
import queue
import re
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import typer

from git_sim.settings import settings

POLL_SECONDS = 1.0
SETTLE_SECONDS = 0.6  # a change must hold still this long before it is drawn
SETTLE_LIMIT_SECONDS = 6.0  # ...but a long rebase is drawn at least this often
HISTORY_LIMIT = 300
REFLOG_DEPTH = 40


# ------------------------------------------------------------------ reading
def _git(repo: str, *args: str, ok_codes=(0,)) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode not in ok_codes:
        return ""
    return proc.stdout


@dataclass
class RepoState:
    """What the repository looks like from the outside, at one moment."""

    head: str = ""  # "refs/heads/main", or "" when detached / unborn
    head_sha: str = ""
    refs: Dict[str, str] = field(default_factory=dict)  # refname -> sha
    status: Tuple[str, ...] = ()  # git status --porcelain lines
    stash: Tuple[str, ...] = ()  # stash shas, newest first
    reflog: Tuple[str, ...] = ()  # HEAD reflog subjects, newest first

    @property
    def signature(self) -> str:
        h = hashlib.sha1()
        h.update(self.head.encode())
        h.update(self.head_sha.encode())
        for name in sorted(self.refs):
            h.update(f"{name}={self.refs[name]}".encode())
        for line in sorted(self.status):
            h.update(line.encode("utf-8", "replace"))
        h.update("|".join(self.stash).encode())
        return h.hexdigest()

    def heads(self) -> Dict[str, str]:
        return {
            n[len("refs/heads/") :]: s
            for n, s in self.refs.items()
            if n.startswith("refs/heads/")
        }

    def tags(self) -> Dict[str, str]:
        return {
            n[len("refs/tags/") :]: s
            for n, s in self.refs.items()
            if n.startswith("refs/tags/")
        }

    def remotes(self) -> Dict[str, str]:
        return {
            n[len("refs/remotes/") :]: s
            for n, s in self.refs.items()
            if n.startswith("refs/remotes/")
        }

    def entries(self) -> Dict[str, Tuple[str, str]]:
        """path -> (index status, worktree status) from the porcelain lines."""
        out = {}
        for line in self.status:
            if len(line) < 4:
                continue
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            out[path] = (line[0], line[1])
        return out


def read_state(repo: str) -> RepoState:
    state = RepoState()
    state.head = _git(repo, "symbolic-ref", "-q", "HEAD", ok_codes=(0, 1)).strip()
    state.head_sha = _git(
        repo, "rev-parse", "-q", "--verify", "HEAD", ok_codes=(0, 1)
    ).strip()
    refs = {}
    for line in _git(
        repo, "for-each-ref", "--format=%(refname)%00%(objectname)"
    ).splitlines():
        if "\x00" in line:
            name, sha = line.split("\x00", 1)
            refs[name] = sha
    state.refs = refs
    state.status = tuple(
        line
        for line in _git(repo, "status", "--porcelain").splitlines()
        if line.strip()
    )
    state.stash = tuple(_git(repo, "stash", "list", "--format=%H").split())
    state.reflog = tuple(
        _git(
            repo,
            "reflog",
            "show",
            f"-n{REFLOG_DEPTH}",
            "--format=%gs",
            "HEAD",
            ok_codes=(0, 128),
        ).splitlines()
    )
    return state


# --------------------------------------------------------------- describing
def new_reflog_entries(before: Tuple[str, ...], after: Tuple[str, ...]) -> List[str]:
    """The reflog subjects added since ``before``, newest first."""
    if not after or after == before:
        return []
    for n in range(0, len(after)):
        if after[n:] == before[: len(after) - n]:
            return list(after[:n])
    return [after[0]]


REFLOG_RULES = (
    (re.compile(r"^commit \(amend\)"), lambda m: "git commit --amend"),
    (re.compile(r"^commit"), lambda m: "git commit"),
    (re.compile(r"^reset: moving to (.+)$"), lambda m: f"git reset {m.group(1)}"),
    (
        re.compile(r"^checkout: moving from \S+ to (.+)$"),
        lambda m: f"git checkout {m.group(1)}",
    ),
    (re.compile(r"^merge (.+?):"), lambda m: f"git merge {m.group(1)}"),
    (re.compile(r"^rebase"), lambda m: "git rebase"),
    (re.compile(r"^cherry-pick"), lambda m: "git cherry-pick"),
    (re.compile(r"^revert"), lambda m: "git revert"),
    (re.compile(r"^pull"), lambda m: "git pull"),
    (re.compile(r"^am:"), lambda m: "git am"),
    (re.compile(r"^clone"), lambda m: "git clone"),
    (re.compile(r"^Branch: renamed"), lambda m: "git branch -m"),
    (re.compile(r"^(\S+?):"), lambda m: f"git {m.group(1)}"),
)


def command_from_reflog(subject: str) -> str:
    for pattern, make in REFLOG_RULES:
        m = pattern.match(subject)
        if m:
            return make(m)
    return "git " + subject.split()[0] if subject.split() else "git"


def _names(paths: List[str], limit: int = 2) -> str:
    shown = [os.path.basename(p.rstrip("/")) or p for p in paths[:limit]]
    more = len(paths) - len(shown)
    return " ".join(shown) + (f" +{more}" if more > 0 else "")


def describe_change(before: RepoState, after: RepoState) -> Tuple[str, str]:
    """(label, detail): the command that most likely produced ``after`` from
    ``before``, short enough for a title, and a longer line for a tooltip."""
    entries = new_reflog_entries(before.reflog, after.reflog)
    if entries:
        if any(e.startswith("rebase") for e in entries):
            label = "git rebase"
        else:
            label = command_from_reflog(entries[0])
        # checkout -b: the branch moved to did not exist before
        m = re.match(r"^git checkout (.+)$", label)
        if m and m.group(1) in after.heads() and m.group(1) not in before.heads():
            label = f"git checkout -b {m.group(1)}"
        return label, entries[0]

    if len(after.stash) > len(before.stash):
        return "git stash", "stashed the working directory and index"
    if len(after.stash) < len(before.stash):
        gained = len(after.status) > len(before.status)
        return ("git stash pop" if gained else "git stash drop"), "stash list shrank"

    bh, ah = before.heads(), after.heads()
    added = sorted(set(ah) - set(bh))
    gone = sorted(set(bh) - set(ah))
    if added and gone and len(added) == len(gone) == 1 and bh[gone[0]] == ah[added[0]]:
        return f"git branch -m {added[0]}", f"renamed {gone[0]} to {added[0]}"
    if added:
        return (
            f"git branch {added[0]}"
            + (f" +{len(added) - 1}" if len(added) > 1 else ""),
            f"created {', '.join(added)}",
        )
    if gone:
        return (
            f"git branch -d {gone[0]}"
            + (f" +{len(gone) - 1}" if len(gone) > 1 else ""),
            f"deleted {', '.join(gone)}",
        )
    moved = sorted(n for n in ah if n in bh and ah[n] != bh[n])
    if moved:
        return f"git branch -f {moved[0]}", f"{', '.join(moved)} now at another commit"

    bt, at = before.tags(), after.tags()
    added = sorted(set(at) - set(bt))
    gone = sorted(set(bt) - set(at))
    if added:
        return f"git tag {added[0]}", f"tagged {', '.join(added)}"
    if gone:
        return f"git tag -d {gone[0]}", f"deleted tag {', '.join(gone)}"
    if before.remotes() != after.remotes():
        return "git fetch", "remote-tracking branches changed"

    be, ae = before.entries(), after.entries()
    staged_now = [
        p
        for p, (x, y) in ae.items()
        if x not in " ?!" and be.get(p, (" ", " "))[0] in " ?!"
    ]
    if staged_now:
        kinds = {ae[p][0] for p in staged_now}
        if kinds == {"D"}:
            return (
                f"git rm {_names(staged_now)}",
                "removed from the index: " + ", ".join(staged_now),
            )
        if kinds == {"R"}:
            return f"git mv {_names(staged_now)}", "renamed in the index: " + ", ".join(
                staged_now
            )
        return f"git add {_names(staged_now)}", "staged: " + ", ".join(staged_now)
    unstaged = [
        p
        for p, (x, y) in be.items()
        if x not in " ?!" and ae.get(p, (" ", " "))[0] in " ?!"
    ]
    if unstaged:
        return f"git restore --staged {_names(unstaged)}", "unstaged: " + ", ".join(
            unstaged
        )
    untracked_now = [p for p, (x, y) in ae.items() if x == "?" and p not in be]
    if untracked_now:
        return f"new file {_names(untracked_now)}", "untracked: " + ", ".join(
            untracked_now
        )
    edited_now = [
        p for p, (x, y) in ae.items() if y == "M" and be.get(p, (" ", " "))[1] != "M"
    ]
    if edited_now:
        return (
            f"edited {_names(edited_now)}",
            "modified in the working directory: " + ", ".join(edited_now),
        )
    deleted_now = [
        p for p, (x, y) in ae.items() if y == "D" and be.get(p, (" ", " "))[1] != "D"
    ]
    if deleted_now:
        return (
            f"deleted {_names(deleted_now)}",
            "deleted from the working directory: " + ", ".join(deleted_now),
        )
    reverted = [p for p in be if p not in ae]
    if reverted:
        return f"git restore {_names(reverted)}", "clean again: " + ", ".join(reverted)
    if before.head != after.head or before.head_sha != after.head_sha:
        return "git checkout", "HEAD moved"
    return "repository changed", "something changed that has no name here"


# ---------------------------------------------------------------- rendering
def _repo_root(path: str) -> Optional[str]:
    out = _git(path, "rev-parse", "--show-toplevel").strip()
    return os.path.normpath(out) if out else None


def render_snapshot(label: str, zones: bool = True) -> str:
    """Draw the repository in the current directory as an SVG titled ``label``:
    the commit graph (all branches when --all was given) and, with ``zones``,
    the untracked / modified / staged table beneath it."""
    from git_sim.live_scene import LiveScene
    from git_sim.render.constants import DEFAULT_PIXEL_HEIGHT, DEFAULT_PIXEL_WIDTH
    from git_sim.render.html import FONT_STACK
    from git_sim.theme import theme_for

    theme = theme_for(settings.light_mode)
    scene = LiveScene(label=label, zones=zones)
    try:
        scene.render()
        return scene.render_svg(
            DEFAULT_PIXEL_WIDTH,
            DEFAULT_PIXEL_HEIGHT,
            background=theme.bg,
            font_stack=FONT_STACK,
            extra_mobjects=scene.removed_mobjects,
        )
    finally:
        try:
            scene.repo.close()
        except Exception:
            pass


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "change"


@dataclass
class Snapshot:
    index: int
    label: str
    detail: str
    time: float
    svg_path: str  # the graph the page plays (merged with the previous state)
    page_path: str  # the same, as a standalone interactive page
    raw_svg: str = field(repr=False, default="")  # this state alone, for the next merge

    def to_json(self) -> dict:
        return {
            "index": self.index,
            "label": self.label,
            "detail": self.detail,
            "time": self.time,
            "svg": self.svg_path,
            "page": self.page_path,
        }


class LiveSession:
    """Watches one repository; renders and records each change."""

    def __init__(
        self, repo: str, out_dir: str, zones: bool = True, poll: float = POLL_SECONDS
    ):
        self.repo = repo
        self.name = os.path.basename(repo)
        self.out_dir = out_dir
        self.zones = zones
        self.poll = poll
        self.snapshots: List[Snapshot] = []
        self.listeners: List[Callable[[Snapshot], None]] = []
        self.state: Optional[RepoState] = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.errors: List[str] = []
        # Presented by the page on every request to the local server.
        self.key = secrets.token_urlsafe(18)
        # Asked before each poll; returning True ends the session (the
        # editor that started us went away).
        self.before_poll: Optional[Callable[[], bool]] = None

    # -- history ----------------------------------------------------------------
    def history(self) -> List[dict]:
        with self.lock:
            return [s.to_json() for s in self.snapshots]

    def get(self, index: int) -> Optional[Snapshot]:
        with self.lock:
            for s in self.snapshots:
                if s.index == index:
                    return s
        return None

    def subscribe(self, fn: Callable[[Snapshot], None]) -> None:
        self.listeners.append(fn)

    # -- rendering --------------------------------------------------------------
    def _draw(self, label: str, detail: str, previous: Optional[Snapshot]) -> Snapshot:
        from git_sim.render.html import build_html
        from git_sim.render.merge import merge_svgs
        from git_sim.theme import theme_for

        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            raw = render_snapshot(label, self.zones)
        finally:
            os.chdir(cwd)
        shown = merge_svgs(previous.raw_svg, raw) if previous else raw
        index = (self.snapshots[-1].index + 1) if self.snapshots else 0
        stem = f"{index:03d}-{_slug(label)}"
        os.makedirs(self.out_dir, exist_ok=True)
        svg_path = os.path.join(self.out_dir, stem + ".svg")
        page_path = os.path.join(self.out_dir, stem + ".html")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(shown)
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(
                build_html(
                    shown,
                    title=label,
                    theme=theme_for(settings.light_mode),
                    viewer_url=settings.viewer_url,
                )
            )
        return Snapshot(index, label, detail, time.time(), svg_path, page_path, raw)

    def _record(self, snap: Snapshot) -> None:
        with self.lock:
            self.snapshots.append(snap)
            if len(self.snapshots) > HISTORY_LIMIT:
                dropped = self.snapshots.pop(0)
                for p in (dropped.svg_path, dropped.page_path):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            # only the latest raw drawing is needed for the next merge
            for s in self.snapshots[:-1]:
                s.raw_svg = ""
        for fn in list(self.listeners):
            try:
                fn(snap)
            except Exception:
                pass

    def start(self) -> Snapshot:
        """Read the repository and draw its current state (change 0)."""
        self.state = read_state(self.repo)
        branch = (
            self.state.head.replace("refs/heads/", "")
            if self.state.head
            else "detached HEAD"
        )
        snap = self._draw(
            f"git-sim live: {self.name}", f"watching {self.repo} on {branch}", None
        )
        self._record(snap)
        return snap

    def _debug(self, text: str) -> None:
        if os.environ.get("GIT_SIM_LIVE_DEBUG"):
            try:
                sys.stderr.write(f"git-sim live [debug]: {text}\n")
                sys.stderr.flush()
            except Exception:
                pass

    def check(self) -> Optional[Snapshot]:
        """One poll: if the repository changed and has held still, draw it."""
        current = read_state(self.repo)
        if self.state is not None and current.signature == self.state.signature:
            return None
        self._debug(
            f"change seen (head {current.head_sha[:7]}), waiting for it to settle"
        )
        # Let a multi-step command (a rebase, a pull) finish before drawing.
        started = time.time()
        while not self.stop.is_set():
            time.sleep(SETTLE_SECONDS)
            again = read_state(self.repo)
            if (
                again.signature == current.signature
                or time.time() - started > SETTLE_LIMIT_SECONDS
            ):
                current = again
                break
            current = again
        if self.state is not None and current.signature == self.state.signature:
            return None
        previous_state, self.state = self.state, current
        label, detail = (
            describe_change(previous_state, current)
            if previous_state
            else ("git-sim live", "")
        )
        try:
            snap = self._draw(
                label, detail, self.snapshots[-1] if self.snapshots else None
            )
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # a failed drawing must not end the session
            # (BaseException: a scene that gives up calls sys.exit)
            self._error(f"{label}: could not draw the repository ({exc!r})")
            return None
        self._record(snap)
        return snap

    def _error(self, text: str) -> None:
        self.errors.append(text)
        try:
            sys.stderr.write(f"git-sim live: {text}\n")
            sys.stderr.flush()
        except Exception:
            pass

    def run(self) -> None:
        while not self.stop.is_set():
            if self.before_poll is not None and self.before_poll():
                self.stop.set()
                break
            try:
                self.check()
            except Exception as exc:
                self._error(repr(exc))
            self.stop.wait(self.poll)


# ------------------------------------------------------------------- server
def _origin_of(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


class LiveHandler(http.server.BaseHTTPRequestHandler):
    """The local server: the page, the list of changes, each graph and page,
    and the event stream.

    The page hosted on initialcommit.com reads from here too, so the data
    routes answer cross-origin requests from that one origin (and carry the
    header browsers want before letting a website reach the local network).
    Every data route requires the session key, so a web page you happen to
    visit cannot read your repository graph off localhost; only the page
    git-sim opened (local or hosted) knows it."""

    server_version = "git-sim-live"
    session: LiveSession = None  # set on the server

    def log_message(self, fmt, *args):  # quiet
        pass

    def _allowed_origin(self) -> str:
        origin = self.headers.get("Origin", "")
        if not origin:
            return ""
        own = f"http://{self.headers.get('Host', '')}"
        if origin in (own, _origin_of(settings.viewer_url)):
            return origin
        return ""

    def _cors(self) -> None:
        origin = self._allowed_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-Git-Sim-Key")
            self.send_header("Access-Control-Max-Age", "600")

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self, query: str) -> bool:
        key = self.server.session.key
        given = urllib.parse.parse_qs(query).get("k", [""])[0] or self.headers.get(
            "X-Git-Sim-Key", ""
        )
        return bool(key) and secrets.compare_digest(given, key)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        session = self.server.session
        split = urllib.parse.urlsplit(self.path)
        path = split.path
        if path == "/":
            from git_sim.render.live_html import build_live_html
            from git_sim.theme import theme_for

            # Only this machine's browser gets the page (and the key in it):
            # a cross-origin fetch of it is refused.
            if self.headers.get("Origin") and not self._allowed_origin():
                return self._send(b"forbidden", "text/plain", 403)
            page = build_live_html(
                theme=theme_for(settings.light_mode),
                repo=session.name,
                viewer_url=settings.viewer_url,
                key=session.key,
            )
            return self._send(page.encode("utf-8"), "text/html; charset=utf-8")
        if not self._authorised(split.query):
            return self._send(
                b"forbidden: session key missing or wrong", "text/plain", 403
            )
        if path == "/history":
            return self._send(
                json.dumps(session.history()).encode("utf-8"), "application/json"
            )
        m = re.match(r"^/(svg|page)/(\d+)$", path)
        if m:
            snap = session.get(int(m.group(2)))
            if snap is None:
                return self._send(b"no such change", "text/plain", 404)
            file = snap.svg_path if m.group(1) == "svg" else snap.page_path
            try:
                with open(file, "rb") as f:
                    body = f.read()
            except OSError:
                return self._send(b"gone", "text/plain", 410)
            kind = (
                "image/svg+xml" if m.group(1) == "svg" else "text/html; charset=utf-8"
            )
            return self._send(body, kind)
        if path == "/events":
            return self._events(session)
        self._send(b"not found", "text/plain", 404)

    def _events(self, session: LiveSession) -> None:
        q: "queue.Queue[Snapshot]" = queue.Queue()
        session.subscribe(q.put)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(b"retry: 1500\n\n")
            self.wfile.flush()
            while not session.stop.is_set():
                try:
                    snap = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                data = json.dumps({"type": "snapshot", "item": snap.to_json()})
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            try:
                session.listeners.remove(q.put)
            except ValueError:
                pass


class LiveServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, session: LiveSession):
        super().__init__(address, LiveHandler)
        self.session = session


# ------------------------------------------------------------------ command
def _default_setting(ctx: typer.Context, name: str, value) -> None:
    """Give a global option a live-mode default when it was not on the command line."""
    parent = ctx.parent
    try:
        from click.core import ParameterSource

        chosen = parent is not None and parent.get_parameter_source(name) in (
            ParameterSource.COMMANDLINE,
            ParameterSource.ENVIRONMENT,
        )
    except Exception:
        chosen = False
    if not chosen:
        setattr(settings, name, value)


def _stdin_is_pipe() -> bool:
    try:
        return stat.S_ISFIFO(os.fstat(sys.stdin.fileno()).st_mode)
    except Exception:
        return False


def _parent_gone() -> bool:
    """Whether the pipe on stdin has been closed by whoever started us. Polled
    between checks rather than read in a thread: a blocking read on a pipe an
    editor created (overlapped I/O on Windows) can stall the whole process."""
    if not _stdin_is_pipe():  # a terminal, or /dev/null: nothing to watch
        return False
    try:
        if sys.platform == "win32":
            import _winapi
            import msvcrt

            _winapi.PeekNamedPipe(msvcrt.get_osfhandle(sys.stdin.fileno()), 0)
            return False
        import select

        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return False
        return os.read(sys.stdin.fileno(), 1) == b""
    except OSError:
        return True
    except Exception:
        return False


def _say(*parts) -> None:
    if not settings.quiet:
        typer.echo(" ".join(str(p) for p in parts), err=True)


def live(
    ctx: typer.Context,
    port: int = typer.Option(
        0, "--port", help="Port for the live page (default: any free port)."
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="No server: print one JSON line per change to stdout (for editors).",
    ),
    once: bool = typer.Option(
        False, "--once", help="Draw the current state, print it, and exit."
    ),
    print_page: bool = typer.Option(
        False,
        "--print-page",
        help="Print the live page's HTML and exit (for editors embedding it).",
    ),
    zones: bool = typer.Option(
        True,
        "--zones/--no-zones",
        help="Draw the untracked / modified / staged table under the graph.",
    ),
    interval: float = typer.Option(
        POLL_SECONDS, "--interval", help="Seconds between checks of the repository."
    ),
    repo: str = typer.Option(".", "--repo", "-C", help="The repository to watch."),
):
    """Follow the repository as it changes: an animated graph that plays every
    commit, branch, checkout, reset, rebase or staged file as it happens, in
    the browser (default) or for an editor (--json). Changes are kept so the
    page can step back through the session and replay it. Global options
    (--all, -n, --light-mode, --media-dir) apply to every drawing.
    """
    from git_sim.theme import theme_for

    if print_page:
        from git_sim.render.live_html import build_live_html

        root = _repo_root(os.path.abspath(repo))
        page = build_live_html(
            theme=theme_for(settings.light_mode),
            repo=os.path.basename(root) if root else "",
            viewer_url=settings.viewer_url,
        )
        # As UTF-8 bytes: the page has characters a Windows console pipe's
        # default code page cannot write.
        sys.stdout.buffer.write(page.encode("utf-8"))
        sys.stdout.flush()
        return

    if shutil.which("git") is None:
        typer.echo("git-sim error: git is not on the PATH", err=True)
        raise typer.Exit(code=1)
    root = _repo_root(os.path.abspath(repo))
    if not root:
        typer.echo(
            f"git-sim error: no Git repository at {os.path.abspath(repo)}", err=True
        )
        raise typer.Exit(code=1)

    # Branches are the point of a live graph: unless the user chose, show up
    # to three labels on a commit instead of the one a single simulation shows.
    _default_setting(ctx, "max_branches_per_commit", 3)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    media = os.path.expanduser(str(settings.media_dir))
    # The CLI callback appended the repository name of the *current* folder;
    # live may watch another one (--repo), so name the folder after it.
    if os.path.basename(media) != os.path.basename(root):
        media = os.path.join(os.path.dirname(media), os.path.basename(root))
    out_dir = os.path.join(media, "live", stamp)
    session = LiveSession(root, out_dir, zones=zones, poll=max(0.2, interval))

    def emit(snap: Snapshot) -> None:
        line = json.dumps({"event": "snapshot", **snap.to_json()})
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except (OSError, ValueError):  # the editor that spawned us is gone
            session.stop.set()

    if as_json or once:
        if as_json:
            sys.stdout.write(
                json.dumps(
                    {"event": "start", "repo": root, "dir": out_dir, "zones": zones}
                )
                + "\n"
            )
            sys.stdout.flush()
        session.subscribe(emit)
        session.start()
        if once:
            return
        # An editor holds our stdin open; when it closes, so do we, so a
        # watcher never outlives the window that started it.
        session.before_poll = _parent_gone
        try:
            session.run()
        except (KeyboardInterrupt, BrokenPipeError):
            pass
        return

    # Browser mode: draw the current state, serve, watch.
    _say(f"git-sim live: drawing {root} ...")
    session.start()
    server = LiveServer(("127.0.0.1", port), session)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    local_url = f"{base}/#k={session.key}"
    watcher = threading.Thread(
        target=session.run, name="git-sim-live-watch", daemon=True
    )
    watcher.start()
    # As with simulations, the page opens in the viewer on initialcommit.com
    # unless --open-in local: the site serves only the page, and the graphs
    # come from this server, whose address and key ride in the #fragment
    # that browsers never send.
    from git_sim.enums import OpenIn
    from git_sim.render.live_html import hosted_live_url

    hosted = settings.open_in == OpenIn.HOSTED
    url = (
        hosted_live_url(settings.viewer_url, base, session.key) if hosted else local_url
    )
    _say(f"git-sim live: watching {root}")
    _say(f"  {url}")
    if hosted:
        _say(f"  (the same page served locally: {local_url})")
    _say(f"  changes are saved under {out_dir}")
    _say("  Ctrl+C to stop")
    if settings.auto_open:
        try:
            from git_sim.render.scene import open_url

            open_url(url)
        except Exception:
            pass
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        session.stop.set()
        server.server_close()
        _say(
            f"git-sim live: stopped after {max(0, len(session.snapshots) - 1)} change(s)"
        )
