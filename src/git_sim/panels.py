"""Cards drawn under the commit graph for commands whose output isn't a move
between Git's areas (the zone table is for that: working directory, staging
area, stash, repository).

- diffstat_card: the files a diff touches, each with its status, path, line
  counts and a five-block bar, as `git diff --stat` / `git show --stat` print
  them (show, diff, stash show).
- code_card: lines of a file with a gutter colored by the commit each line
  comes from (blame).
- chip_list_card: rows that each start with a colored chip, such as a
  commit id with its subject (log's matches) or the parts of a name
  (describe).
- bars_card: names ranked with a count and a bar each (shortlog).
- file_lines_card: lines grouped under their file, with parts of a line
  highlighted (grep's matches) or colored by kind (log -p's patch).
- patch_card: a patch line by line, as -p prints it (stash show -p).
- list_card: rows of aligned columns, some highlighted, some arriving with
  the command or struck through by it (branch and tag listings, the
  [branch "x"] lines branch -u writes, an annotated tag's object).

All sit below everything drawn so far, centered on the graph, and use only
theme colors so the interactive page can recolor them for the other theme.
Every file path is tagged role="file" with the card's title as its column, so
the page and the validation suite read them like any other file entry.
"""

from dataclasses import dataclass, field
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


def patch_rows(patch: str):
    """git diff's output as (kind, text, path) rows: a "file" row naming each
    file, then its hunks' "hunk" (@@) rows and their "added", "deleted" and
    "context" lines. The header lines git prints above a file's hunks (diff
    --git, index, ---, +++, mode lines) fold into its one "file" row."""
    rows, old = [], None
    for line in patch.splitlines():
        if line.startswith("--- "):
            old = line[4:]
        elif line.startswith("+++ "):
            new = line[4:]
            path = old if new == "/dev/null" else new
            path = path[2:] if path[:2] in ("a/", "b/") else path
            rows.append(("file", path, path))
        elif line.startswith(("diff --git", "index ", "new file mode", "deleted file mode", "old mode", "new mode", "similarity", "rename ", "Binary files", "\\ No newline")):
            continue
        elif line.startswith("@@"):
            rows.append(("hunk", line, None))
        elif line.startswith("+"):
            rows.append(("added", line, None))
        elif line.startswith("-"):
            rows.append(("deleted", line, None))
        else:
            rows.append(("context", line, None))
    return rows


def patch_card(scene, title: str, patch: str, max_rows: int = 24, subtitle: Optional[str] = None, appear: bool = False):
    """A patch as git prints it with -p (git stash show -p): each file's name,
    then its hunks, added lines green and deleted lines red. Rows past
    ``max_rows`` are counted on a last line instead of drawn."""
    size = 19
    cw = _char_width(scene, size)
    rows = patch_rows(patch)
    shown, more = rows[:max_rows], max(0, len(rows) - max_rows)
    longest = max([len(t) for _, t, _ in shown] + [len(title), 30])
    inner = min(longest, 64) * cw + 0.4
    top, center_x, width = _place(scene, inner + 2 * PAD)
    width = max(width, inner + 2 * PAD)
    lines = len(shown) + (1 if more else 0)
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
        sub = _text(scene, subtitle, 17, scene.mutedColor)
        sub.move_to((0, y + 0.02, 0)).align_to((left, 0, 0), m.LEFT)
        mobs.append(sub)
        y -= 0.4
    mobs.append(m.Line((left, y + 0.08, 0), (right, y + 0.08, 0), color=scene.ruleColor, stroke_width=2))
    tones = {
        "file": scene.fontColor,
        "hunk": scene.mutedColor,
        "added": scene.theme.branch,
        "deleted": scene.theme.accent,
        "context": scene.fontColor,
    }
    for kind, text, path in shown:
        cy = y - ROW / 2
        if kind == "file":
            label = _text(scene, scene.trim_path(text, 56), size + 1, bold=True)
            scene.tag(label, role="file", name=path, column=title, phase="before")
        else:
            shown_text = text[:64] + ("..." if len(text) > 64 else "")
            label = _text(scene, shown_text, size, tones[kind]) if shown_text.strip() else None
        if label is not None:
            label.move_to((0, cy, 0)).align_to((left + (0 if kind == "file" else 0.2), 0, 0), m.LEFT)
            mobs.append(label)
        y -= ROW
    if more:
        extra = _text(scene, f"... {more} more line(s)", size, scene.mutedColor)
        extra.move_to((0, y - ROW / 2, 0)).align_to((left + 0.2, 0, 0), m.LEFT)
        mobs.append(extra)
    if not rows:
        none = _text(scene, "no changes", size, scene.mutedColor)
        none.move_to((0, y - ROW / 2, 0)).align_to((left + 0.2, 0, 0), m.LEFT)
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


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _header(scene, title, subtitle, top, left, right):
    """The card's title, its subtitle and the rule under them. Returns the
    parts and the y the first row starts at."""
    head = _text(scene, title, 22, bold=True)
    head.move_to((0, top - PAD - 0.2, 0)).align_to((left, 0, 0), m.LEFT)
    mobs = [head]
    y = top - PAD - 0.62
    if subtitle:
        sub = _text(scene, subtitle, 17, scene.mutedColor)
        sub.move_to((0, y + 0.02, 0)).align_to((left, 0, 0), m.LEFT)
        mobs.append(sub)
        y -= 0.4
    mobs.append(m.Line((left, y + 0.08, 0), (right, y + 0.08, 0), color=scene.ruleColor, stroke_width=2))
    return mobs, y


