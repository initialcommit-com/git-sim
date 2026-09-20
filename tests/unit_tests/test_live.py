"""Live mode: reading the repository, naming what changed, merging two
drawings into one animated graph, the live page, and the command."""

import json
import os
import re
import subprocess
import sys

import pytest

from git_sim.live import (
    LiveSession,
    RepoState,
    describe_change,
    new_reflog_entries,
    read_state,
)
from git_sim.render.merge import (
    Frame,
    displacement,
    is_animated,
    merge_svgs,
    transform_between,
)
from git_sim.settings import Settings, settings


def run_git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Three commits on main and a feature branch one behind; settings reset."""
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-q", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    for i in range(1, 4):
        (path / f"file{i}.txt").write_text(f"content {i}\n")
        run_git(path, "add", ".")
        run_git(path, "commit", "-q", "-m", f"commit {i}")
    run_git(path, "branch", "feature", "HEAD~1")
    for key, value in Settings().model_dump().items():
        setattr(settings, key, value)
    settings.auto_open = False
    settings.media_dir = str(tmp_path / "media")
    return path


# ------------------------------------------------------------ the camera maths
def svg_root(scale, cx, cy, body, view_box="0 0 1920 1080"):
    return (
        f'<svg id="scene" xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" '
        f'width="1920" height="1080" data-scale="{scale}" data-center="{cx} {cy}" '
        f'data-frame="1920 1080"><rect x="0" y="0" width="1920" height="1080" '
        f'fill="#000000" data-role="background"/>{body}</svg>'
    )


def test_reprojection_sends_a_scene_point_to_the_same_pixel():
    import xml.etree.ElementTree as ET

    a = Frame(ET.fromstring(svg_root(100.0, 0.0, 0.0, "")))
    b = Frame(ET.fromstring(svg_root(50.0, 2.0, -1.0, "")))
    k, tx, ty = transform_between(a, b)
    # scene point (3, 1): under a -> (960 + 300, 540 - 100); under b -> (960 + 50, 540 - 100)
    x, y = 1260.0, 440.0
    assert (round(k * x + tx, 6), round(k * y + ty, 6)) == (1010.0, 440.0)
    # scene point (2, -1) is b's centre: it lands mid-frame
    assert (round(k * 1160.0 + tx, 6), round(k * 640.0 + ty, 6)) == (960.0, 540.0)
    assert k == 0.5


def test_displacement_tells_translations_from_reshapes():
    import xml.etree.ElementTree as ET

    a = ET.fromstring('<circle cx="10" cy="20" r="5"/>')
    b = ET.fromstring('<circle cx="40" cy="20" r="5"/>')
    assert displacement(a, b) == (-30.0, 0.0)
    assert displacement(a, ET.fromstring('<circle cx="10" cy="20" r="5"/>')) == (
        0.0,
        0.0,
    )
    assert displacement(a, ET.fromstring('<circle cx="10" cy="20" r="9"/>')) is None
    p = ET.fromstring('<path d="M 0 0 C 10 0, 20 0, 30 0"/>')
    q = ET.fromstring('<path d="M 5 2 C 15 2, 25 2, 35 2"/>')
    assert displacement(p, q) == (-5.0, -2.0)
    r = ET.fromstring('<path d="M 5 2 C 15 2, 25 9, 35 2"/>')
    assert displacement(p, r) is None


def test_merge_marks_what_appeared_moved_and_went_away():
    before = svg_root(
        100.0,
        0.0,
        0.0,
        '<circle cx="960" cy="540" r="30" fill="#F47067" data-role="commit" data-sha="aaa" data-phase="before"/>'
        '<rect x="940" y="480" width="40" height="20" fill="#3FB950" data-role="ref" data-name="main" data-phase="before"/>'
        '<rect x="940" y="450" width="40" height="20" fill="#3FB950" data-role="ref" data-name="old" data-phase="before"/>'
        '<text x="900" y="600" font-size="14" data-role="title">before</text>',
    )
    # Same camera; commit aaa slid right by 200 px, bbb is new at its old spot,
    # "main" followed bbb, "old" is gone, and the title is new.
    after = svg_root(
        100.0,
        0.0,
        0.0,
        '<circle cx="1160" cy="540" r="30" fill="#F47067" data-role="commit" data-sha="aaa" data-phase="before"/>'
        '<circle cx="960" cy="540" r="30" fill="#F47067" data-role="commit" data-sha="bbb" data-phase="before"/>'
        '<rect x="940" y="480" width="40" height="20" fill="#3FB950" data-role="ref" data-name="main" data-phase="before"/>'
        '<text x="900" y="600" font-size="14" data-role="title">after</text>',
    )
    merged = merge_svgs(before, after)
    assert is_animated(merged)
    aaa = re.search(r'<circle [^>]*data-sha="aaa"[^>]*>', merged).group(0)
    assert (
        'data-dx="-200"' in aaa
        and 'data-dy="0"' in aaa
        and 'data-phase="before"' in aaa
    )
    bbb = re.search(r'<circle [^>]*data-sha="bbb"[^>]*>', merged).group(0)
    assert 'data-phase="after"' in bbb
    old = re.search(r'<rect [^>]*data-name="old"[^>]*>', merged).group(0)
    assert 'data-phase="removed"' in old
    # main did not move (same pixels): a plain "before" element
    main = re.search(r'<rect [^>]*data-name="main"[^>]*>', merged).group(0)
    assert "data-dx" not in main and 'data-phase="before"' in main
    # removed first, then moves, then arrivals
    assert 'data-step="1"' in old and 'data-step="2"' in aaa and 'data-step="3"' in bbb
    # one title only: the later drawing's
    assert merged.count('data-role="title"') == 1 and ">after<" in merged


def test_merge_reprojects_the_earlier_drawing_into_the_later_camera():
    # The camera zoomed out by half between the two drawings; aaa stayed put in
    # the scene, so it must not count as moved, while ccc (only before) is
    # placed and sized for the new camera.
    before = svg_root(
        100.0,
        0.0,
        0.0,
        '<circle cx="1060" cy="540" r="30" fill="#F47067" data-role="commit" data-sha="aaa" data-phase="before"/>'
        '<circle cx="860" cy="540" r="30" fill="#F47067" data-role="commit" data-sha="ccc" data-phase="before"/>',
    )
    after = svg_root(
        50.0,
        0.0,
        0.0,
        '<circle cx="1010" cy="540" r="15" fill="#F47067" data-role="commit" data-sha="aaa" data-phase="before"/>',
    )
    merged = merge_svgs(before, after)
    aaa = re.search(r'<circle [^>]*data-sha="aaa"[^>]*>', merged).group(0)
    assert "data-dx" not in aaa and 'data-phase="before"' in aaa
    ccc = re.search(r'<circle [^>]*data-sha="ccc"[^>]*>', merged).group(0)
    assert 'cx="910"' in ccc and 'r="15"' in ccc and 'data-phase="removed"' in ccc


def test_a_file_changing_column_slides_and_a_recolor_is_blended():
    before = svg_root(
        100.0,
        0.0,
        0.0,
        '<text x="100" y="700" font-size="14" fill="#AAAAAA" data-role="file" data-name="a.txt" data-column="Untracked files" data-phase="before">a.txt</text>'
        '<circle cx="960" cy="540" r="30" fill="#F47067" data-role="commit" data-sha="aaa" data-phase="before"/>',
    )
    after = svg_root(
        100.0,
        0.0,
        0.0,
        '<text x="1500" y="700" font-size="14" fill="#AAAAAA" data-role="file" data-name="a.txt" data-column="Staged files" data-phase="before">a.txt</text>'
        '<circle cx="960" cy="540" r="30" fill="#D29922" data-role="commit" data-sha="aaa" data-phase="before"/>',
    )
    merged = merge_svgs(before, after)
    file = re.search(r"<text [^>]*data-name=\"a.txt\"[^>]*>", merged).group(0)
    assert 'data-dx="-1400"' in file and 'data-phase="before"' in file
    disc = re.search(r'<circle [^>]*data-sha="aaa"[^>]*>', merged).group(0)
    assert 'data-before-fill="#F47067"' in disc and 'fill="#D29922"' in disc


def test_identical_drawings_merge_to_a_still_graph():
    svg = svg_root(
        100.0,
        0.0,
        0.0,
        '<circle cx="960" cy="540" r="30" data-role="commit" data-sha="aaa" data-phase="before"/>',
    )
    assert not is_animated(merge_svgs(svg, svg))


# ------------------------------------------------------- naming the change
def state(**kw):
    s = RepoState()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_new_reflog_entries_are_the_leading_ones():
    before = ("commit: b", "commit: a")
    assert new_reflog_entries(
        before, ("reset: moving to HEAD~1", "commit: b", "commit: a")
    ) == ["reset: moving to HEAD~1"]
    assert new_reflog_entries(before, before) == []
    assert new_reflog_entries((), ("commit (initial): a",)) == ["commit (initial): a"]
    # a repeated subject is still one new entry
    assert new_reflog_entries(("commit: x",), ("commit: x", "commit: x")) == [
        "commit: x"
    ]


def test_reflog_subjects_become_commands():
    heads = {"refs/heads/main": "1"}
    cases = {
        "commit: add a thing": "git commit",
        "commit (amend): add a thing": "git commit --amend",
        "commit (initial): root": "git commit",
        "reset: moving to HEAD~1": "git reset HEAD~1",
        "checkout: moving from main to feature": "git checkout feature",
        "merge feature: Merge made by the 'ort' strategy.": "git merge feature",
        "rebase (finish): returning to refs/heads/feature": "git rebase",
        "cherry-pick: fix": "git cherry-pick",
        'revert: Revert "x"': "git revert",
        "pull: Fast-forward": "git pull",
        "frobnicate: something": "git frobnicate",
    }
    for subject, expected in cases.items():
        before = state(refs=heads, reflog=("commit: earlier",))
        after = state(refs=heads, reflog=(subject, "commit: earlier"))
        assert describe_change(before, after)[0] == expected, subject


def test_checkout_of_a_branch_that_did_not_exist_is_checkout_b():
    before = state(refs={"refs/heads/main": "1"}, reflog=("commit: a",))
    after = state(
        refs={"refs/heads/main": "1", "refs/heads/topic": "1"},
        reflog=("checkout: moving from main to topic", "commit: a"),
    )
    assert describe_change(before, after)[0] == "git checkout -b topic"


def test_changes_without_a_reflog_entry_are_read_from_the_diff():
    base = {"refs/heads/main": "1"}
    assert (
        describe_change(state(refs=base), state(refs={**base, "refs/heads/x": "1"}))[0]
        == "git branch x"
    )
    assert (
        describe_change(state(refs={**base, "refs/heads/x": "1"}), state(refs=base))[0]
        == "git branch -d x"
    )
    assert (
        describe_change(
            state(refs={**base, "refs/heads/old": "2"}),
            state(refs={**base, "refs/heads/new": "2"}),
        )[0]
        == "git branch -m new"
    )
    assert (
        describe_change(state(refs=base), state(refs={**base, "refs/tags/v1": "1"}))[0]
        == "git tag v1"
    )
    assert (
        describe_change(
            state(refs=base), state(refs={**base, "refs/remotes/origin/main": "1"})
        )[0]
        == "git fetch"
    )
    assert (
        describe_change(state(refs=base), state(refs=base, stash=("s",)))[0]
        == "git stash"
    )
    assert (
        describe_change(
            state(refs=base, stash=("s",)), state(refs=base, status=(" M a.txt",))
        )[0]
        == "git stash pop"
    )
    assert (
        describe_change(
            state(refs=base, status=("?? a.txt",)),
            state(refs=base, status=("A  a.txt",)),
        )[0]
        == "git add a.txt"
    )
    assert (
        describe_change(state(refs=base), state(refs=base, status=("D  a.txt",)))[0]
        == "git rm a.txt"
    )
    assert (
        describe_change(
            state(refs=base, status=("M  a.txt",)),
            state(refs=base, status=(" M a.txt",)),
        )[0]
        == "git restore --staged a.txt"
    )
    assert (
        describe_change(state(refs=base), state(refs=base, status=("?? new.txt",)))[0]
        == "new file new.txt"
    )
    assert (
        describe_change(state(refs=base), state(refs=base, status=(" M a.txt",)))[0]
        == "edited a.txt"
    )
    assert (
        describe_change(state(refs=base, status=(" M a.txt",)), state(refs=base))[0]
        == "git restore a.txt"
    )
    assert (
        describe_change(state(refs=base), state(refs=base))[0] == "repository changed"
    )


# ------------------------------------------------------------- a real repo
def test_read_state_sees_refs_status_and_the_reflog(repo):
    (repo / "file1.txt").write_text("changed\n")
    (repo / "new.txt").write_text("new\n")
    s = read_state(str(repo))
    assert s.head == "refs/heads/main" and len(s.head_sha) == 40
    assert set(s.heads()) == {"main", "feature"}
    assert " M file1.txt" in s.status and "?? new.txt" in s.status
    assert s.reflog[0].startswith("commit: commit 3")
    before = s.signature
    run_git(repo, "add", "new.txt")
    assert read_state(str(repo)).signature != before


def test_a_session_plays_a_commit_as_a_before_after_graph(repo, tmp_path):
    session = LiveSession(str(repo), str(tmp_path / "out"), zones=True, poll=0.1)
    first = session.start()
    assert (
        first.index == 0
        and os.path.exists(first.svg_path)
        and os.path.exists(first.page_path)
    )
    assert not is_animated(open(first.svg_path, encoding="utf-8").read())
    assert session.check() is None, "nothing changed"

    old_head = run_git(repo, "rev-parse", "HEAD").strip()
    (repo / "file4.txt").write_text("four\n")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "commit 4")
    new_head = run_git(repo, "rev-parse", "HEAD").strip()
    snap = session.check()
    assert snap is not None and snap.index == 1 and snap.label == "git commit"
    svg = open(snap.svg_path, encoding="utf-8").read()
    new = re.search(rf'<circle [^>]*data-sha="{new_head}"[^>]*>', svg).group(0)
    assert 'data-phase="after"' in new
    old = re.search(rf'<circle [^>]*data-sha="{old_head}"[^>]*>', svg).group(0)
    assert 'data-phase="before"' in old and "data-dx=" in old, "the old tip slides over"
    # Newest commit on the left: the new one takes the tip's place, so the
    # HEAD pill stays where it is and the older commits slide right.
    head = re.search(r'<rect [^>]*data-name="HEAD"[^>]*>', svg).group(0)
    assert "data-dx=" not in head and 'data-phase="before"' in head
    assert session.history()[1]["label"] == "git commit"
    assert session.errors == []
    # the standalone page carries the same graph and the change as its title
    page = open(snap.page_path, encoding="utf-8").read()
    assert "<title>git commit</title>" in page and 'data-phase="after"' in page


def test_the_live_page_has_the_strip_and_every_transport():
    from git_sim.render.live_html import build_live_html, hosted_live_url

    page = build_live_html(repo="demo", key="s3cret")
    assert 'id="live"' in page and 'id="chips"' in page and 'id="replay"' in page
    assert "acquireVsCodeApi" in page and "new EventSource(api('/events'))" in page
    assert "window.GitSimViewer" in page
    assert '"repo": "demo"' in page and '"key": "s3cret"' in page
    assert (
        hosted_live_url(
            "https://initialcommit.com/tools/git-sim", "http://127.0.0.1:8123", "s3cret"
        )
        == "https://initialcommit.com/tools/git-sim/live#live=http%3A%2F%2F127.0.0.1%3A8123&k=s3cret"
    )


def test_the_live_assets_are_exported_for_the_site(tmp_path):
    from git_sim.render.html import export_viewer_assets
    from git_sim.render.live_html import LIVE_JS

    written = {os.path.basename(p) for p in export_viewer_assets(str(tmp_path))}
    assert {"git-sim-live.css", "git-sim-live.js", "git-sim-live-strip.html"} <= written
    strip = (tmp_path / "git-sim-live-strip.html").read_text(encoding="utf-8")
    assert 'th:fragment="strip"' in strip and 'id="chips"' in strip
    assert (tmp_path / "git-sim-live.js").read_text(
        encoding="utf-8"
    ).strip() == LIVE_JS.strip()


def test_the_local_server_requires_the_key_and_answers_the_site(repo, tmp_path):
    import urllib.error
    import urllib.request

    from git_sim.live import LiveServer

    session = LiveSession(str(repo), str(tmp_path / "out"), zones=False, poll=0.1)
    session.start()
    server = LiveServer(("127.0.0.1", 0), session)
    thread = __import__("threading").Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True
    )
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        # the page itself needs no key, and carries it
        page = urllib.request.urlopen(base + "/").read().decode("utf-8")
        assert session.key in page
        # data without the key: refused
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(base + "/history")
        assert err.value.code == 403
        # with it: served, and readable by the hosted page's origin only
        req = urllib.request.Request(
            base + f"/history?k={session.key}",
            headers={"Origin": "https://initialcommit.com"},
        )
        with urllib.request.urlopen(req) as r:
            assert (
                r.headers["Access-Control-Allow-Origin"] == "https://initialcommit.com"
            )
            assert r.headers["Access-Control-Allow-Private-Network"] == "true"
            assert json.loads(r.read())[0]["index"] == 0
        req = urllib.request.Request(
            base + f"/svg/0?k={session.key}", headers={"Origin": "https://evil.example"}
        )
        with urllib.request.urlopen(req) as r:
            assert r.headers.get("Access-Control-Allow-Origin") is None
            assert r.read().startswith(b"<svg")
        # the preflight browsers send before a cross-origin request
        req = urllib.request.Request(
            base + "/history",
            method="OPTIONS",
            headers={"Origin": "https://initialcommit.com"},
        )
        with urllib.request.urlopen(req) as r:
            assert (
                r.status == 204
                and r.headers["Access-Control-Allow-Origin"]
                == "https://initialcommit.com"
            )
        # the whole session as a downloadable page
        with urllib.request.urlopen(base + f"/session.html?k={session.key}") as r:
            assert r.headers["Content-Disposition"].startswith(
                'attachment; filename="repo-live-'
            )
            assert b'id="git-sim-session"' in r.read()
    finally:
        session.stop.set()
        server.shutdown()
        server.server_close()


def test_cli_once_prints_the_first_snapshot(repo, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.lower().startswith("git_sim_")}
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "git_sim",
            "-d",
            "--media-dir",
            str(tmp_path / "m"),
            "live",
            "--json",
            "--once",
            "-C",
            str(repo),
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        cwd=str(tmp_path),
    ).stdout
    lines = [json.loads(l) for l in out.splitlines() if l.strip()]
    assert lines[0]["event"] == "start" and lines[0]["repo"] == os.path.normpath(
        str(repo)
    )
    snap = lines[1]
    assert snap["event"] == "snapshot" and snap["index"] == 0
    assert os.path.exists(snap["svg"]) and os.path.exists(snap["page"])
    assert (
        os.sep + "repo" + os.sep + "live" + os.sep in snap["svg"]
    ), "saved under the watched repository's media folder"


def test_a_session_is_kept_as_one_page_and_listed(repo, tmp_path):
    from git_sim.live import SESSION_PAGE, list_sessions
    from git_sim.render.live_html import build_live_html

    out = tmp_path / "sessions" / "20260920-120000"
    session = LiveSession(str(repo), str(out), zones=False, poll=0.1)
    session.start()
    (repo / "file1.txt").write_text("changed\n")
    run_git(repo, "add", "file1.txt")
    run_git(repo, "commit", "-q", "-m", "commit 4")
    assert session.check() is not None
    page = (out / SESSION_PAGE).read_text(encoding="utf-8")
    assert 'id="git-sim-session"' in page and 'data-live-recorded="1"' in page
    data = session.session_data()
    assert data["repo"] == "repo" and [i["index"] for i in data["items"]] == [0, 1]
    assert data["items"][1]["label"] == "git commit" and data["items"][1][
        "svg"
    ].lstrip().startswith("<svg")
    assert "git-sim live session" in page and page.count("<svg") >= 2
    listed = list_sessions(str(tmp_path / "sessions"))
    assert (
        len(listed) == 1
        and listed[0]["changes"] == 1
        and listed[0]["page"] == str(out / SESSION_PAGE)
    )
    # a recorded page from data alone, for the extension and the server
    alone = build_live_html(repo="repo", session=data)
    assert '"items":' in alone and "Record video" in alone and "Save session" in alone


def test_cli_lists_and_replays_sessions(repo, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.lower().startswith("git_sim_")}
    env["PYTHONIOENCODING"] = "utf-8"
    media = str(tmp_path / "m")
    base = [sys.executable, "-m", "git_sim", "-d", "--media-dir", media, "live"]
    # nothing yet
    out = subprocess.run(
        base + ["--sessions", "--json", "-C", str(repo)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    ).stdout
    assert out.strip() == ""
    result = subprocess.run(
        base + ["--replay", "-C", str(repo)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )
    assert result.returncode == 1 and "no recorded session" in result.stderr
    # one run that draws the start state writes a session
    subprocess.run(
        base + ["--json", "--once", "-C", str(repo)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=True,
    )
    out = subprocess.run(
        base + ["--sessions", "--json", "-C", str(repo)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=True,
    ).stdout
    listed = [json.loads(l) for l in out.splitlines() if l.strip()]
    assert (
        len(listed) == 1
        and listed[0]["event"] == "session"
        and listed[0]["changes"] == 0
    )
    page = subprocess.run(
        base + ["--replay", "-C", str(repo)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=True,
    ).stdout.strip()
    assert page == listed[0]["page"] and os.path.exists(page)
    assert (
        subprocess.run(
            base + ["--replay", "--session", os.path.dirname(page), "-C", str(repo)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
            check=True,
        ).stdout.strip()
        == page
    )


def test_cli_prints_the_live_page(repo, tmp_path):
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "git_sim",
            "-d",
            "live",
            "--print-page",
            "-C",
            str(repo),
        ],
        capture_output=True,
        check=True,
        cwd=str(tmp_path),
    ).stdout.decode("utf-8")
    assert out.startswith("<!DOCTYPE html>") and 'id="live"' in out
