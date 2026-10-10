"""The Jupyter magic's pieces that need no notebook."""

import subprocess
import urllib.request

from git_sim import jupyter
from git_sim.jupyter import DEFAULT_HEIGHT, embed_page, parse_line


def test_the_magic_line_splits_our_options_from_gits():
    assert parse_line("rebase main") == (["rebase", "main"], None, None)
    assert parse_line("--height 700 -C ../repo merge feature") == (
        ["merge", "feature"],
        700,
        "../repo",
    )
    assert parse_line("preflight reset --hard HEAD~1")[0] == [
        "preflight",
        "reset",
        "--hard",
        "HEAD~1",
    ]
    assert parse_line("") == ([], None, None)


def test_the_page_is_framed_with_its_markup_escaped():
    frame = embed_page('<html><body onload="x()">a & b</body></html>', 640)
    assert frame.startswith('<div><iframe srcdoc="') and "height:640px" in frame
    assert (
        "&lt;html&gt;" in frame and "&quot;x()&quot;" in frame and "a &amp; b" in frame
    )
    assert "sandbox=" in frame and '" onload="' not in frame


def test_with_no_height_the_frame_fits_the_graph():
    frame = embed_page("<html></html>")
    assert f"height:{DEFAULT_HEIGHT}px" in frame and '" onload="' in frame
    assert "getElementById(&#x27;scene&#x27;)" in frame


def test_live_starts_once_per_repo_and_serves_a_frameable_page(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "a")
    try:
        url, error = jupyter.live_start(["--no-zones"], str(tmp_path))
        assert url and not error and jupyter.LIVE_URL.fullmatch(url)
        # a second cell reuses the running server
        assert jupyter.live_start([], str(tmp_path)) == (url, "")
        with urllib.request.urlopen(url.split("#")[0]) as r:
            assert "frame-ancestors" in r.headers["Content-Security-Policy"]
        assert f'src="{url}"' in jupyter.live_frame(url)
    finally:
        assert jupyter.live_stop() == [str(tmp_path)]
    assert jupyter.live_stop() == []
