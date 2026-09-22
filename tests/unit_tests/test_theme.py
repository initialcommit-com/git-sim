"""The visual theme: palettes, the rounded pill and shadow primitives the
skia renderer gained for it, and the scenes' use of them."""

import os
import subprocess
import types

import numpy as np
import pytest

from git_sim.settings import Settings, settings
from git_sim.theme import DARK, LIGHT, apply_shadow, theme_for


def test_palettes_are_distinct_and_complete():
    assert theme_for(False) is DARK and theme_for(True) is LIGHT
    for theme in (DARK, LIGHT):
        for name in (
            "bg",
            "text",
            "text_muted",
            "rule",
            "arrow",
            "accent",
            "commit",
            "merge",
            "head",
            "branch",
            "tag",
            "purple",
            "gold",
            "ref_text",
        ):
            value = getattr(theme, name)
            assert value.startswith("#") and len(value) == 7, (theme.name, name)
        assert len(theme.author_colors) == 11
    assert DARK.bg != LIGHT.bg and DARK.text != LIGHT.text
    # Dark mode glows in the disc's own color; light mode drops a neutral shadow.
    assert DARK.shadow("#123456")["color"] == "#123456"
    assert LIGHT.shadow("#123456")["color"] == "#000000"
    assert DARK.pill_shadow() is None and LIGHT.pill_shadow() is not None


def test_shim_shadow_and_rounded_rectangle_render(tmp_path):
    from git_sim import render as m

    scene = m.Scene()
    box = m.RoundedRectangle(
        corner_radius=0.2, width=2, height=0.6, color="#3FB950", fill_opacity=1.0
    )
    apply_shadow(box, LIGHT.shadow("#3FB950"))
    assert box.shadow["sigma"] > 0
    disc = m.Circle(color="#F47067", fill_opacity=1.0).shift(m.DOWN * 2)
    apply_shadow(disc, DARK.shadow("#F47067"))
    scene.add(box, disc)
    out = tmp_path / "shadow.png"
    data = scene.render_image(str(out), background=DARK.bg, fmt="png")
    assert out.exists() and len(data) > 1000
    # Bounding boxes are those of the plain shapes: shadows never shift layout.
    assert np.allclose(box.get_width(), 2) and np.allclose(box.get_height(), 0.6)


def test_apply_shadow_is_a_noop_without_set_shadow():
    class Plain:
        pass

    plain = Plain()
    assert apply_shadow(plain, DARK.shadow()) is plain
    assert not hasattr(plain, "shadow")


def test_monospace_resolves_to_a_real_typeface():
    from git_sim.render.text import GENERIC_FAMILIES, _typeface

    assert GENERIC_FAMILIES["monospace"][-1] == "Courier New"
    typeface, _ = _typeface("Monospace", False)
    assert typeface is not None


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "repo"
    path.mkdir()

    def git(*args):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    for i in range(1, 4):
        (path / f"f{i}.txt").write_text(f"{i}\n")
        git("add", ".")
        git("commit", "-m", f"commit {i}")
    for key, value in Settings().model_dump().items():
        setattr(settings, key, value)
    settings.auto_open = False
    monkeypatch.chdir(path)
    return path


@pytest.mark.parametrize("light", [False, True])
def test_scene_takes_its_colors_from_the_theme(repo, light):
    from git_sim.status import Status

    settings.dark_mode = not light
    theme = theme_for(light)
    scene = Status()
    scene.construct()
    assert scene.fontColor == theme.text
    head_box, head_text = scene.drawnRefs["HEAD"]
    assert head_box.fill_color == theme.head and head_box.fill_opacity == 1.0
    assert head_text.color == theme.ref_text
    # Labels keep a fixed color by kind, whatever lane they sit in.
    branch_box, _ = scene.drawnRefs["main"]
    assert branch_box.fill_color == theme.branch
    assert theme.lane_color(0) == theme.commit
    disc = next(iter(scene.drawnCommits.values()))
    assert disc.fill_color == theme.commit and disc.fill_opacity == 1.0
    assert disc.stroke_color == theme.ring_for(theme.commit)
    assert disc.shadow is not None
    # The table gets a translucent header band.
    bands = [
        mob
        for top in scene.mobjects
        for mob in top.get_family()
        if getattr(mob, "fill_color", None) == theme.panel
        and mob.fill_opacity == theme.panel_opacity
    ]
    assert len(bands) == 1
    # Gold marking recolors the glow along with the disc.
    scene.mark_commits([next(iter(scene.drawnCommits))])
    assert disc.fill_color == theme.gold and disc.shadow["color"] in (
        theme.gold,
        "#000000",
    )


def test_lane_hues_cycle_and_rings_track_the_fill():
    assert DARK.lane_color(0) == DARK.commit
    assert DARK.lane_color(1) != DARK.lane_color(0)
    assert DARK.lane_color(len(DARK.lane_colors)) == DARK.lane_color(0)
    assert DARK.lane_color(-2) == DARK.lane_color(2)
    # Dark rims are lighter than the fill, light rims darker.
    assert DARK.ring_for("#808080") == "#A6A6A6"
    assert LIGHT.ring_for("#808080") == "#606060"


