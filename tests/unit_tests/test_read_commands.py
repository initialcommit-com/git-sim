"""The read-only commands that look through history: log's filters (paths,
-S, --author, --since/--until, -p, --follow), diff --stat, shortlog, grep
and describe. Scenes are built against a small repository with a few
authors, a renamed file and tags, and checked against what git says."""

import os
import re
import subprocess

import pytest

from git_sim.settings import Settings, settings
from git_sim.theme import theme_for

ADA = ("Ada Lovelace", "ada@example.com")
GRACE = ("Grace Hopper", "grace@example.com")
LINUS = ("Linus Torvalds", "linus@example.com")


def run_git(cwd, *args, who=None, day=None):
    env = dict(os.environ)
    if who:
        env.update(GIT_AUTHOR_NAME=who[0], GIT_AUTHOR_EMAIL=who[1], GIT_COMMITTER_NAME=who[0], GIT_COMMITTER_EMAIL=who[1])
    if day:
        stamp = f"2024-03-{day:02d}T12:00:00"
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """main.py renamed to app.py, three authors, an annotated tag v1.0 two
    commits in and a lightweight tag v1.1-rc, TODOs to search for."""
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    run_git(path, "config", "core.autocrlf", "false")

    def write(name, text):
        (path / name).write_text(text, newline="\n")

    write("main.py", "def main():\n    print('hello')\n")
    write("README.md", "# Demo\n")
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Initial commit", who=ADA, day=1)
    write("main.py", "def main():\n    total = compute_total(orders)\n")
    run_git(path, "commit", "-am", "Compute the total", who=GRACE, day=2)
    run_git(path, "tag", "-a", "v1.0", "-m", "First release", who=GRACE, day=2)
    run_git(path, "mv", "main.py", "app.py")
    run_git(path, "commit", "-m", "Rename main.py to app.py", who=LINUS, day=3)
    write("utils.py", "def compute_total(orders):\n    return sum(orders)  # TODO: tax\n")
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Add utils", who=ADA, day=4)
    run_git(path, "tag", "v1.1-rc")
    write("app.py", "def main():\n    total = compute_total(orders)\n    # TODO: log the TOTAL\n")
    run_git(path, "commit", "-am", "Log a reminder", who=ADA, day=5)
    for key, value in Settings().model_dump().items():
        setattr(settings, key, value)
    settings.auto_open = False
    monkeypatch.chdir(path)
    yield path
    settings.compact = False


def sha(repo, rev):
    return run_git(repo, "rev-parse", rev).strip()


def highlighted(scene):
    return {s for s, c in scene.drawnCommits.items() if "before_fill" in (getattr(c, "meta", None) or {})}


def texts(scene):
    return {
        mob.text
        for top in scene.mobjects
        for mob in top.get_family()
        if hasattr(mob, "text")
    }


def draw(scene, compact=False):
    settings.compact = compact
    scene.compact = compact
    scene.construct()
    return scene.render_svg(background=theme_for(settings.light).bg, extra_mobjects=scene.removed_mobjects)


# -- log ---------------------------------------------------------------------------


def test_plain_log_highlights_nothing_and_keeps_its_title(repo):
    from git_sim.log import Log

    scene = Log(n=None, all=False)
    scene.construct()
    assert scene.cmd == "git log"
    assert not highlighted(scene)
    assert Log(n=3, all=True, oneline=True, graph=True).cmd == "git log --oneline --graph --all -n 3"


def test_log_path_highlights_the_commits_git_lists(repo):
    from git_sim.log import Log

    scene = Log(paths=["app.py"])
    scene.construct()
    listed = run_git(repo, "log", "--format=%H", "--", "app.py").split()
    assert highlighted(scene) == set(listed)
    assert "2 commits changed app.py" in texts(scene)
    assert scene.cmd == "git log -- app.py"


def test_log_follow_goes_past_the_rename_and_says_so(repo):
    from git_sim.log import Log

    scene = Log(paths=["app.py"], follow=True)
    scene.construct()
    listed = run_git(repo, "log", "--follow", "--format=%H", "--", "app.py").split()
    assert len(listed) == 4
    assert highlighted(scene) == set(listed)
    assert "4 commits changed app.py, following its rename from main.py" in texts(scene)


def test_log_without_follow_points_at_the_rename(repo):
    from git_sim.log import Log

    scene = Log(paths=["app.py"])
    scene.construct()
    assert any("--follow goes further back" in t for t in texts(scene))


def test_log_pickaxe_author_and_dates(repo):
    from git_sim.log import Log

    todo = Log(search="TODO")
    todo.construct()
    assert highlighted(todo) == {sha(repo, "HEAD"), sha(repo, "HEAD~1")}
    assert '2 commits added or removed "TODO"' in texts(todo)

    ada = Log(author="Ada", since="2024-03-03", until="2024-03-04T23:00")
    ada.construct()
    assert highlighted(ada) == {sha(repo, "HEAD~1")}
    assert ada.cmd == "git log --author Ada --since 2024-03-03 --until 2024-03-04T23:00"


