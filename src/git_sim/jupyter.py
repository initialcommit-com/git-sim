"""git-sim in Jupyter: ``%load_ext git_sim.jupyter`` then

    %gitsim rebase main                 the interactive graph, inline
    %gitsim --height 700 merge feature  a fixed height (it fits the graph otherwise)
    %gitsim preflight reset --hard HEAD~1
                                        the pre-flight report, as text

The command runs in the notebook's working directory (or ``-C path``) exactly
as it would in a terminal, with the browser kept closed, and the page git-sim
writes is shown in an iframe so its scripts and styles stay out of the
notebook's own. Nothing in the repository is changed.
"""

import html
import os
import shlex
import subprocess
import sys
from typing import List, Optional, Tuple

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


def gitsim(line: str):
    """The %gitsim line magic."""
    from IPython.display import HTML, Markdown, display

    words, height, repo = parse_line(line)
    if not words:
        display(
            Markdown(
                "`%gitsim <git command>`, e.g. `%gitsim rebase main`, or `%gitsim preflight reset --hard HEAD~1`."
            )
        )
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
