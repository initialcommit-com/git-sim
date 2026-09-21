"""Interactive (SVG/HTML) output: the SVG painter, the page wrapper, and the
before/after tagging the scenes do for it."""

import os
import pathlib
import re
import subprocess

import numpy as np
import pytest

from git_sim.settings import Settings, settings
from git_sim.theme import DARK


def run_git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Five commits on main, a feature branch off commit 2, cwd inside the repo."""
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    for i in range(1, 6):
        (path / f"file{i}.txt").write_text(f"content {i}\n")
        run_git(path, "add", ".")
        run_git(path, "commit", "-m", f"commit {i}")
    run_git(path, "branch", "feature", "HEAD~3")
    for key, value in Settings().model_dump().items():
        setattr(settings, key, value)
    settings.auto_open = False
    monkeypatch.chdir(path)
    return path


def attrs(svg, selector):
    """All elements of the SVG whose attribute string contains ``selector``."""
    return [m for m in re.findall(r"<[a-z]+ [^>]*>", svg) if selector in m]


def test_svg_painter_mirrors_the_raster_primitives(tmp_path):
    from git_sim import render as m

    scene = m.Scene()
    disc = m.Circle(color="#F47067", fill_opacity=1.0)
    disc.set_shadow(DARK.shadow("#F47067"))
    disc.set_meta(role="commit", sha="abc123", phase="before")
    pill = m.RoundedRectangle(corner_radius=0.1, width=1, height=0.4, fill_opacity=1)
    label = m.Text("main", font="Monospace", font_size=20, weight=m.BOLD)
    curve = m.LaneArrow(np.array([0.0, 0.0, 0.0]), np.array([2.5, -4.0, 0.0]))
    dashed = m.DashedLine(m.LEFT, m.RIGHT, dash_length=0.2)
    scene.add(disc, pill, label, curve, dashed)
    svg = scene.render_svg(background=DARK.bg)
    assert svg.startswith('<svg id="scene"') and svg.endswith("</svg>")
    # The viewBox frames the drawn content (padded), not the whole 16:9 frame.
    vb = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', svg)
    assert vb is not None
    x, y, w, h = (float(v) for v in vb.groups())
    assert 0 < w < 1920 and 0 < h < 1080
    assert f'width="{vb.group(3)}"' in svg and f'height="{vb.group(4)}"' in svg
    assert "feDropShadow" in svg and 'filter="url(#shadow1)"' in svg
    circle = attrs(svg, "<circle")[0]
    assert 'data-role="commit"' in circle and 'data-sha="abc123"' in circle
    assert 'fill="#F47067"' in circle
    assert attrs(svg, "<rect") and 'rx="' in attrs(svg, "<rect")[-1]
    text = attrs(svg, "<text")[0]
    assert 'font-weight="700"' in text and "textLength=" in text
    assert re.search(r'<path d="M [\d.]+ [\d.]+ C ', svg), "lane arrows are cubics"
    assert len(attrs(svg, "<line")) >= 2, "dashes are separate lines"
    # Nothing is written to disk for an SVG string.
    assert list(tmp_path.iterdir()) == []


def test_html_page_is_self_contained_and_wires_the_controls(tmp_path):
    from git_sim import render as m

    scene = m.Scene()
    scene.add(m.Circle().set_meta(role="commit", sha="a", phase="after"))
    out = tmp_path / "page.html"
    data = scene.render_html(str(out), theme=DARK, title="git commit -m x")
    page = data.decode("utf-8")
    assert out.exists() and page.startswith("<!DOCTYPE html>")
    assert "<title>git commit -m x</title>" in page
    assert 'id="toBefore"' in page and 'id="toAfter"' in page
    # #before / #auto / #step=N are page states, so no element may carry those ids.
    assert 'id="before"' not in page and 'id="auto"' not in page
    assert 'id="scrub"' in page and 'type="range"' in page, "a before/after scrubber"
    assert 'id="play"' in page and "startPlay" in page and "stopPlay" in page
    assert 'id="bar"' in page and "position:sticky" in page
    assert "data-phase" in page and "ancestry" in page and "viewBox" in page
    # Links the reader may click are fine; nothing is fetched on load.
    assert 'src="http' not in page and "<link" not in page and "@import" not in page
    assert 'href="https://initialcommit.com"' in page
    assert 'href="https://devlands.com"' in page
    assert 'id="help"' in page and 'id="helpMenu"' in page
    assert 'id="share"' in page and 'data-action="image"' in page
    assert "intent/tweet" in page and "bsky.app" in page and "linkedin.com" in page
    assert "startPlay();" in page and "before|after|step=" in page, "plays on open"
    assert "/^step=\\d+$/.test(raw)" in page, "#step=N is a pinned state, not a key"
    assert "let progress = 0;" in page, "opens on the 'before' state"
    assert "function fit()" in page and "stage.getBoundingClientRect().top" in page
    assert "function scheduleClear()" in page, "hover highlight survives the gaps"
    assert "commit-hit" in page and "getBBox()" in page, "one hit area per commit"
    assert "forEach(el => link(el.dataset.src, el.dataset.dst))" in page
    assert "GitSimViewer.init();" in page
    assert '"viewer_url": "https://initialcommit.com/tools/git-sim"' in page
    assert "mousedown" not in page, "no drag-to-pan"
    assert f"--bg:{DARK.bg}" in page


def test_moved_and_removed_labels_carry_before_positions(repo):
    from git_sim.branch import Branch
    from git_sim.commit import Commit

    scene = Commit(message="new", amend=False)
    scene.construct()
    svg = scene.render_svg(background=DARK.bg)
    new_disc = [e for e in attrs(svg, 'data-sha="abcdef"') if e.startswith("<circle")]
    assert new_disc and 'data-phase="after"' in new_disc[0]
    assert 'data-author="simulated"' in new_disc[0]
    head_pill = [e for e in attrs(svg, 'data-name="HEAD"') if e.startswith("<rect")][0]
    assert "data-dx=" in head_pill and "data-dy=" in head_pill, "HEAD slid to abcdef"
    dx = float(re.search(r'data-dx="([-\d.]+)"', head_pill).group(1))
    assert (
        dx > 0
    ), "in the left-to-right layout HEAD moved left, so 'before' is to the right"
    # Real commits are 'before' and know their parents and authors.
    real = [e for e in attrs(svg, 'data-role="commit"') if 'data-phase="before"' in e]
    assert real and all(
        "data-parents=" in e and 'data-author="Test"' in e for e in real
    )

    deleted = Branch(name="feature", delete=True)
    deleted.construct()
    assert len(deleted.removed_mobjects) == 1
    svg = deleted.render_svg(
        background=DARK.bg, extra_mobjects=deleted.removed_mobjects
    )
    gone = [e for e in attrs(svg, 'data-name="feature"') if e.startswith("<rect")]
    assert gone and 'data-phase="removed"' in gone[0]


def test_gold_marks_remember_their_before_color(repo):
    from git_sim.branch import Branch

    run_git(repo, "checkout", "-q", "-b", "wip")
    (repo / "wip.txt").write_text("wip\n")
    run_git(repo, "add", "wip.txt")
    run_git(repo, "commit", "-q", "-m", "wip work")
    run_git(repo, "checkout", "-q", "main")
    scene = Branch(name="wip", force_delete=True)
    scene.construct()
    svg = scene.render_svg(background=DARK.bg)
    gold = [e for e in attrs(svg, "data-before-fill=") if e.startswith("<circle")]
    assert gold and f'fill="{DARK.gold}"' in gold[0]
    assert 'data-before-fill="' + DARK.lane_color(1) + '"' in gold[0]


def test_multi_action_commands_are_stepped(repo, tmp_path):
    from git_sim.rebase import Rebase

    c3, c4, c5 = (run_git(repo, "rev-parse", f"HEAD~{i}").strip() for i in (2, 1, 0))
    todo = tmp_path / "todo"
    todo.write_text(f"pick {c3[:7]} a\nsquash {c4[:7]} b\ndrop {c5[:7]} c\n")
    scene = Rebase(branch="feature", interactive=True, todo=str(todo))
    scene.construct()
    svg = scene.render_svg(background=DARK.bg)
    commits, trails, arrows, moves = step_groups(svg)
    # Each todo action takes two steps: the pick slides in with its trail (1)
    # and its parent arrow draws (2); the squash adds only a trail (3); the
    # drop turns its commit gold (5); then the labels move (7).
    assert commits == {1, 5} and trails == {1, 3} and arrows == {2}
    assert moves == {7}
    dropped = [e for e in attrs(svg, f'data-sha="{c5}"') if "data-before-fill" in e]
    assert dropped and 'data-step="5"' in dropped[0]


def step_groups(svg):
    """The step numbers used in an SVG by simulated commits (including ones
    recolored), by dotted "copied from" trails, by parent arrows, and by
    labels that move."""
    step_of = lambda e: int(re.search(r'data-step="(\d+)"', e).group(1))
    commits = {
        step_of(e)
        for e in attrs(svg, 'data-role="commit"')
        if 'data-phase="after"' in e and "data-step=" in e and e.startswith("<circle")
    }
    recolored = {
        step_of(e)
        for e in attrs(svg, "data-before-fill=")
        if "data-step=" in e and e.startswith("<circle")
    }
    edges = [
        e
        for e in attrs(svg, 'data-role="edge"')
        if 'data-phase="after"' in e and "data-step=" in e
    ]
    trails = {step_of(e) for e in edges if 'data-kind="origin"' in e}
    arrows = {step_of(e) for e in edges if 'data-kind="origin"' not in e}
    moves = {
        step_of(e)
        for e in attrs(svg, "data-dx=")
        if "data-step=" in e and 'data-role="ref"' in e
    }
    return commits | recolored, trails, arrows, moves


def test_plain_rebase_replays_one_commit_per_step(repo):
    from git_sim.rebase import Rebase

    # feature diverges from main, which has three commits of its own beyond
    # the fork; rebasing main onto feature replays them, one step each.
    run_git(repo, "checkout", "-q", "feature")
    (repo / "feature.txt").write_text("feature work\n")
    run_git(repo, "add", "feature.txt")
    run_git(repo, "commit", "-q", "-m", "feature work")
    run_git(repo, "checkout", "-q", "main")
    scene = Rebase(branch="feature")
    scene.construct()
    svg = scene.render_svg(background=DARK.bg)
    copies = [
        e
        for e in attrs(svg, 'data-role="commit"')
        if 'data-phase="after"' in e and e.startswith("<circle")
    ]
    assert len(copies) == 3
    commits, trails, arrows, moves = step_groups(svg)
    # Each copy slides in with its dotted trail (odd steps), then its parent
    # arrow draws (even steps); HEAD and the branch label move last (7).
    assert commits == {1, 3, 5} and trails == {1, 3, 5} and arrows == {2, 4, 6}
    assert moves == {7}
    # The copies travel from the commits they were made from.
    assert all("data-dx=" in e for e in copies), "copies know where they came from"
    dots = [e for e in attrs(svg, 'data-kind="origin"') if e.startswith("<circle")]
    ts = sorted({float(re.search(r'data-t="([\d.]+)"', e).group(1)) for e in dots})
    assert ts[0] == 0.0 and ts[-1] <= 1.0 and len(ts) > 2, "dots know their place"
    # Dotted links are drawn first, beneath the commits they cross.
    first_dot = svg.index('data-kind="origin"')
    first_copy = min(svg.index(e) for e in copies)
    assert first_dot < first_copy


def test_zone_moves_slide_files_between_columns(repo):
    from git_sim.add import Add

    (repo / "file1.txt").write_text("changed\n")
    scene = Add(files=["file1.txt"])
    scene.construct()
    svg = scene.render_svg(background=DARK.bg)
    staged = [
        e
        for e in attrs(svg, 'data-name="file1.txt"')
        if 'data-column="Staged files"' in e
    ]
    assert staged and 'data-phase="after"' in staged[0] and "data-dx=" in staged[0]
    modified = [
        e
        for e in attrs(svg, 'data-name="file1.txt"')
        if 'data-column="Modified files"' in e
    ]
    assert modified and 'data-phase="before"' in modified[0]


def test_interactive_flag_selects_the_html_format():
    from git_sim.enums import ImgFormat

    assert ImgFormat("html") is ImgFormat.HTML
    assert Settings().img_format is ImgFormat.HTML, "the page is the default output"
    from git_sim.__main__ import app  # noqa: F401  (the option is registered)

    import inspect

    from git_sim.__main__ import main

    assert "interactive" in inspect.signature(main).parameters


def test_hosted_viewer_link_carries_the_graph_in_the_fragment():
    import base64
    import urllib.parse
    import zlib

    from git_sim.enums import OpenIn
    from git_sim.render.html import viewer_link

    assert Settings().open_in is OpenIn.HOSTED, "the hosted viewer is the default"
    svg = '<svg id="scene"><circle data-sha="abc"/></svg>'
    link = viewer_link(
        svg,
        title="git  reset --hard HEAD~2",
        theme_name="light",
        summary="* abc (HEAD -> main) top",
        local_path=r"C:\repo\git-sim_media\page.html",
    )
    parts = urllib.parse.urlsplit(link)
    assert parts.scheme == "https" and parts.netloc == "initialcommit.com"
    query = dict(urllib.parse.parse_qsl(parts.query))
    assert query["t"] == "git reset --hard HEAD~2" and query["m"] == "light"
    fragment = dict(urllib.parse.parse_qsl(parts.fragment))
    assert "s" not in fragment, "unpinned: the page opens on 'before' and plays"
    assert fragment["p"] == "page.html", "only the file name, never the path"
    pinned = viewer_link(svg, state="after")
    pinned_fragment = dict(
        urllib.parse.parse_qsl(urllib.parse.urlsplit(pinned).fragment)
    )
    assert pinned_fragment["s"] == "after"

    # git-sim opening the page for its own user sends the server nothing about
    # the repository: no command or text graph in the query string.
    private = urllib.parse.urlsplit(
        viewer_link(svg, title="git reset --hard", summary="* abc secret", share=False)
    )
    assert dict(urllib.parse.parse_qsl(private.query)) == {"m": "dark"}
    private_fragment = dict(urllib.parse.parse_qsl(private.fragment))
    assert private_fragment["t"] == "git reset --hard" and "g" not in private.query
    assert "secret" not in private.geturl()

    def unpack(packed):
        padded = packed + "=" * (-len(packed) % 4)
        return zlib.decompress(base64.urlsafe_b64decode(padded)).decode("utf-8")

    assert unpack(fragment["d"]) == svg, "the graph round-trips through the link"
    assert unpack(query["g"]) == "* abc (HEAD -> main) top"
    assert (
        svg not in link and "abc" not in parts.query
    ), "nothing of the graph in the query"
    # The page knows how to say where the local copy is.
    from git_sim.render.html import VIEWER_JS

    assert "function openedNote" in VIEWER_JS and "params.p" in VIEWER_JS
    assert "--open-in local" in VIEWER_JS and "git_sim_open_in=local" in VIEWER_JS


def test_page_opens_in_the_hosted_viewer_unless_told_otherwise(
    repo, tmp_path, monkeypatch, capsys
):
    import urllib.parse

    from git_sim import animations
    from git_sim.commit import Commit
    from git_sim.enums import OpenIn
    from git_sim.render import scene as scene_module
    from git_sim.theme import DARK

    opened = {"urls": [], "files": []}
    monkeypatch.setattr(
        scene_module, "open_url", lambda url: opened["urls"].append(url)
    )
    monkeypatch.setattr(
        scene_module, "open_file", lambda path: opened["files"].append(path)
    )
    monkeypatch.setattr(
        "git_sim.render.open_file", lambda path: opened["files"].append(path)
    )
    settings.auto_open = True
    scene = Commit(message="new", amend=False)
    scene.construct()
    page = tmp_path / "page.html"
    scene.render_html(str(page), theme=DARK, title=scene.cmd)

    animations._open_page(scene, str(page), DARK)
    assert len(opened["urls"]) == 1 and not opened["files"]
    url = opened["urls"][0]
    assert url.startswith(settings.viewer_url + "?m=dark#")
    query, fragment = url.split("?", 1)[1].split("#", 1)
    assert query == "m=dark", "the server is told nothing but the theme"
    frag = dict(urllib.parse.parse_qsl(fragment))
    assert frag["d"] and frag["t"].startswith("git commit")
    assert frag["p"] == page.name and str(tmp_path) not in url, "file name only"
    out = capsys.readouterr().out
    assert "Opened in the git-sim viewer at initialcommit.com" in out
    assert "Nothing about you, your repository or your code was sent" in out
    assert "--open-in local" in out and "git_sim_open_in=local" in out

    settings.open_in = OpenIn.LOCAL
    animations._open_page(scene, str(page), DARK)
    assert opened["files"] == [str(page)] and len(opened["urls"]) == 1


def run_cli(args, cwd):
    """Run the CLI in a fresh interpreter with the user's git_sim_* settings
    stripped, returning the completed process (bytes output)."""
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if not k.lower().startswith("git_sim_")}
    code = f"from git_sim.__main__ import app; app({args!r})"
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        timeout=180,
        cwd=cwd,
        env=env,
    )


def test_cli_writes_the_page_by_default_and_an_image_to_a_pipe(repo, tmp_path):
    media = str(tmp_path / "media")
    result = run_cli(["-d", "--output-only-path", "--media-dir", media, "log"], repo)
    assert result.returncode == 0, result.stderr.decode()
    page = pathlib.Path(result.stdout.decode().strip().splitlines()[-1])
    assert page.suffix == ".html" and "git-sim-log" in page.name
    assert page.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")

    # --img-format still gives the classic image.
    result = run_cli(
        [
            "-d",
            "--output-only-path",
            "--img-format",
            "jpg",
            "--media-dir",
            media,
            "log",
        ],
        repo,
    )
    assert result.returncode == 0, result.stderr.decode()
    image = pathlib.Path(result.stdout.decode().strip().splitlines()[-1])
    assert image.suffix == ".jpg" and image.read_bytes()[:3] == b"\xff\xd8\xff"

    # A pipe gets picture bytes, never a page.
    result = run_cli(["-d", "--stdout", "--media-dir", media, "log"], repo)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout[:8] == b"\x89PNG\r\n\x1a\n"


def test_zone_separators_reach_the_last_row(repo):
    from git_sim.add import Add

    for i in range(14):
        (repo / f"loose{i:02d}.txt").write_text("x\n")
    scene = Add(files=["loose00.txt"])
    scene.construct()
    lowest_row = min(t.get_bottom()[1] for t in scene.firstColumnFiles)
    for separator in scene.zoneSeparators:
        assert separator.get_bottom()[1] <= lowest_row - 0.5


def test_viewer_assets_export_matches_the_page(tmp_path):
    """initialcommit.com serves the same stylesheet, script and header the
    standalone page embeds, exported from here so there is one source."""
    from git_sim import render as m
    from git_sim.render.html import VIEWER_CSS, VIEWER_JS, export_viewer_assets

    written = export_viewer_assets(str(tmp_path))
    names = {pathlib.Path(p).name for p in written}
    assert names == {
        "git-sim-viewer.css",
        "git-sim-viewer.js",
        "git-sim-viewer-header.html",
        # the live page's strip, stylesheet and script (see test_live.py)
        "git-sim-live.css",
        "git-sim-live.js",
        "git-sim-live-strip.html",
        # the embeddable viewer (see test_embed.py)
        "git-sim-embed.js",
    }
    css = (tmp_path / "git-sim-viewer.css").read_text(encoding="utf-8")
    js = (tmp_path / "git-sim-viewer.js").read_text(encoding="utf-8")
    header = (tmp_path / "git-sim-viewer-header.html").read_text(encoding="utf-8")
    assert css.strip() == VIEWER_CSS.strip() and js.strip() == VIEWER_JS.strip()
    assert ':root[data-theme="light"]' in css and f"--bg:{DARK.bg}" in css
    assert "boot" in js and "DecompressionStream" in js and "CompressionStream" in js
    # Both palettes ride along so a graph drawn in one theme can be shown in the other.
    assert (
        "__PALETTES__" not in js and '"lane_rings"' in js and "function retheme" in js
    )
    assert f'"bg": "{DARK.bg}"' in js and '"light": {' in js
    assert '<header id="bar" th:fragment="header">' in header and 'id="scrub"' in header
    # The standalone page carries the very same CSS and JS inline.
    scene = m.Scene()
    scene.add(m.Circle().set_meta(role="commit", sha="a"))
    page = scene.render_html(str(tmp_path / "p.html"), theme=DARK, title="git log")
    assert VIEWER_CSS in page.decode("utf-8") and VIEWER_JS in page.decode("utf-8")


def stacked_right_above(label, base):
    """``label`` sits directly above ``base``: same column, a small gap."""
    gap = label.get_bottom()[1] - base.get_top()[1]
    return abs(label.get_center()[0] - base.get_center()[0]) < 1e-6 and 0 < gap < 0.5


def test_tags_on_the_head_commit_stay_drawn_when_head_moves_on(repo):
    from git_sim.commit import Commit

    run_git(repo, "tag", "v5")
    scene = Commit(message="new", amend=False)
    scene.construct()
    old_head = run_git(repo, "rev-parse", "HEAD").strip()
    assert "v5" in scene.drawnRefs, "the tag on the first commit is drawn"
    # HEAD and main left for abcdef; the tag closed the gap they left behind.
    assert stacked_right_above(scene.drawnRefs["v5"], scene.drawnCommitIds[old_head])
    svg = scene.render_svg(background=DARK.bg)
    pill = [e for e in attrs(svg, 'data-name="v5"') if e.startswith("<rect")][0]
    assert 'data-phase="before"' in pill and "data-dy=" in pill


def test_moving_labels_stack_above_the_labels_already_there(repo):
    from git_sim.enums import ResetMode
    from git_sim.reset import Reset

    run_git(repo, "tag", "v5")
    run_git(repo, "tag", "v3", "HEAD~2")
    target = run_git(repo, "rev-parse", "HEAD~2").strip()
    scene = Reset(
        commit="HEAD~2", mode=ResetMode.DEFAULT, soft=False, mixed=False, hard=False
    )
    scene.construct()
    head, main, v3 = (scene.drawnRefs[n] for n in ("HEAD", "main", "v3"))
    assert "v3" in scene.drawnRefs, "the target keeps its own labels"
    assert stacked_right_above(v3, scene.drawnCommitIds[target])
    assert stacked_right_above(head, v3), "HEAD lands above the tag, not on it"
    assert stacked_right_above(main, head)
    assert [r for r in scene.refs_on(target)] and scene.commit_holding(head) == target


def test_new_tags_stack_on_their_commit_and_deleted_ones_are_removed(repo):
    from git_sim.tag import Tag

    run_git(repo, "tag", "v3", "HEAD~2")
    scene = Tag(name="v9", commit="HEAD~2", d=False)
    scene.construct()
    assert stacked_right_above(scene.drawnRefs["v9"], scene.drawnRefs["v3"])
    svg = scene.render_svg(background=DARK.bg)
    pill = [e for e in attrs(svg, 'data-name="v9"') if e.startswith("<rect")][0]
    assert 'data-phase="after"' in pill

    gone = Tag(name="v3", commit=None, d=True)
    gone.construct()
    assert len(gone.removed_mobjects) == 1 and "v3" not in gone.drawnRefs
