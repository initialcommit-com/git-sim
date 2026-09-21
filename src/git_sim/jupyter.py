"""git-sim in Jupyter: ``%load_ext git_sim.jupyter`` then

    %gitsim rebase main                 the interactive graph, inline
    %gitsim --height 700 merge feature  taller
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


def parse_line(line: str) -> Tuple[List[str], int, Optional[str]]:
    """Split a magic line into git-sim arguments, the iframe height and the
    repository path (our own options are taken off the front)."""
    words = shlex.split(line, posix=(os.name != "nt"))
    height, repo = DEFAULT_HEIGHT, None
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


def embed_page(page_html: str, height: int = DEFAULT_HEIGHT) -> str:
    """The page inside an iframe, so a notebook can show several without
    their scripts or ids colliding."""
    return (
        f'<iframe srcdoc="{html.escape(page_html, quote=True)}" '
        f'style="width:100%;height:{int(height)}px;border:0;border-radius:10px" '
        'sandbox="allow-scripts allow-same-origin allow-popups" '
        'title="git-sim"></iframe>'
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
