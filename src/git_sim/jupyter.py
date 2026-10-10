"""git-sim in Jupyter: ``%load_ext git_sim.jupyter`` then

    %gitsim rebase main                 the interactive graph, inline
    %gitsim --height 700 merge feature  a fixed height (it fits the graph otherwise)
    %gitsim preflight reset --hard HEAD~1
                                        the pre-flight report, as text
    %gitsim live                        the live graph, updating as the repo changes
    %gitsim live stop                   stops it (so does restarting the kernel)

The command runs in the notebook's working directory (or ``-C path``) exactly
as it would in a terminal, with the browser kept closed, and the page git-sim
writes is shown in an iframe so its scripts and styles stay out of the
notebook's own. Live mode runs git-sim live in the background and frames the
page its local server serves, so it needs Jupyter on your own machine.
Nothing in the repository is changed.
"""

import atexit
import html
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
from typing import Dict, List, Optional, Tuple

DEFAULT_HEIGHT = 560


def parse_line(line: str) -> Tuple[List[str], Optional[int], Optional[str]]:
    """Split a magic line into git-sim arguments, the iframe height (None to
    fit the graph) and the repository path (our own options are taken off the
    front)."""
    words = shlex.split(line, posix=(os.name != "nt"))
    height, repo = None, None
    while words and words[0] in ("--height", "-C", "--repo"):
        flag = words.pop(0)
        if not words:
            break
        value = words.pop(0)
        if flag == "--height":
            height = int(value)
        else:
            repo = value
    return words, height, repo


MAX_FIT_HEIGHT = 1200

# Runs in the notebook when the frame loads (the sandbox allows same origin,
# so it can read the page). The viewer shrinks a tall graph to the frame, so
# the graph's own height is cleared and measured with the frame squeezed to
# 1px, all before the browser paints. The frame refits when its width changes
# or the viewer's layout does.
FIT_SCRIPT = (
    "var f=this,w=f.contentWindow,last=0;"
    "function fit(){var d=f.contentDocument,s=d&&d.getElementById('scene');if(!s)return;"
    "s.style.height='';f.style.height='1px';"
    f"f.style.height=Math.min(d.documentElement.scrollHeight+24,{MAX_FIT_HEIGHT})+'px';}}"
    "fit();w.addEventListener('git-sim:layout',fit);"
    "if(window.ResizeObserver)new ResizeObserver(function(){"
    "if(f.clientWidth!==last){last=f.clientWidth;fit();}}).observe(f);"
)


def embed_page(page_html: str, height: Optional[int] = None) -> str:
    """The page inside an iframe, so a notebook can show several without
    their scripts or ids colliding. The div keeps IPython from suggesting its
    IFrame, which takes a URL rather than a page. With no height, the frame
    grows to fit the graph."""
    size = (
        f'height:{int(height)}px"'
        if height
        else f'height:{DEFAULT_HEIGHT}px" onload="{html.escape(FIT_SCRIPT, quote=True)}"'
    )
    return (
        f'<div><iframe srcdoc="{html.escape(page_html, quote=True)}" '
        f'style="width:100%;border:0;border-radius:10px;{size} '
        'sandbox="allow-scripts allow-same-origin allow-popups" '
        'title="git-sim"></iframe></div>'
    )


