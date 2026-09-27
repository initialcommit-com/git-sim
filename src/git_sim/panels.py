"""Cards drawn under the commit graph for commands whose output isn't a move
between Git's areas (the zone table is for that: working directory, staging
area, stash, repository).

- diffstat_card: the files a diff touches, each with its status, path, line
  counts and a five-block bar, as `git diff --stat` / `git show --stat` print
  them (show, diff, stash show).
- code_card: lines of a file with a gutter colored by the commit each line
  comes from (blame).

Both sit below everything drawn so far, centered on the graph, and use only
theme colors so the interactive page can recolor them for the other theme.
Every file path is tagged role="file" with the card's title as its column, so
the page and the validation suite read them like any other file entry.
"""

from typing import List, Optional, Sequence, Tuple

from git_sim.backend import m
from git_sim.settings import settings

ROW = 0.52  # row height in scene units
PAD = 0.42  # inner padding
BLOCKS = 5  # the diffstat bar, as git and GitHub draw it


def _text(scene, text, size=20, color=None, bold=False):
    return m.Text(
        text,
        font=scene.font,
        font_size=size,
        color=color or scene.fontColor,
        weight=m.BOLD if bold else m.NORMAL,
    )


def _char_width(scene, size):
    probe = _text(scene, "0" * 20, size)
    return probe.width / 20


def _frame(scene, width, height, top_y, center_x):
    card = m.RoundedRectangle(
        corner_radius=0.18,
        width=width,
        height=height,
        color=scene.ruleColor,
        stroke_width=2,
        fill_color=scene.theme.panel,
        fill_opacity=scene.theme.panel_opacity * 1.6,
    )
    card.move_to((center_x, top_y - height / 2, 0))
    scene.tag(card, role="panel")
    return card


def _place(scene, width_hint):
    """Where the card goes: under everything drawn, centered on the graph."""
    group = scene.toFadeOut
    if len(group.submobjects):
        bottom = group.get_bottom()[1]
        center_x = group.get_center()[0]
        width = max(width_hint, group.get_width())
    else:
        bottom, center_x, width = 0.0, 0.0, width_hint
    return bottom - 0.9, center_x, width


def _show(scene, mobs, appear=False):
    """Add the card. With ``appear``, every part of it belongs to the command's
    result: the interactive page fades it in on the same step the command's
    other changes happen (show: as the shown commit turns blue)."""
    if appear:
        for mob in mobs:
            scene.tag(mob, phase="after", with_recolor=True)
    scene.toFadeOut.add(*mobs)
    if settings.animate:
        scene.play(*[m.FadeIn(x) for x in mobs], run_time=1 / settings.speed)
    else:
        scene.add(*mobs)


def sides_strip(scene, old_label: str, new_label: str, old_color: str, new_color: str, old_note: Optional[str] = None):
    """The two things a diff compares, as a row under the graph:
    [from] ---> [to]. The "from" side exists from the start (the page's
    "before" state shows only it); the arrow and the "to" side arrive as the
    command's result, on whatever step the caller has set. ``old_note`` is a
    line under the "from" chip saying what it holds."""

    def chip(label, caption, color):
        text = _text(scene, label, 20, scene.theme.ref_text, bold=True)
        pill = m.RoundedRectangle(
            corner_radius=0.14,
            width=text.width + 0.6,
            height=0.56,
            color=color,
            fill_color=color,
            fill_opacity=1.0,
            stroke_width=0,
        )
        return [pill, text, _text(scene, caption, 16, scene.mutedColor)]

    gap = 1.8
    old = chip(old_label, "from", old_color)
    new = chip(new_label, "to", new_color)
    old_w, new_w = old[0].width, new[0].width
    total = old_w + gap + new_w
    top, center_x, _ = _place(scene, total)
    y = top - 0.55
    left = center_x - total / 2
    for parts, x in ((old, left + old_w / 2), (new, left + old_w + gap + new_w / 2)):
        pill, text, cap = parts
        text.move_to((x, y, 0))
        pill.move_to((x, y, 0))
        cap.next_to(pill, m.UP, buff=0.12)
    if old_note:
        note = _text(scene, old_note, 15, scene.mutedColor)
        note.next_to(old[0], m.DOWN, buff=0.12)
        old.append(note)
    arrow = m.Arrow(
        (left + old_w + 0.15, y, 0),
        (left + old_w + gap - 0.15, y, 0),
        color=scene.mutedColor,
        stroke_width=4,
        buff=0,
    )
    for mob in old:
        scene.tag(mob, phase="before")
    for mob in [arrow, *new]:
        scene.tag(mob, phase="after")
    mobs = [*old, arrow, *new]
    scene.toFadeOut.add(*mobs)
    if settings.animate:
        from git_sim.git_sim_base_command import GrowArrow

        scene.play(*[m.FadeIn(x) for x in old], run_time=1 / settings.speed)
        scene.play(GrowArrow(arrow), *[m.FadeIn(x) for x in new], run_time=1 / settings.speed)
    else:
        scene.add(*mobs)


