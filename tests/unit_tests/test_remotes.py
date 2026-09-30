"""The commands that talk to remotes: remote -v and remote show, ls-remote,
fetch --all, clone --depth / -b and pull <remote> <branch>.

The fixture is a repository with a bare "origin" beside it that a colleague
has moved on since the last fetch: two new commits on main, a branch deleted
(still here as origin/old-idea), a new branch not fetched yet (fresh) and a
new tag. There is also a local commit on feature not pushed yet, a tag only
here, and a second remote, "upstream", with nothing fetched from it.
Remote URLs are relative paths (../origin.git), as people write them.
"""

import os
import re
import subprocess

import pytest

from git_sim.settings import Settings, settings
from git_sim.theme import theme_for


def run_git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def commit(cwd, name, message):
    (cwd / name).write_text(message + "\n")
    run_git(cwd, "add", name)
    run_git(cwd, "commit", "-q", "-m", message)
    return run_git(cwd, "rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
    run_git(tmp_path, "init", "-q", "--bare", "-b", "main", "origin.git")
    run_git(tmp_path, "init", "-q", "--bare", "-b", "main", "upstream.git")
    path = tmp_path / "work"
    path.mkdir()
    run_git(path, "init", "-q", "-b", "main")
    for i in range(1, 5):
        commit(path, f"f{i}.txt", f"Add file {i}")
    run_git(path, "remote", "add", "origin", "../origin.git")
    run_git(path, "branch", "feature")
    run_git(path, "branch", "old-idea", "HEAD~1")
    run_git(path, "tag", "v1.0", "HEAD~1")
    run_git(path, "push", "-q", "origin", "main", "feature", "old-idea", "v1.0")
    run_git(path, "branch", "-q", "--set-upstream-to=origin/main", "main")
    run_git(path, "branch", "-q", "--set-upstream-to=origin/feature", "feature")

    other = tmp_path / "colleague"
    run_git(tmp_path, "clone", "-q", "origin.git", "colleague")
    commit(other, "c.txt", "Colleague change 1")
    commit(other, "d.txt", "Colleague change 2")
    run_git(other, "push", "-q", "origin", "main")
    run_git(other, "push", "-q", "origin", "--delete", "old-idea")
    run_git(other, "checkout", "-q", "-b", "fresh")
    commit(other, "fresh.txt", "Fresh idea")
    run_git(other, "push", "-q", "origin", "fresh")
    run_git(other, "tag", "v1.1", "main")
    run_git(other, "push", "-q", "origin", "v1.1")

    run_git(path, "checkout", "-q", "feature")
    commit(path, "feat.txt", "Feature work")
    run_git(path, "checkout", "-q", "main")
    run_git(path, "tag", "local-only")
    run_git(path, "push", "-q", "../upstream.git", "main:main")
    run_git(path, "remote", "add", "upstream", "../upstream.git")

    for key, value in Settings().model_dump().items():
        setattr(settings, key, value)
    settings.auto_open = False
    monkeypatch.chdir(path)
    yield path
    settings.compact = False


def sha(cwd, rev):
    return run_git(cwd, "rev-parse", rev).strip()


def scene_texts(scene):
    return [
        mob.text
        for top in scene.mobjects
        for mob in top.get_family()
        if hasattr(mob, "text")
    ]


def svg_of(scene):
    scene.construct()
    return scene.render_svg(
        background=theme_for(settings.light).bg, extra_mobjects=scene.removed_mobjects
    )


def roles(svg, role):
    return re.findall(rf'<[a-z]+ [^>]*data-role="{role}"[^>]*>', svg)


def ref_commit(scene, name):
    label = scene.drawnRefs[name].get_center()
    for hexsha, circle in scene.drawnCommits.items():
        center = circle.get_center()
        if abs(center[0] - label[0]) < 0.6 and label[1] > center[1]:
            return hexsha
    return None


# ---- remote -v -----------------------------------------------------------------------------
def test_remote_verbose_lists_fetch_and_push_urls(repo):
    from git_sim.remote import Remote

    run_git(repo, "config", "remote.origin.pushurl", "../push-here.git")
    scene = Remote(command=None, remote=None, url_or_path=None, verbose=True)
    assert scene.cmd == "git remote -v"
    scene.construct()
    texts = scene_texts(scene)
    assert texts.count("fetch") == 2 and texts.count("push") == 2
    assert "../origin.git" in texts and "../push-here.git" in texts
    assert "../upstream.git" in texts
    # the file card lights the address lines it reads
    assert "pushurl = ../push-here.git" in texts
    # -v belongs to the listing; with a subcommand git ignores it
    from git_sim.enums import RemoteSubCommand

    other = Remote(command=RemoteSubCommand.GET_URL, remote="origin", url_or_path=None, verbose=True)
    assert other.cmd == "git remote get-url origin" and not other.verbose


# ---- remote show ---------------------------------------------------------------------------
def test_remote_show_reports_branches_pull_and_push(repo):
    from git_sim.enums import RemoteSubCommand
    from git_sim.remote import Remote

    before = run_git(repo, "for-each-ref")
    scene = Remote(command=RemoteSubCommand.SHOW, remote="origin", url_or_path=None)
    assert scene.cmd == "git remote show origin"
    scene.construct()
    info = scene.shown
    assert info["fetch_url"] == "../origin.git" == info["push_url"]
    assert info["head_branch"] == "main"
    assert dict(info["branches"]) == {
        "feature": "tracked",
        "fresh": "new",
        "main": "tracked",
        "old-idea": "stale",
    }
    assert sorted(info["pulls"]) == [
        ("feature", "merges with", "feature"),
        ("main", "merges with", "main"),
    ]
    assert dict((b, s) for b, _, s in info["pushes"]) == {
        "feature": "fast-forwardable",
        "main": "local out of date",
    }
    texts = scene_texts(scene)
    assert any("new: the next fetch stores it as origin/fresh" in t for t in texts)
    assert any(t.startswith("stale: deleted on origin") for t in texts)
    assert run_git(repo, "for-each-ref") == before, "remote show changes nothing"


def test_remote_show_refuses_an_unknown_or_unreachable_remote(repo, capsys):
    from git_sim.enums import RemoteSubCommand
    from git_sim.remote import Remote

    with pytest.raises(SystemExit):
        Remote(command=RemoteSubCommand.SHOW, remote="nope", url_or_path=None).construct()
    run_git(repo, "remote", "add", "gone", "../no-such-repo.git")
    with pytest.raises(SystemExit):
        Remote(command=RemoteSubCommand.SHOW, remote="gone", url_or_path=None).construct()
    assert "could not reach remote 'gone'" in capsys.readouterr().out


def test_remote_show_compact_keeps_the_report_but_not_the_explanation(repo):
    from git_sim.enums import RemoteSubCommand
    from git_sim.remote import Remote

    make = lambda: Remote(command=RemoteSubCommand.SHOW, remote="origin", url_or_path=None)  # noqa: E731
    full = svg_of(make())
    settings.compact = True
    small = svg_of(make())
    assert roles(full, "title") and not roles(small, "title")
    assert "what it does" in full and "what it does" not in small
    assert "tracked as origin/main" in small


# ---- ls-remote -----------------------------------------------------------------------------
def rows_by_ref(scene):
    return {(r[0], r[1]): r for r in scene.rows}


def test_ls_remote_compares_the_remote_with_your_copies(repo):
    from git_sim.lsremote import LsRemote

    scene = LsRemote()
    assert scene.name == "origin" and scene.cmd == "git ls-remote"
    rows = rows_by_ref(scene)
    state = lambda section, ref: rows[(section, ref)][5]  # noqa: E731
    assert rows[("HEAD", "HEAD")][2] == sha("../origin.git", "main")
    assert state("branches", "main") == "moved"
    assert state("branches", "fresh") == "new"
    assert state("branches", "old-idea") == "gone"
    assert state("branches", "feature") == "ahead" and rows[("branches", "feature")][6] == 1
    assert state("tags", "v1.0") == "same"
    assert state("tags", "v1.1") == "new"
    assert state("tags", "local-only") == "only-here"
    scene.construct()
    texts = scene_texts(scene)
    assert "you're 1 ahead: push sends it" in texts
    assert "deleted on origin: fetch --prune drops yours" in texts


def test_ls_remote_filters_and_other_remotes(repo, tmp_path):
    from git_sim.lsremote import LsRemote

    heads = LsRemote(remote="origin", heads=True)
    assert heads.cmd == "git ls-remote --heads origin"
    assert {r[0] for r in heads.rows} == {"branches"}
    tags = LsRemote(tags=True)
    assert {r[0] for r in tags.rows} == {"tags"}
    # a remote with nothing fetched: every branch is new here
    up = LsRemote(remote="upstream")
    assert rows_by_ref(up)[("branches", "main")][5] == "new"
    # a URL rather than a remote name: nothing here to compare with
    url = LsRemote(remote=str(tmp_path / "origin.git"), heads=True)
    assert url.name is None and {r[5] for r in url.rows} == {"none"}
    url.construct()


def test_ls_remote_errors(repo, tmp_path, monkeypatch, capsys):
    from git_sim.lsremote import LsRemote

    with pytest.raises(SystemExit):
        LsRemote(remote="../no-such-repo.git")
    assert "could not list the refs" in capsys.readouterr().out
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    run_git(lonely, "init", "-q", "-b", "main")
    commit(lonely, "a.txt", "Only commit")
    monkeypatch.chdir(lonely)
    with pytest.raises(SystemExit):
        LsRemote()
    assert "no remotes" in capsys.readouterr().out


def test_ls_remote_compact_drops_the_title_and_the_explanation(repo):
    from git_sim.lsremote import LsRemote

    full = svg_of(LsRemote())
    settings.compact = True
    small = svg_of(LsRemote())
    assert roles(full, "title") and not roles(small, "title")
    assert "Nothing is downloaded" in full and "Nothing is downloaded" not in small
    assert "not fetched yet" in small


# ---- fetch --all ---------------------------------------------------------------------------
def test_fetch_all_draws_what_each_remote_brings(repo):
    from git_sim.fetch import Fetch

    scene = Fetch(remote=None, branch=None, all=True)
    assert scene.cmd.split() == ["git", "fetch", "--all"]
    scene.construct()
    new_main = sha("../origin.git", "main")
    fresh = sha("../origin.git", "fresh")
    assert ref_commit(scene, "origin/main") == new_main
    assert ref_commit(scene, "origin/fresh") == fresh
    assert ref_commit(scene, "upstream/main") == sha(repo, "main")
    texts = scene_texts(scene)
    assert "origin: 3 new commits; origin/main moved; origin/fresh new" in texts
    assert "upstream: upstream/main new" in texts
    assert any("origin/old-idea no longer exists" in t for t in texts)
    # unchanged remote-tracking labels stay off the crowded graph
    assert "origin/feature" not in scene.drawnRefs
    with pytest.raises(SystemExit):
        Fetch(remote="origin", branch=None, all=True)


def test_fetch_all_prune_removes_the_stale_label(repo):
    from git_sim.fetch import Fetch

    scene = Fetch(remote=None, branch=None, prune=True, all=True)
    assert scene.cmd.split() == ["git", "fetch", "--all", "--prune"]
    scene.construct()
    assert "origin/old-idea" not in scene.drawnRefs
    assert any(
        (getattr(m, "meta", None) or {}).get("name") == "origin/old-idea"
        for m in scene.removed_mobjects
    )


# ---- clone ---------------------------------------------------------------------------------
def test_clone_depth_draws_only_the_last_commits_and_the_cut(repo, tmp_path):
    from git_sim.clone import Clone

    url = str(tmp_path / "origin.git")
    scene = Clone(url=url, path=".", depth=2)
    assert scene.cmd == f"git clone --depth 2 {url}"
    scene.construct()
    tip = sha("../origin.git", "main")
    parent = sha("../origin.git", "main~1")
    assert set(scene.drawnCommits) == {tip, parent}
    assert scene.grafted == {parent}
    assert "grafted" in scene_texts(scene)
    assert any("shallow: only the last 2 commits" in t for t in scene_texts(scene))
    # the grafted commit has no parents in the clone
    assert scene.drawnCommits[parent].meta["parents"] == ""


def test_clone_branch_checks_out_that_branch(repo, tmp_path, capsys):
    from git_sim.clone import Clone

    url = str(tmp_path / "origin.git")
    scene = Clone(url=url, path="mine", branch="fresh")
    assert scene.cmd == f"git clone -b fresh {url} mine"
    scene.construct()
    assert ref_commit(scene, "HEAD") == sha("../origin.git", "fresh")
    assert ref_commit(scene, "fresh") == sha("../origin.git", "fresh")
    both = Clone(url=url, path=".", depth=1, branch="fresh")
    both.construct()
    assert set(both.drawnCommits) == {sha("../origin.git", "fresh")}
    with pytest.raises(SystemExit):
        Clone(url=url, path=".", branch="nope").construct()
    assert "Remote branch nope not found" in capsys.readouterr().out


def test_clone_compact_leaves_out_the_caption(repo, tmp_path):
    from git_sim.clone import Clone

    settings.compact = True
    scene = Clone(url=str(tmp_path / "origin.git"), path=".", depth=2)
    scene.construct()
    texts = scene_texts(scene)
    assert "grafted" in texts
    assert not any(t.startswith("Successfully cloned") for t in texts)


# ---- pull <remote> <branch> ------------------------------------------------------------------
def test_pull_remote_branch_with_a_relative_remote_url(repo):
    from git_sim.pull import Pull

    scene = Pull(remote="origin", branch="main")
    assert scene.cmd.split() == ["git", "pull", "origin", "main"]
    scene.construct()
    new_main = sha("../origin.git", "main")
    assert ref_commit(scene, "main") == new_main
    assert ref_commit(scene, "origin/main") == new_main
    # this repository's other branches keep their own names and places
    assert ref_commit(scene, "old-idea") == sha(repo, "old-idea")
    assert ref_commit(scene, "origin/old-idea") == sha(repo, "origin/old-idea")


def test_pull_remote_branch_into_another_branch_merges_it(repo):
    from git_sim.pull import Pull

    run_git(repo, "checkout", "-q", "feature")
    scene = Pull(remote="origin", branch="main")
    scene.construct()
    head = ref_commit(scene, "HEAD")
    assert ref_commit(scene, "feature") == head
    parents = scene.drawnCommits[head].meta["parents"].split()
    assert parents == [sha(repo, "feature"), sha("../origin.git", "main")]
    # origin/feature is where it was fetched, not where the local feature is
    assert ref_commit(scene, "origin/feature") == sha(repo, "origin/feature")


def test_remote_url_makes_a_relative_path_absolute(repo, tmp_path):
    import git

    from git_sim.git_sim_base_command import GitSimBaseCommand

    remote = git.Repo(repo).remote("origin")
    assert os.path.samefile(GitSimBaseCommand.remote_url(remote), tmp_path / "origin.git")
    run_git(repo, "remote", "add", "web", "https://example.com/x.git")
    run_git(repo, "remote", "add", "ssh", "git@example.com:x/y.git")
    assert GitSimBaseCommand.remote_url(git.Repo(repo).remote("web")) == "https://example.com/x.git"
    assert GitSimBaseCommand.remote_url(git.Repo(repo).remote("ssh")) == "git@example.com:x/y.git"