def test_log_with_nothing_matching_says_so(repo):
    from git_sim.log import Log

    scene = Log(author="Nobody")
    scene.construct()
    assert not highlighted(scene)
    assert "No commits by Nobody" in texts(scene)


def test_log_patch_shows_the_newest_listed_commits_changes(repo):
    from git_sim.log import Log

    scene = Log(paths=["app.py"], patch=True)
    scene.construct()
    shown = texts(scene)
    assert f"The patch of {sha(repo, 'HEAD')[:7]}" in shown
    assert "+    # TODO: log the TOTAL" in shown


def test_log_filters_drawn_compact_keep_the_card_and_drop_the_prose(repo):
    from git_sim.log import Log

    full = draw(Log(paths=["app.py"]))
    small = draw(Log(paths=["app.py"]), compact=True)
    assert 'data-role="note"' in full and 'data-role="title"' in full
    assert 'data-role="note"' not in small and 'data-role="title"' not in small
    assert "2 commits changed app.py" in small
    # the card is framed: the view box reaches below its bottom edge
    box = [float(v) for v in re.search(r'viewBox="([-\d. ]+)"', small).group(1).split()]
    panels = [float(y) + float(h) for y, h in re.findall(r'<rect [^>]*y="([-\d.]+)"[^>]*height="([\d.]+)"[^>]*data-role="panel"', small)]
    assert panels and max(panels) <= box[1] + box[3]


def test_parse_patch_numbers_lines_on_their_side():
    from git_sim.log import parse_patch

    out = "diff --git a/x.py b/x.py\nindex 1..2 100644\n--- a/x.py\n+++ b/x.py\n@@ -3,2 +3,2 @@ def f():\n     keep\n-    old\n+    new\n"
    ((path, lines),) = parse_patch(out)
    assert path == "x.py"
    assert lines == [(None, "@@ -3,2 +3,2 @@", "@"), (3, "     keep", " "), (4, "-    old", "-"), (4, "+    new", "+")]


def test_log_refuses_follow_with_two_files_and_unknown_paths(repo, capsys):
    from git_sim.log import Log

    with pytest.raises(SystemExit):
        Log(paths=["app.py", "utils.py"], follow=True)
    assert "exactly one file" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        Log(paths=["nope.py"])
    # a file that is gone still has a history
    assert Log(paths=["main.py"]).cmd == "git log -- main.py"


# -- diff --stat --------------------------------------------------------------------


def test_diff_stat_words_the_summary_as_git_does(repo):
    from git_sim.diff import Diff, stat_summary

    assert stat_summary(3, 10, 2) == "3 files changed, 10 insertions(+), 2 deletions(-)"
    assert stat_summary(1, 1, 0) == "1 file changed, 1 insertion(+)"
    scene = Diff(args=["HEAD~2..HEAD"], stat=True)
    scene.construct()
    assert scene.cmd == "git diff --stat HEAD~2..HEAD"
    expected = run_git(repo, "diff", "--stat", "HEAD~2", "HEAD").strip().splitlines()[-1].strip()
    assert expected in texts(scene)


def test_diff_two_commits_and_a_range_compare_the_same(repo):
    from git_sim.diff import Diff

    two, dots = Diff(args=["HEAD~2", "HEAD"]), Diff(args=["HEAD~2..HEAD"])
    assert two.diff_args == dots.diff_args


# -- shortlog -----------------------------------------------------------------------


def test_shortlog_counts_authors_and_colors_their_commits(repo):
    from git_sim.shortlog import Shortlog

    scene = Shortlog(summary=True, numbered=True)
    assert scene.cmd == "git shortlog -sn"
    ranked = scene.authors()
    assert [(name, len(c)) for name, c in ranked] == [("Ada Lovelace", 3), ("Grace Hopper", 1), ("Linus Torvalds", 1)]
    scene.construct()
    shown = texts(scene)
    assert "5 commits in HEAD by 3 authors" in shown
    circles = scene.drawnCommits
    ada = {c.hexsha for c in scene.repo.iter_commits("HEAD", author="Ada")}
    colors = {circles[s].fill_color for s in ada}
    assert len(colors) == 1, "one author's commits share one color"
    assert colors != {circles[sha(repo, "HEAD~2")].fill_color}


def test_shortlog_lists_subjects_without_s_and_emails_with_e(repo):
    from git_sim.shortlog import Shortlog

    scene = Shortlog(email=True)
    scene.construct()
    shown = texts(scene)
    assert "Ada Lovelace <ada@example.com>" in shown
    assert "Initial commit" in shown  # oldest first, as git shortlog lists them
    assert "... and 1 more" in shown


def test_shortlog_of_a_range_counts_only_its_commits(repo):
    from git_sim.shortlog import Shortlog

    scene = Shortlog(rev="v1.0..HEAD", summary=True)
    scene.construct()
    assert highlighted(scene) == set(run_git(repo, "rev-list", "v1.0..HEAD").split())


def test_shortlog_refuses_an_unknown_revision(repo, capsys):
    from git_sim.shortlog import Shortlog

    with pytest.raises(SystemExit):
        Shortlog(rev="nope")
    assert "git-sim error" in capsys.readouterr().out