def _header_width(scene, title, subtitle):
    widths = [_text(scene, title, 22, bold=True).width]
    if subtitle:
        widths.append(_text(scene, subtitle, 17).width)
    return max(widths)


def _row(mob, x, cy, edge=m.LEFT):
    """A row's text at ``x`` (its left edge, its right edge, or with no
    edge its center), with its capitals centered on the row, so a line with
    descenders sits level with one without."""
    mob.move_to((x if edge is None else 0, cy, 0))
    if edge is not None:
        mob.align_to((x, 0, 0), edge)
    if hasattr(mob, "center_on_caps"):
        mob.center_on_caps((mob.get_center()[0], cy, 0))
    return mob


def _chip(scene, label, color, x_left, cy, width, size):
    chip = m.RoundedRectangle(
        corner_radius=0.1, width=width, height=ROW * 0.78, color=color, fill_color=color, fill_opacity=1.0, stroke_width=0
    )
    chip.move_to((x_left + width / 2, cy, 0))
    text = _text(scene, label, size, scene.theme.ref_text, bold=True)
    _row(text, x_left + width / 2, cy, None)
    return [chip, text]


def chip_list_card(
    scene,
    title: str,
    rows: Sequence[Tuple[str, str, str, Optional[str]]],
    subtitle: Optional[str] = None,
    more: Optional[str] = None,
    empty: str = "nothing to list",
    appear: bool = False,
):
    """``rows``: (chip text, chip color, text, detail or None). The detail is
    set muted at the right edge. ``more``: a closing line for rows left out."""
    size = 19
    cw = _char_width(scene, size)
    chip_w = max([len(r[0]) for r in rows] + [7]) * _char_width(scene, size - 2) + 0.4
    text_w = max([len(_cut(r[2], 52)) for r in rows] + [16]) * cw
    detail_w = max([len(_cut(r[3] or "", 32)) for r in rows] + [0]) * cw
    inner = max(chip_w + 0.3 + text_w + (0.6 + detail_w if detail_w else 0), _header_width(scene, title, subtitle))
    top, center_x, width = _place(scene, inner + 2 * PAD)
    width = max(width, inner + 2 * PAD)
    lines = max(len(rows), 1) + (1 if more else 0)
    height = PAD + 0.62 + (0.4 if subtitle else 0) + ROW * lines + PAD
    card = _frame(scene, width, height, top, center_x)
    left, right = center_x - width / 2 + PAD, center_x + width / 2 - PAD
    head, y = _header(scene, title, subtitle, top, left, right)
    mobs = [card, *head]
    for label, color, text, detail in rows:
        cy = y - ROW / 2
        mobs += _chip(scene, label, color, left, cy, chip_w, size - 2)
        body = _text(scene, _cut(text, 52), size)
        _row(body, left + chip_w + 0.3, cy)
        mobs.append(body)
        if detail:
            aside = _text(scene, _cut(detail, 32), size - 2, scene.mutedColor)
            _row(aside, right, cy, m.RIGHT)
            mobs.append(aside)
        y -= ROW
    if not rows:
        none = _text(scene, empty, size, scene.mutedColor)
        none.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
        mobs.append(none)
        y -= ROW
    if more:
        extra = _text(scene, more, size, scene.mutedColor)
        extra.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
        mobs.append(extra)
    _show(scene, mobs, appear)
    return card


BAR_WIDTH = 3.2  # the longest bar of a bars_card