def test_lane_arrows_fan_out_around_a_shared_parent(tmp_path):
    from git_sim import render as m

    parent = np.array([2.5, 0.0, 0.0])
    arrows = [
        m.LaneArrow(
            np.array([0.0, -4.0 * k, 0.0]),
            parent,
            lane_pitch=4.0,
            max_stroke_width_to_length_ratio=1000,
        )
        for k in (1, 2, 3, 4)
    ]
    for arrow in arrows:
        arrow.set_length(arrow.get_length() - 3)  # layout shortens the chord
    angles = [round(np.degrees(a.arrival_angle())) for a in arrows]
    assert angles == [30, 50, 60, 70], "further lanes land ever steeper"
    reaches = [round(a.landing()[1], 2) for a in arrows]
    assert reaches == [0.9, 1.3, 1.7, 2.1], "and stop a little further out"
    landings = []
    for arrow in arrows:
        p0, p1, p2, p3 = arrow._controls()
        # Starts just off the child's rim, heading toward the parent's side.
        assert 0.7 < np.linalg.norm(p0 - arrow.anchor_start) < 0.9 and p1[0] > p0[0]
        assert abs(p1[1] - p0[1]) < 1e-9, "runs along its own lane first"
        assert p1[0] <= p2[0] + 1e-9, "never runs past the climb, so no doubling back"
        # Lands pointing at the parent's centre.
        toward = parent - p3
        tangent = p3 - p2
        cos = np.dot(toward, tangent) / (
            np.linalg.norm(toward) * np.linalg.norm(tangent)
        )
        assert cos > 0.999
        landings.append(p3)
    gaps = [np.linalg.norm(a - b) for a, b in zip(landings, landings[1:])]
    assert min(gaps) > 0.35, "arrowheads (0.35 wide) never overlap"
    # None lands over the parent's message (below it, within its text span).
    for p3 in landings:
        rel = p3 - parent
        assert not (rel[1] < -0.8 and abs(rel[0]) < 0.7), rel
    # The bodies climb the empty column beside the lane ends (x >= 1.0 past
    # the child's centre), clear of the ids and messages of the lanes between.
    for arrow in arrows[1:]:
        _, p1, p2, _ = arrow._controls()
        assert p1[0] > 0.9 and p2[0] > 0.9, (p1, p2)
    scene = m.Scene()
    scene.add(*arrows)
    scene.render_image(str(tmp_path / "lanes.png"), fmt="png")


def test_lane_hues_color_commits_but_never_labels(repo):
    from git_sim.log import Log

    subprocess.run(
        ["git", "checkout", "-q", "-b", "side", "HEAD~1"], cwd=repo, check=True
    )
    (repo / "s.txt").write_text("s\n")
    subprocess.run(["git", "add", "s.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "side"], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
    ctx = types.SimpleNamespace(
        parent=types.SimpleNamespace(params={"n": 5, "all": True})
    )
    scene = Log(ctx=ctx, n=5, all=True)
    scene.construct()
    fills = {c.fill_color for c in scene.drawnCommits.values()}
    theme = theme_for(settings.light)  # whichever palette is the default draws the scene
    assert theme.lane_color(1) in fills, "the side lane is drawn in the second hue"
    side_box, _ = scene.drawnRefs["side"]
    main_box, _ = scene.drawnRefs["main"]
    assert side_box.fill_color == main_box.fill_color == theme.branch
    assert scene.drawnRefs["HEAD"][0].fill_color == theme.head


def test_commit_messages_wrap_at_word_boundaries():
    from git_sim.git_sim_base_command import GitSimBaseCommand

    wrapped = GitSimBaseCommand.wrap_message("Merge branch1 into main")
    assert wrapped == "Merge branch1 into\nmain"
    assert all(len(line) <= 20 for line in wrapped.split("\n"))
    assert len(GitSimBaseCommand.wrap_message("x" * 500)) <= 100


def test_pill_labels_center_on_their_capitals():
    """Labels with and without descenders share a baseline inside pills of
    the same height, so "main" and "origin/main" sit at the same visual
    height instead of the ink box pushing descender-bearing names upward."""
    from git_sim import render as m
    from git_sim.git_sim_base_command import GitSimBaseCommand

    box = m.RoundedRectangle(corner_radius=0.12, width=3, height=0.4)
    plain = m.Text("main", font="Monospace", font_size=20, weight=m.BOLD)
    descender = m.Text("origin/pages", font="Monospace", font_size=20, weight=m.BOLD)
    GitSimBaseCommand.center_label(plain, box)
    GitSimBaseCommand.center_label(descender, box)
    assert abs(plain.baseline_y() - descender.baseline_y()) < 1e-6
    # The capitals straddle the pill's center line.
    cap_mid = plain.baseline_y() + plain.layout.cap_height / 2
    assert abs(cap_mid - box.get_center()[1]) < 1e-6
    assert abs(plain.get_center()[0] - box.get_center()[0]) < 1e-6