STATUS_LETTER = {"added": "A", "modified": "M", "deleted": "D", "renamed": "R", "copied": "C", "type changed": "T", "unmerged": "U"}


def diffstat_card(scene, title: str, changes, more: int = 0, subtitle: Optional[str] = None, appear: bool = False):
    """``changes``: FileChange items (git_sim.diffstat). ``more``: how many
    further files the card leaves out."""
    size = 20
    cw = _char_width(scene, size)
    added_color, deleted_color, muted = scene.theme.branch, scene.theme.accent, scene.mutedColor

    rows = []
    longest = max([len(c.path) + (len(c.old_path) + 4 if c.old_path else 0) for c in changes] + [len(title) - 6, 24])
    path_width = min(longest, 56) * cw
    counts_width = 12 * cw
    bar_width = BLOCKS * 0.24
    inner = 0.5 + path_width + 0.5 + counts_width + bar_width
    top, center_x, width = _place(scene, inner + 2 * PAD)
    width = max(width, inner + 2 * PAD)
    lines = len(changes) + (1 if more else 0)
    height = PAD + 0.62 + (0.4 if subtitle else 0) + ROW * max(lines, 1) + PAD
    card = _frame(scene, width, height, top, center_x)
    left = center_x - width / 2 + PAD
    right = center_x + width / 2 - PAD
    mobs = [card]

    head = _text(scene, title, 22, bold=True)
    head.move_to((0, top - PAD - 0.2, 0)).align_to((left, 0, 0), m.LEFT)
    mobs.append(head)
    y = top - PAD - 0.62
    if subtitle:
        sub = _text(scene, subtitle, 17, muted)
        sub.move_to((0, y + 0.02, 0)).align_to((left, 0, 0), m.LEFT)
        mobs.append(sub)
        y -= 0.4
    rule = m.Line((left, y + 0.08, 0), (right, y + 0.08, 0), color=scene.ruleColor, stroke_width=2)
    mobs.append(rule)

    peak = max([(c.added or 0) + (c.deleted or 0) for c in changes] + [1])
    for change in changes:
        cy = y - ROW / 2
        letter = STATUS_LETTER.get(change.status, "?")
        tone = added_color if letter == "A" else deleted_color if letter == "D" else scene.fontColor
        glyph = _text(scene, letter, size, tone, bold=True)
        glyph.move_to((left + 0.15, cy, 0))
        label = change.path if not change.old_path else f"{change.old_path} -> {change.path}"
        path = _text(scene, scene.trim_path(label, 56), size)
        path.move_to((0, cy, 0)).align_to((left + 0.5, 0, 0), m.LEFT)
        scene.tag(path, role="file", name=change.path, column=title, phase="before")
        mobs += [glyph, path]
        # counts, right-aligned before the bar
        bar_left = right - bar_width
        if change.added is None:
            counts = [_text(scene, "binary", size, muted)]
        else:
            counts = [
                _text(scene, f"+{change.added}", size, added_color, bold=True),
                _text(scene, f"-{change.deleted}", size, deleted_color, bold=True),
            ]
        x = bar_left - 0.3
        for t in reversed(counts):
            t.move_to((0, cy, 0)).align_to((x, 0, 0), m.RIGHT)
            x = t.get_left()[0] - 0.22
            mobs.append(t)
        # the bar: added and deleted lines in proportion to the busiest file
        total = (change.added or 0) + (change.deleted or 0)
        filled = 0 if not total else max(1, round(BLOCKS * total / peak))
        green = 0 if not total else round(filled * (change.added or 0) / total)
        for k in range(BLOCKS):
            color = added_color if k < green else deleted_color if k < filled else scene.ruleColor
            block = m.Square(side_length=0.17, color=color, fill_color=color, fill_opacity=1.0, stroke_width=0)
            block.move_to((bar_left + 0.12 + k * 0.24, cy, 0))
            mobs.append(block)
        y -= ROW
    if more:
        extra = _text(scene, f"... and {more} more file(s)", size, muted)
        extra.move_to((0, y - ROW / 2, 0)).align_to((left + 0.5, 0, 0), m.LEFT)
        mobs.append(extra)
    if not changes and not more:
        none = _text(scene, "no changes", size, muted)
        none.move_to((0, y - ROW / 2, 0)).align_to((left + 0.5, 0, 0), m.LEFT)
        mobs.append(none)
    _show(scene, mobs, appear)
    return card


