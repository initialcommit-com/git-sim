"""Interactive (SVG/HTML) output: the SVG painter, the page wrapper, and the
before/after tagging the scenes do for it."""

import os
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
    assert 'viewBox="0 0 1920 1080"' in svg
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
    assert 'id="before"' in page and 'id="afterBtn"' in page and 'id="steps"' in page
    assert "data-phase" in page and "ancestry" in page and "viewBox" in page
    assert "http://" not in page.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in page, "no external requests"
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
    steps = {int(s) for s in re.findall(r'data-step="(\d+)"', svg)}
    assert steps == {1, 2, 3}
    dropped = [e for e in attrs(svg, f'data-sha="{c5}"') if "data-before-fill" in e]
    assert dropped and 'data-step="3"' in dropped[0]


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
    from git_sim.__main__ import app  # noqa: F401  (the option is registered)

    import inspect

    from git_sim.__main__ import main

    assert "interactive" in inspect.signature(main).parameters
