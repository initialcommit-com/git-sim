"""The Jupyter magic's pieces that need no notebook."""

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