def code_card(scene, title: str, lines: Sequence[Tuple[int, str, Optional[str], str, bool]], more: int = 0, appear: bool = False):
    """``lines``: (line number, text, commit label or None, gutter color,
    first line of its run). The label is drawn as a chip at the start of each
    run of lines from one commit; every line gets its commit's gutter color."""
    size = 19
    cw = _char_width(scene, size)
    num_w = max(len(str(n)) for n, *_ in lines) * cw if lines else cw
    chip_w = 9 * cw + 0.3
    longest = max([len(t) for _, t, *_ in lines] + [30])
    code_w = min(longest, 64) * cw
    inner = 0.2 + chip_w + 0.3 + num_w + 0.4 + code_w
    top, center_x, width = _place(scene, inner + 2 * PAD)
    width = max(width, inner + 2 * PAD)
    height = PAD + 0.62 + ROW * (len(lines) + (1 if more else 0)) + PAD
    card = _frame(scene, width, height, top, center_x)
    left = center_x - width / 2 + PAD
    mobs = [card]
    head = _text(scene, title, 22, bold=True)
    head.move_to((0, top - PAD - 0.2, 0)).align_to((left, 0, 0), m.LEFT)
    mobs.append(head)
    y = top - PAD - 0.62
    mobs.append(m.Line((left, y + 0.08, 0), (center_x + width / 2 - PAD, y + 0.08, 0), color=scene.ruleColor, stroke_width=2))
    for number, text, label, color, first in lines:
        cy = y - ROW / 2
        gutter = m.Rectangle(width=0.08, height=ROW, color=color, fill_color=color, fill_opacity=1.0, stroke_width=0)
        gutter.move_to((left + 0.04, cy, 0))
        mobs.append(gutter)
        if first and label:
            chip = m.RoundedRectangle(corner_radius=0.1, width=chip_w, height=ROW * 0.78, color=color, fill_color=color, fill_opacity=1.0, stroke_width=0)
            chip.move_to((left + 0.2 + chip_w / 2, cy, 0))
            chip_text = _text(scene, label, size - 2, scene.theme.ref_text, bold=True)
            chip_text.move_to(chip.get_center())
            mobs += [chip, chip_text]
        num = _text(scene, str(number), size, scene.mutedColor)
        num_right = left + 0.2 + chip_w + 0.3 + num_w
        num.move_to((0, cy, 0)).align_to((num_right, 0, 0), m.RIGHT)
        mobs.append(num)
        stripped = text.lstrip(" \t")
        indent = len(text.expandtabs(4)) - len(stripped.expandtabs(4))
        if stripped:
            code = _text(scene, stripped[:64] + ("..." if len(stripped) > 64 else ""), size)
            code.move_to((0, cy, 0)).align_to((num_right + 0.4 + indent * cw, 0, 0), m.LEFT)
            mobs.append(code)
        y -= ROW
    if more:
        extra = _text(scene, f"... {more} more line(s)", size, scene.mutedColor)
        extra.move_to((0, y - ROW / 2, 0)).align_to((left + 0.3, 0, 0), m.LEFT)
        mobs.append(extra)
    _show(scene, mobs, appear)
    return card