def run(words: List[str], repo: Optional[str] = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, git_sim_auto_open="false")
    cmd = [sys.executable, "-m", "git_sim"]
    if words and words[0] == "preflight":
        cmd += words
        if repo:
            cmd += ["-C", repo]
    else:
        cmd += ["-d", "--img-format", "html", "--output-only-path", *words]
    return subprocess.run(
        cmd,
        cwd=repo or None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


LIVE_HEIGHT = 760
LIVE_URL = re.compile(r"http://127\.0\.0\.1:\d+/#k=[\w-]+")

# The git-sim live servers this kernel started: repository folder -> (process, url)
_live: Dict[str, Tuple[subprocess.Popen, str]] = {}


def remote_kernel() -> bool:
    """Whether the notebook is likely open in a browser on another machine
    (Colab, JupyterHub, Binder), which can't reach this machine's 127.0.0.1."""
    return "google.colab" in sys.modules or any(
        name in os.environ
        for name in ("COLAB_RELEASE_TAG", "JUPYTERHUB_API_URL", "BINDER_SERVICE_HOST")
    )


def live_frame(url: str, height: int = LIVE_HEIGHT) -> str:
    return (
        f'<div><iframe src="{html.escape(url, quote=True)}" '
        f'style="width:100%;height:{int(height)}px;border:0;border-radius:10px" '
        'title="git-sim live"></iframe></div>'
    )


def live_start(extra: List[str], repo: Optional[str]) -> Tuple[Optional[str], str]:
    """Start git-sim live for the repository in the background, or reuse the
    one already running there. Returns the page's URL, or None and what went
    wrong."""
    where = os.path.abspath(repo or ".")
    running = _live.get(where)
    if running and running[0].poll() is None:
        return running[1], ""
    cmd = [sys.executable, "-m", "git_sim", "--open-in", "local", "live"]
    cmd += ["--allow-local-frames", *extra]
    proc = subprocess.Popen(
        cmd,
        cwd=where,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, git_sim_auto_open="false"),
    )
    # It prints the URL once the first drawing is done. The rest of what it
    # prints is read and dropped so the pipe never fills up.
    found: "queue.Queue[str]" = queue.Queue()
    said: List[str] = []

    def read():
        for text in proc.stderr:
            match = LIVE_URL.search(text)
            if match:
                found.put(match.group(0))
            elif found.empty():
                said.append(text)
        found.put("")

    threading.Thread(target=read, daemon=True).start()
    try:
        url = found.get(timeout=60)
    except queue.Empty:
        url = ""
    if not url:
        proc.kill()
        return None, "".join(said).strip() or "git-sim live did not start in 60 seconds"
    _live[where] = (proc, url)
    return url, ""


def live_stop() -> List[str]:
    """Stop every git-sim live this kernel started. Returns their folders."""
    stopped = []
    for where, (proc, _) in list(_live.items()):
        if proc.poll() is None:
            proc.terminate()
            stopped.append(where)
        del _live[where]
    return stopped


atexit.register(live_stop)


def show_live(rest: List[str], height: Optional[int], repo: Optional[str]) -> None:
    from IPython.display import HTML, Markdown, display

    if rest[:1] == ["stop"]:
        stopped = live_stop()
        display(
            Markdown(
                "Stopped git-sim live for " + ", ".join(f"`{s}`" for s in stopped) + "."
                if stopped
                else "git-sim live isn't running."
            )
        )
        return
    if remote_kernel():
        display(
            Markdown(
                "Live mode needs Jupyter running on your own machine, because the page "
                "comes from a server on the kernel's `127.0.0.1`, which your browser "
                "can't reach from here. Run `git-sim live` on the machine with the repo instead."
            )
        )
        return
    url, error = live_start(rest, repo)
    if not url:
        display(
            HTML(
                f"<pre style='color:#b91c1c;font:13px/1.45 monospace'>git-sim live could not start\n{html.escape(error)}</pre>"
            )
        )
        return
    display(HTML(live_frame(url, height or LIVE_HEIGHT)))
    display(
        Markdown(
            "Watching the repo in the background. `%gitsim live stop` stops it, and so does restarting the kernel."
        )
    )


def gitsim(line: str):
    """The %gitsim line magic."""
    from IPython.display import HTML, Markdown, display

    words, height, repo = parse_line(line)
    if not words:
        display(
            Markdown(
                "`%gitsim <git command>`, e.g. `%gitsim rebase main`, `%gitsim preflight reset --hard HEAD~1`, or `%gitsim live`."
            )
        )
        return
    if words[0] == "live":
        show_live(words[1:], height, repo)
        return
    result = run(words, repo)
    if words[0] == "preflight":
        text = (result.stdout or "") + (result.stderr or "")
        display(
            HTML(
                f"<pre style='font:13px/1.45 monospace'>{html.escape(text.strip())}</pre>"
            )
        )
        return
    lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    page = next(
        (l for l in reversed(lines) if l.lower().endswith((".html", ".htm"))), None
    )
    if result.returncode != 0 or not page or not os.path.exists(page):
        text = (result.stderr or "") + "\n" + (result.stdout or "")
        display(
            HTML(
                f"<pre style='color:#b91c1c;font:13px/1.45 monospace'>git-sim could not simulate `git {html.escape(' '.join(words))}`\n{html.escape(text.strip())}</pre>"
            )
        )
        return
    with open(page, encoding="utf-8") as f:
        display(HTML(embed_page(f.read(), height)))


def load_ipython_extension(ipython):
    ipython.register_magic_function(gitsim, magic_kind="line", magic_name="gitsim")