# -- grep ---------------------------------------------------------------------------


def test_parse_matches_takes_the_spans_from_gits_colors():
    from git_sim.grep import parse_matches

    out = "HEAD:a.py\x002\x00\tx = \x1b[7mtodo\x1b[m + \x1b[7mTODO\x1b[m\r\n"
    found = parse_matches(out, "HEAD:")
    assert found == {"a.py": [(2, "    x = todo + TODO", [(8, 12), (15, 19)])]}


def test_grep_groups_matches_by_file(repo):
    from git_sim.grep import Grep

    scene = Grep(pattern="TODO", line_number=True)
    assert set(scene.found) == {"app.py", "utils.py"}
    assert scene.found["app.py"][0][0] == 3
    svg = draw(scene)
    assert 'data-name="utils.py"' in svg
    assert "2 lines in 2 files match" in svg


def test_grep_ignore_case_and_a_revision(repo):
    from git_sim.grep import Grep

    scene = Grep(pattern="total", args=["v1.0"], ignore_case=True)
    # v1.0 has main.py only, before the rename
    assert list(scene.found) == ["main.py"]
    ((number, text, spans),) = scene.found["main.py"]
    assert [text[a:b] for a, b in spans] == ["total", "total"]
    scene.construct()
    assert highlighted(scene) == {sha(repo, "v1.0^{commit}")}
    assert scene.cmd == "git grep -i total v1.0"


def test_grep_paths_and_no_match(repo):
    from git_sim.grep import Grep

    scene = Grep(pattern="TODO", args=["--", "utils.py"])
    assert list(scene.found) == ["utils.py"]
    empty = Grep(pattern="zzz-nowhere")
    empty.construct()
    assert 'No line matches "zzz-nowhere"' in texts(empty)


def test_grep_drawn_compact_without_a_revision_is_just_the_card(repo):
    from git_sim.grep import Grep

    small = draw(Grep(pattern="TODO"), compact=True)
    assert 'data-role="commit"' not in small
    assert 'data-name="app.py"' in small
    with_rev = draw(Grep(pattern="TODO", args=["HEAD"]), compact=True)
    assert 'data-role="commit"' in with_rev


def test_grep_refuses_an_unknown_argument_and_a_bad_pattern(repo, capsys):
    from git_sim.grep import Grep

    with pytest.raises(SystemExit):
        Grep(pattern="TODO", args=["nope"])
    with pytest.raises(SystemExit):
        Grep(pattern="[")
    assert "git grep refused" in capsys.readouterr().out


def test_clip_line_keeps_the_match_in_view():
    from git_sim.panels import clip_line

    text = "x" * 100 + "NEEDLE" + "y" * 100
    clipped, spans = clip_line(text, [(100, 106)], limit=40)
    assert len(clipped) == 40
    assert [clipped[a:b] for a, b in spans] == ["NEEDLE"]
    assert clipped.startswith("...") and clipped.endswith("...")


# -- describe -----------------------------------------------------------------------


def test_describe_names_the_commit_after_the_annotated_tag(repo):
    from git_sim.describe import Describe

    scene = Describe()
    expected = run_git(repo, "describe").strip()
    assert scene.result == expected and expected.startswith("v1.0-3-g")
    scene.construct()
    since = set(run_git(repo, "rev-list", "v1.0..HEAD").split())
    assert highlighted(scene) == since | {sha(repo, "v1.0^{commit}")}
    assert expected in scene.drawnRefs
    assert "3" in texts(scene)


def test_describe_tags_counts_lightweight_tags(repo):
    from git_sim.describe import Describe

    scene = Describe(tags=True)
    assert scene.result == run_git(repo, "describe", "--tags").strip()
    assert scene.tag_name == "v1.1-rc" and scene.distance == 1
    exact = Describe(commit="v1.1-rc", tags=True)
    assert exact.result == "v1.1-rc" and exact.distance == 0
    exact.construct()
    assert "v1.1-rc" in exact.drawnRefs


def test_describe_explains_why_git_has_no_name(repo, tmp_path, capsys, monkeypatch):
    from git_sim.describe import Describe

    with pytest.raises(SystemExit):
        Describe(commit="HEAD~4")  # the first commit, before any tag
    assert "no tag is in HEAD~4's history" in capsys.readouterr().out

    run_git(repo, "tag", "-d", "v1.0")
    with pytest.raises(SystemExit):
        Describe()
    assert "try --tags" in capsys.readouterr().out

    run_git(repo, "tag", "-d", "v1.1-rc")
    with pytest.raises(SystemExit):
        Describe(tags=True)
    assert "has no tags" in capsys.readouterr().out


def test_describe_compact_keeps_the_card_and_the_label(repo):
    from git_sim.describe import Describe

    scene = Describe(commit="HEAD~1")
    svg = draw(scene, compact=True)
    assert 'data-role="title"' not in svg
    assert re.search(r"v1\.0-2-g[0-9a-f]+", svg)