def bars_card(
    scene,
    title: str,
    rows: Sequence[Tuple[str, int, str, Sequence[str]]],
    subtitle: Optional[str] = None,
    more: Optional[str] = None,
    appear: bool = False,
):
    """``rows``: (name, count, color, lines). Each row is the count, the name
    and a bar in the row's color as long as the count against the largest;
    ``lines`` are set muted under the name (shortlog lists an author's
    commit subjects there)."""
    size = 19
    cw = _char_width(scene, size)
    count_w = max([len(str(r[1])) for r in rows] + [2]) * cw
    name_w = max([len(_cut(r[0], 40)) for r in rows] + [12]) * cw
    sub_w = max([len(_cut(line, 56)) for r in rows for line in r[3]] + [0]) * _char_width(scene, size - 2)
    inner = max(count_w + 0.4 + max(name_w + 0.5 + BAR_WIDTH, 0.3 + sub_w), _header_width(scene, title, subtitle))
    top, center_x, width = _place(scene, inner + 2 * PAD)
    width = max(width, inner + 2 * PAD)
    sub_row = ROW * 0.8
    height = PAD + 0.62 + (0.4 if subtitle else 0) + ROW * (max(len(rows), 1) + (1 if more else 0))
    height += sub_row * sum(len(r[3]) for r in rows) + PAD
    card = _frame(scene, width, height, top, center_x)
    left, right = center_x - width / 2 + PAD, center_x + width / 2 - PAD
    head, y = _header(scene, title, subtitle, top, left, right)
    mobs = [card, *head]
    peak = max([r[1] for r in rows] + [1])
    name_left = left + count_w + 0.4
    bar_left = right - BAR_WIDTH
    for name, count, color, lines in rows:
        cy = y - ROW / 2
        number = _text(scene, str(count), size, color, bold=True)
        _row(number, left + count_w, cy, m.RIGHT)
        label = _text(scene, _cut(name, 40), size)
        _row(label, name_left, cy)
        length = max(0.08, BAR_WIDTH * count / peak)
        bar = m.RoundedRectangle(
            corner_radius=0.06, width=length, height=ROW * 0.5, color=color, fill_color=color, fill_opacity=1.0, stroke_width=0
        )
        bar.move_to((bar_left + length / 2, cy, 0))
        mobs += [number, label, bar]
        y -= ROW
        for line in lines:
            sub = _text(scene, _cut(line, 56), size - 2, scene.mutedColor)
            sub.move_to((0, y - sub_row / 2, 0)).align_to((name_left + 0.3, 0, 0), m.LEFT)
            mobs.append(sub)
            y -= sub_row
    if not rows:
        none = _text(scene, "no commits", size, scene.mutedColor)
        none.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
        mobs.append(none)
        y -= ROW
    if more:
        extra = _text(scene, more, size, scene.mutedColor)
        extra.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
        mobs.append(extra)
    _show(scene, mobs, appear)
    return card


LINE_CHARS = 72  # the most of a line a file_lines_card shows


def _advance(scene, size):
    """How far the pen moves per character (the font is monospaced)."""
    return (_text(scene, "0" * 41, size).width - _text(scene, "0", size).width) / 40


def _set_at(mob, x, cy):
    """Start a text's pen at ``x`` with its capitals centered on ``cy``, so
    pieces of one line share a baseline and keep their columns. Without the
    static renderer's metrics (manim), its ink is placed there instead."""
    if hasattr(mob, "center_on_caps") and hasattr(mob, "_origin_offset"):
        mob.center_on_caps((x, cy, 0))
        pen = mob.get_center()[0] + mob._origin_offset[0] * mob._font_scale
        mob.shift((x - pen, 0, 0))
    else:
        mob.move_to((0, cy, 0)).align_to((x, 0, 0), m.LEFT)
    return mob


def clip_line(text: str, spans: Sequence[Tuple[int, int]], limit: int = LINE_CHARS):
    """A long line cut down to ``limit`` characters around its first
    highlighted part, with "..." where it was cut; the spans move with it."""
    if len(text) <= limit:
        return text, list(spans)
    start = max(0, (spans[0][0] if spans else 0) - 16)
    start = min(start, max(0, len(text) - limit))
    lead = "..." if start else ""
    room = limit - len(lead)
    tail = "..." if start + room < len(text) else ""
    room -= len(tail)
    body = text[start : start + room]
    shift = len(lead) - start
    kept = []
    for a, b in spans:
        a, b = max(a + shift, len(lead)), min(b + shift, len(lead) + len(body))
        if a < b:
            kept.append((a, b))
    return lead + body + tail, kept


