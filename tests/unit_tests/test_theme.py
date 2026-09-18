"""The visual theme: palettes, the rounded pill and shadow primitives the
skia renderer gained for it, and the scenes' use of them."""

import os
import subprocess

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

    settings.light_mode = light
    theme = theme_for(light)
    scene = Status()
    scene.construct()
    assert scene.fontColor == theme.text
    head_box, head_text = scene.drawnRefs["HEAD"]
    assert head_box.fill_color == theme.head and head_box.fill_opacity == 1.0
    assert head_text.color == theme.ref_text
    branch_box, _ = scene.drawnRefs["main"]
    assert branch_box.fill_color == theme.branch
    disc = next(iter(scene.drawnCommits.values()))
    assert disc.fill_color == theme.commit and disc.fill_opacity == 1.0
    assert disc.stroke_color == theme.commit_ring
    assert disc.shadow is not None
    # Gold marking recolors the glow along with the disc.
    scene.mark_commits([next(iter(scene.drawnCommits))])
    assert disc.fill_color == theme.gold and disc.shadow["color"] in (
        theme.gold,
        "#000000",
    )


def test_commit_messages_wrap_at_word_boundaries():
    from git_sim.git_sim_base_command import GitSimBaseCommand

    wrapped = GitSimBaseCommand.wrap_message("Merge branch1 into main")
    assert wrapped == "Merge branch1 into\nmain"
    assert all(len(line) <= 20 for line in wrapped.split("\n"))
    assert len(GitSimBaseCommand.wrap_message("x" * 500)) <= 100
