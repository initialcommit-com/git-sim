"""The global options, each applied to a real command and checked for the
effect it promises, not just for exiting 0."""

from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8\xff"
SVG = "{http://www.w3.org/2000/svg}"


def elements(path, role):
    root = ET.parse(path).getroot()
    return [el for el in root.iter() if el.get("data-role") == role]


def background_fill(path):
    rects = [el for el in elements(path, "background") if el.tag == f"{SVG}rect"]
    return rects[0].get("fill", "").lower() if rects else None


def label_font_sizes(path):
    return [float(el.get("font-size")) for el in elements(path, "commit-label") if el.tag == f"{SVG}text" and el.get("font-size")]


def test_default_output_is_an_interactive_page(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", "--all", fmt="").ok()
    assert run.path.suffix == ".html"
    text = run.path.read_text(encoding="utf-8")
    assert "<svg" in text and "data-role" in text, "the page embeds the tagged graph"
    assert "scrub" in text, "the page carries the viewer's slider"


def test_open_in_local_writes_the_same_page(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", fmt="", globals_=["--open-in", "local"]).ok()
    assert run.path.suffix == ".html"


def test_open_in_hosted_is_the_default_spelling(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", fmt="", globals_=["--open-in", "hosted"]).ok()
    assert run.path.suffix == ".html"


@pytest.mark.parametrize("fmt,magic", [("png", PNG), ("jpg", JPEG)])
def test_raster_formats(shapes, gitsim, fmt, magic):
    run = gitsim.run(shapes.get("history").path, "log", fmt=fmt).ok()
    assert run.path.suffix == f".{fmt}"
    assert run.path.read_bytes()[: len(magic)] == magic
    assert run.path.stat().st_size > 10_000


def test_svg_is_well_formed_and_tagged(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", "--all").ok()
    assert run.model["commits"], "commits are tagged"
    assert run.model["refs"], "refs are tagged"
    assert run.model["title"].startswith("git log")


def test_stdout_streams_a_png(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", fmt="", globals_=["--stdout"], raw=True)
    assert run.returncode == 0
    assert run.raw[: len(PNG)] == PNG, "raw image on stdout, nothing else"


def test_stdout_jpg(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", fmt="jpg", globals_=["--stdout"], raw=True)
    assert run.returncode == 0 and run.raw[:3] == JPEG


def test_output_only_path_prints_just_the_path(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log").ok()
    lines = [l for l in run.stdout.splitlines() if l.strip()]
    assert lines == [str(run.path)], run.stdout


def test_quiet_prints_nothing(shapes, gitsim):
    """--quiet silences everything but errors, the path included."""
    proc = subprocess.run(
        [sys.executable, "-m", "git_sim", "-d", "--img-format", "svg", "--media-dir", str(gitsim.media), "--quiet", "log"],
        cwd=str(shapes.get("history").path), capture_output=True, env=gitsim.env(),
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    assert proc.stdout.strip() == b"", proc.stdout


def test_media_dir_is_honoured(shapes, gitsim, tmp_path):
    run = gitsim.run(shapes.get("history").path, "log", globals_=["--media-dir", str(tmp_path / "out")]).ok()
    assert str(tmp_path / "out") in str(run.path)


def test_light_mode_changes_the_background(shapes, gitsim):
    dark = gitsim.run(shapes.get("history").path, "log").ok()
    light = gitsim.run(shapes.get("history").path, "log", globals_=["--light-mode"]).ok()
    d, l = background_fill(dark.path), background_fill(light.path)
    assert d and l and d != l
    assert d.startswith("#0") and not l.startswith("#0")


def test_no_light_mode_is_dark(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", globals_=["--no-light-mode"]).ok()
    assert background_fill(run.path).startswith("#0")


def test_transparent_background_keeps_the_svg(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", globals_=["--transparent-bg"]).ok()
    assert run.path.suffix == ".svg", "an SVG stays an SVG"
    fill = background_fill(run.path)
    assert fill in (None, "none", "transparent") or "0" in (elements(run.path, "background")[0].get("fill-opacity") or "")


def test_transparent_background_png(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", fmt="png", globals_=["--transparent-bg"]).ok()
    assert run.path.read_bytes()[: len(PNG)] == PNG


def test_n_limits_commits_per_branch(shapes, gitsim):
    two = gitsim.run(shapes.get("history").path, "log", "--all", globals_=["-n", "2"]).ok()
    six = gitsim.run(shapes.get("history").path, "log", "--all", globals_=["-n", "6"]).ok()
    assert len(two.model["commits"]) < len(six.model["commits"])


def test_all_shows_more_branches(shapes, gitsim):
    one = gitsim.run(shapes.get("classic").path, "log").ok()
    every = gitsim.run(shapes.get("classic").path, "log", globals_=["--all"]).ok()
    assert len(every.model["refs"]) > len(one.model["refs"])


def test_no_all_matches_the_default(shapes, gitsim):
    one = gitsim.run(shapes.get("classic").path, "log").ok()
    explicit = gitsim.run(shapes.get("classic").path, "log", globals_=["--no-all"]).ok()
    assert set(one.model["refs"]) == set(explicit.model["refs"])


def test_hide_merged_branches(shapes, gitsim):
    full = gitsim.run(shapes.get("classic").path, "log", "--all").ok()
    hidden = gitsim.run(shapes.get("classic").path, "log", "--all", globals_=["--hide-merged-branches"]).ok()
    assert len(hidden.model["commits"]) < len(full.model["commits"])
    shown = gitsim.run(shapes.get("classic").path, "log", "--all", globals_=["--no-hide-merged-branches"]).ok()
    assert len(shown.model["commits"]) == len(full.model["commits"])


def test_invert_branches_keeps_the_same_commits(shapes, gitsim):
    plain = gitsim.run(shapes.get("classic").path, "log", "--all").ok()
    inverted = gitsim.run(shapes.get("classic").path, "log", "--all", globals_=["--invert-branches"]).ok()
    upright = gitsim.run(shapes.get("classic").path, "log", "--all", globals_=["--no-invert-branches"]).ok()
    assert set(plain.model["commits"]) == set(inverted.model["commits"]) == set(upright.model["commits"])


def test_reverse_and_no_reverse_keep_the_same_commits(shapes, gitsim):
    plain = gitsim.run(shapes.get("classic").path, "log", "--all").ok()
    forward = gitsim.run(shapes.get("classic").path, "log", "--all", globals_=["--reverse"]).ok()
    old = gitsim.run(shapes.get("classic").path, "log", "--all", globals_=["--no-reverse"]).ok()
    short = gitsim.run(shapes.get("classic").path, "log", "--all", globals_=["-r"]).ok()
    for run in (forward, old, short):
        assert set(run.model["commits"]) == set(plain.model["commits"])
        assert run.model["title"] == plain.model["title"]


@pytest.mark.parametrize("color_by", ["author", "branch"])
def test_color_by(shapes, gitsim, color_by):
    run = gitsim.run(shapes.get("history").path, "log", "--all", globals_=["--color-by", color_by]).ok()
    fills = {el.get("fill") for el in elements(run.path, "commit") if el.tag == f"{SVG}circle"}
    if color_by == "author":
        assert len(fills) >= 2, "several authors, several colours"


def test_highlight_commit_messages(shapes, gitsim):
    plain = gitsim.run(shapes.get("history").path, "log").ok()
    loud = gitsim.run(shapes.get("history").path, "log", globals_=["--highlight-commit-messages"]).ok()
    quiet = gitsim.run(shapes.get("history").path, "log", globals_=["--no-highlight-commit-messages"]).ok()
    assert max(label_font_sizes(loud.path)) > max(label_font_sizes(plain.path))
    assert max(label_font_sizes(quiet.path)) == max(label_font_sizes(plain.path))


@pytest.mark.parametrize("style", ["clean", "thick"])
def test_style(shapes, gitsim, style):
    run = gitsim.run(shapes.get("history").path, "log", globals_=["--style", style]).ok()
    assert run.model["commits"]


def test_max_labels_per_commit(shapes, gitsim):
    one = gitsim.run(shapes.get("history").path, "log", "--all", globals_=["--max-branches-per-commit", "1", "--max-tags-per-commit", "1"]).ok()
    many = gitsim.run(shapes.get("history").path, "log", "--all", globals_=["--max-branches-per-commit", "4", "--max-tags-per-commit", "4"]).ok()
    assert len(many.model["refs"]) >= len(one.model["refs"])


def test_font_option_reaches_the_svg(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", globals_=["--font", "Arial"]).ok()
    root = ET.parse(run.path).getroot()
    assert "Arial" in (root.get("font-family") or "")


def test_title_can_be_switched_off_and_on(shapes, gitsim):
    off = gitsim.run(shapes.get("history").path, "log", globals_=["--no-show-command-as-title"]).ok()
    on = gitsim.run(shapes.get("history").path, "log", globals_=["--show-command-as-title"]).ok()
    assert off.model["title"] == ""
    assert on.model["title"].startswith("git log")


def test_interactive_flag_is_accepted(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "log", fmt="", globals_=["--interactive"]).ok()
    assert run.path.suffix == ".html"


def test_version(gitsim, shapes):
    run = gitsim.run(shapes.get("history").path, fmt="", globals_=["--version"], raw=True)
    assert run.returncode == 0 and re.search(r"\d+\.\d+", run.raw.decode())


def test_environment_variable_sets_an_option(shapes, gitsim):
    """git_sim_<option> in the environment is the same as the flag."""
    env = gitsim.env()
    env["git_sim_light_mode"] = "true"
    proc = subprocess.run(
        [sys.executable, "-m", "git_sim", "-d", "--output-only-path", "--img-format", "svg", "--media-dir", str(gitsim.media), "log"],
        cwd=str(shapes.get("history").path), capture_output=True, text=True, env=env, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    path = proc.stdout.strip().splitlines()[-1]
    assert not background_fill(path).startswith("#0"), "light background from the environment variable"


def test_media_dir_command(shapes, gitsim):
    run = gitsim.run(shapes.get("history").path, "media-dir", fmt="", raw=True)
    assert run.returncode == 0 and run.raw.decode().strip()