def file_lines_card(
    scene,
    title: str,
    groups: Sequence[Tuple[str, Sequence[Tuple[Optional[int], str, Sequence[Tuple[int, int]], Optional[str]]]]],
    subtitle: Optional[str] = None,
    more: Optional[str] = None,
    numbers: bool = True,
    empty: str = "nothing to show",
    appear: bool = False,
):
    """``groups``: (path, lines), each line (number or None, text, spans,
    color or None). A line with a color gets a gutter and its text in that
    color (a patch's added and removed lines); ``spans`` are (start, end)
    character ranges drawn highlighted (the text grep matched). Each path
    is tagged as a file in a column named after the card's title."""
    size = 18
    cw = _advance(scene, size)
    all_lines = [line for _, lines in groups for line in lines]
    num_w = (max([len(str(n)) for n, *_ in all_lines if n is not None] + [1]) * cw) if numbers else 0
    text_left_offset = 0.25 + (num_w + 0.35 if numbers else 0)
    longest = max([len(t) for _, t, *_ in all_lines] + [len(p) for p, _ in groups] + [24])
    inner = max(text_left_offset + min(longest, LINE_CHARS) * cw, _header_width(scene, title, subtitle))
    top, center_x, width = _place(scene, inner + 2 * PAD)
    width = max(width, inner + 2 * PAD)
    rows = len(groups) + len(all_lines) + (1 if more else 0) + (0 if groups else 1)
    height = PAD + 0.62 + (0.4 if subtitle else 0) + ROW * rows + PAD
    card = _frame(scene, width, height, top, center_x)
    left, right = center_x - width / 2 + PAD, center_x + width / 2 - PAD
    head, y = _header(scene, title, subtitle, top, left, right)
    mobs = [card, *head]
    text_left = left + text_left_offset
    mark = scene.theme.gold
    for path, lines in groups:
        cy = y - ROW / 2
        name = _text(scene, scene.trim_path(path, 64), size, bold=True)
        _row(name, left, cy)
        scene.tag(name, role="file", name=path, column=title, phase="before")
        mobs.append(name)
        y -= ROW
        for number, text, spans, color in lines:
            cy = y - ROW / 2
            if color:
                gutter = m.Rectangle(width=0.07, height=ROW, color=color, fill_color=color, fill_opacity=1.0, stroke_width=0)
                gutter.move_to((left + 0.035, cy, 0))
                mobs.append(gutter)
            if numbers and number is not None:
                num = _text(scene, str(number), size, scene.mutedColor)
                _row(num, left + 0.25 + num_w, cy, m.RIGHT)
                mobs.append(num)
            text, spans = clip_line(text, spans)
            # the line in pieces, each at its own column, with a marker
            # behind every highlighted one
            cuts = sorted({0, len(text), *[i for span in spans for i in span]})
            for a, b in zip(cuts, cuts[1:]):
                piece = text[a:b]
                lit = any(s <= a and b <= e for s, e in spans)
                if lit:
                    marker = m.RoundedRectangle(
                        corner_radius=0.05,
                        width=(b - a) * cw + 0.06,
                        height=ROW * 0.74,
                        color=mark,
                        fill_color=mark,
                        fill_opacity=0.35,
                        stroke_width=0,
                    )
                    marker.move_to((text_left + (a + b) / 2 * cw, cy, 0))
                    mobs.append(marker)
                stripped = piece.lstrip(" ")
                if not stripped.strip():
                    continue
                at = a + len(piece) - len(stripped)
                word = _text(scene, stripped.rstrip(" "), size, color or scene.fontColor)
                mobs.append(_set_at(word, text_left + at * cw, cy))
            y -= ROW
    if not groups:
        none = _text(scene, empty, size, scene.mutedColor)
        none.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
        mobs.append(none)
        y -= ROW
    if more:
        extra = _text(scene, more, size, scene.mutedColor)
        extra.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
        mobs.append(extra)
    _show(scene, mobs, appear)
    return card


@dataclass
class Row:
    """One line of a list_card. ``cells`` are strings or (text, color, bold)
    tuples, lined up in columns across the rows; a ``span`` row ignores the
    columns (a heading, a line of prose) and lays its cells one after another."""

    cells: Sequence = field(default_factory=tuple)
    band: Optional[str] = None  # a highlight behind the row, in this color
    phase: str = "before"  # "after": the command writes the row
    struck: bool = False  # the command strikes the row through
    span: bool = False
    indent: float = 0.0
    column: int = 0  # the column a span row starts in


def list_card(scene, title: str, rows: Sequence[Row], subtitle: Optional[str] = None, appear: bool = False, size: int = 20, gap: float = 0.5):
    """Rows of aligned columns under the graph, as wide as they need (git
    branch -vv, git tag -l, the lines a command writes to .git/config). A
    row with ``phase="after"`` fades in with the command; a ``struck`` row is
    there before and crossed out after. With ``appear`` the whole card is the
    command's result."""
    muted = scene.mutedColor

    def cell(value):
        text, color, bold = (value, None, False) if isinstance(value, str) else (tuple(value) + (None, False))[:3]
        return _text(scene, text, size, color, bold) if text else None

    ncols = max([len(r.cells) for r in rows if not r.span] + [0])
    widths = [0.0] * ncols
    built = [[cell(c) for c in row.cells] for row in rows]
    for row, mobs in zip(rows, built):
        if not row.span:
            for i, x in enumerate(mobs):
                if x is not None:
                    widths[i] = max(widths[i], x.width)
    # where each column starts, from the card's inner left edge
    offsets = [0.0]
    for w in widths[:-1]:
        offsets.append(offsets[-1] + w + gap)
    span_width = 0.0
    for row, mobs in zip(rows, built):
        shown = [x for x in mobs if x is not None]
        if row.span:
            start = offsets[min(row.column, len(offsets) - 1)] + row.indent
            span_width = max(span_width, start + sum(x.width for x in shown) + gap * max(len(shown) - 1, 0))
    head = _text(scene, title, 22, bold=True)
    sub = _text(scene, subtitle, 17, muted) if subtitle else None
    columns = sum(widths) + gap * max(ncols - 1, 0)
    inner = max(columns, span_width, head.width, sub.width if sub else 0.0)
    width = inner + 2 * PAD
    top, center_x, _ = _place(scene, width)
    height = PAD + 0.62 + (0.4 if sub else 0) + ROW * max(len(rows), 1) + PAD
    card = _frame(scene, width, height, top, center_x)
    left = center_x - width / 2 + PAD
    right = center_x + width / 2 - PAD

    head.move_to((0, top - PAD - 0.2, 0)).align_to((left, 0, 0), m.LEFT)
    y = top - PAD - 0.62
    heading = [head]
    if sub:
        sub.move_to((0, y + 0.02, 0)).align_to((left, 0, 0), m.LEFT)
        heading.append(sub)
        y -= 0.4
    heading.append(m.Line((left, y + 0.08, 0), (right, y + 0.08, 0), color=scene.ruleColor, stroke_width=2))

    bands, texts, marks = [], [], []
    for row, mobs in zip(rows, built):
        cy = y - ROW / 2
        placed = []
        x = left + (offsets[min(row.column, len(offsets) - 1)] if row.span else 0) + row.indent
        for i, mob in enumerate(mobs):
            if mob is None:
                continue
            at = x if row.span else left + offsets[i] + row.indent
            mob.move_to((0, cy, 0)).align_to((at, 0, 0), m.LEFT)
            if hasattr(mob, "center_on_caps"):
                # one baseline across the row, whatever the letters' descenders
                mob.center_on_caps((mob.get_center()[0], cy, 0))
            x = mob.get_right()[0] + gap
            placed.append(mob)
        after = row.phase == "after"
        if row.band:
            band = m.RoundedRectangle(corner_radius=0.1, width=inner + 0.3, height=ROW - 0.06, color=row.band, fill_color=row.band, fill_opacity=0.18, stroke_width=0)
            band.move_to((center_x, cy, 0))
            if after:
                scene.tag(band, phase="after")
            bands.append(band)
        for mob in placed:
            if after:
                scene.tag(mob, phase="after")
            texts.append(mob)
        if row.struck and placed:
            wash = m.RoundedRectangle(corner_radius=0.1, width=inner + 0.3, height=ROW - 0.06, color=scene.theme.commit, fill_color=scene.theme.commit, fill_opacity=0.12, stroke_width=0)
            wash.move_to((center_x, cy, 0))
            strike = m.Line((placed[0].get_left()[0] - 0.05, cy, 0), (placed[-1].get_right()[0] + 0.05, cy, 0), color=scene.theme.commit, stroke_width=4)
            scene.tag(wash, phase="after")
            scene.tag(strike, phase="after")
            bands.append(wash)
            marks.append(strike)
        y -= ROW
    if not rows:
        none = _text(scene, "(none)", size, muted)
        none.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
        texts.append(none)
    _show(scene, [card, *bands, *heading, *texts, *marks], appear)
    return card
