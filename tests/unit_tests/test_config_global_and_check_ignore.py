"""config --global and check-ignore: the card drawings built against a small
repository and a private global config file, inspected without rendering
(and rendered to SVG once each, to check --compact)."""

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


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Two commits, a .gitignore with a negated line, a tracked file that a
    rule would match, a rule in .git/info/exclude, a private global config
    with a global excludes file; cwd inside the repo."""
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / "ignore").write_text("*.swp\n")
    gitconfig = home / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Ada\n\temail = ada@example.com\n[core]\n\teditor = vim\n"
        f"\texcludesFile = {(home / 'ignore').as_posix()}\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.email", "local@example.com")
    (path / "app.py").write_text("print('hi')\n")
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "first")
    (path / ".gitignore").write_text("*.log\nbuild/\n# scratch\n*.tmp\n!keep.tmp\n")
    (path / "debug.log").write_text("tracked anyway\n")
    run_git(path, "add", ".gitignore")
    run_git(path, "add", "-f", "debug.log")
    run_git(path, "commit", "-m", "ignore rules")
    with open(path / ".git" / "info" / "exclude", "a") as f:
        f.write("cache.db\n")
    for key, value in Settings().model_dump().items():
        setattr(settings, key, value)
    settings.auto_open = False
    monkeypatch.chdir(path)
    yield path
    settings.compact = False


def texts(scene, phase=None):
    out = []
    for top in scene.mobjects:
        for mob in top.get_family():
            if not hasattr(mob, "text"):
                continue
            if phase is None or (getattr(mob, "meta", None) or {}).get("phase", "before") == phase:
                out.append(mob.text)
    return out


def svg_roles(scene, role):
    svg = scene.render_svg(background=theme_for(settings.light).bg, extra_mobjects=scene.removed_mobjects)
    return re.findall(rf'<[a-z]+ [^>]*data-role="{role}"[^>]*>', svg)


# ---- config --global ---------------------------------------------------------------------


def test_config_global_writes_the_global_file(repo):
    from git_sim.config import Config

    scene = Config(l=False, settings=["core.editor", "code --wait"], glob=True)
    assert scene.cmd == 'git config --global core.editor "code --wait"'
    scene.construct()
    shown = texts(scene)
    assert "~/.gitconfig" in shown and "global" in shown
    # the global file's own lines, not the repository's
    assert "editor = vim" in shown and "name = Ada" in shown
    assert "email = local@example.com" not in shown
    # the old value is there throughout; the new line only after the command
    assert "editor = vim" in texts(scene, "before")
    assert "editor = code --wait" in texts(scene, "after")
    assert any("all your repositories" in t for t in shown)


def test_config_global_says_when_the_repository_overrides_it(repo):
    from git_sim.config import Config

    scene = Config(l=False, settings=["user.email", "new@example.com"], glob=True)
    scene.construct()
    assert "email = new@example.com" in texts(scene, "after")
    assert "email = ada@example.com" in texts(scene, "before")
    assert any("local@example.com" in t for t in texts(scene)), "the local value that wins here is named"


def test_config_global_new_section_and_alias(repo):
    from git_sim.config import Config

    scene = Config(l=False, settings=["alias.co", "checkout"], glob=True)
    scene.construct()
    after = texts(scene, "after")
    assert "[alias]" in after and "co = checkout" in after
    assert any("git co run" in t for t in texts(scene))


def test_config_subsection_keys_match_their_quoted_sections(repo):
    from git_sim.config import Config

    # branch.main.merge lives under [branch "main"] in the file
    run_git(repo, "config", "branch.main.merge", "refs/heads/main")
    scene = Config(l=False, settings=["branch.main.merge"])
    scene.construct()
    shown = texts(scene)
    assert "refs/heads/main" in shown
    assert not any(t.startswith("not set") for t in shown)

    # a new subsection is written the way git writes it
    scene = Config(l=False, settings=["branch.feature.remote", "origin"])
    scene.construct()
    assert '[branch "feature"]' in texts(scene, "after")


@pytest.fixture
def system_file(repo, tmp_path, monkeypatch):
    """A system config of its own, where git var and git config --system look."""
    path = tmp_path / "system-gitconfig"
    path.write_text("[core]\n\teditor = emacs\n[diff \"astextplain\"]\n\ttextconv = astextplain\n")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(path))
    return path


def test_config_system_reads_the_system_file_where_git_keeps_it(repo, system_file):
    from git_sim.config import Config

    scene = Config(l=False, settings=["core.editor"], system=True)
    assert scene.cmd == "git config --system core.editor"
    assert scene.system_file() == str(system_file).replace("\\", "/")
    scene.construct()
    shown = texts(scene)
    assert "system" in shown and "emacs" in shown
    assert "editor = emacs" in shown
    assert any(t.startswith("Read from the system config") for t in shown)
    # --system names the file outright, so GIT_CONFIG_NOSYSTEM doesn't hide it
    assert "(no system settings yet)" not in shown


def test_config_system_write_says_which_later_scope_wins(repo, system_file):
    from git_sim.config import Config

    scene = Config(l=False, settings=["core.editor", "nano"], system=True)
    scene.construct()
    assert "editor = nano" in texts(scene, "after")
    # the paragraph wraps where the system's fonts make it, so read it whole
    prose = " ".join(texts(scene))
    assert "admin rights" in prose
    assert "~/.gitconfig sets it to vim" in prose, "the global value that wins here is named"


def test_config_system_list_shows_only_the_system_file(repo, system_file):
    from git_sim.config import Config

    scene = Config(l=True, settings=[], system=True)
    assert scene.cmd == "git config --list --system"
    scene.construct()
    shown = texts(scene)
    assert "every user on this machine" in shown
    assert "you, in all your repositories" not in shown
    assert '[diff "astextplain"]' in shown


def test_config_global_and_system_together_is_an_error(repo):
    from git_sim.config import Config

    with pytest.raises(SystemExit):
        Config(l=False, settings=["core.editor"], glob=True, system=True)


def test_config_global_read_answers_from_the_global_file_only(repo):
    from git_sim.config import Config

    scene = Config(l=False, settings=["user.email"], glob=True)
    scene.construct()
    shown = texts(scene)
    assert "ada@example.com" in shown
    assert not texts(scene, "after")
    missing = Config(l=False, settings=["pull.rebase"], glob=True)
    missing.construct()
    assert "(not set)" in texts(missing)


def test_config_list_global_shows_only_the_global_card(repo):
    from git_sim.config import Config

    scene = Config(l=True, settings=None, glob=True)
    assert scene.cmd == "git config --list --global"
    scene.construct()
    shown = texts(scene)
    assert "~/.gitconfig" in shown and "editor = vim" in shown
    assert ".git/config" not in shown
    assert not any(t.startswith("each scope overrides") for t in shown)
    full = Config(l=True, settings=None)
    full.construct()
    assert ".git/config" in texts(full) and "~/.gitconfig" in texts(full)


def test_config_list_leaves_out_the_system_file_git_is_told_to_skip(repo):
    from git_sim.config import Config

    # the fixture sets GIT_CONFIG_NOSYSTEM, so git config --list shows no system settings
    assert "system\t" not in run_git(repo, "config", "--list", "--show-scope")
    scene = Config(l=True, settings=None)
    assert scene.entries("system") == [] and scene.git_entries("system") == ([], None)


def test_config_local_is_unchanged_by_the_global_option(repo):
    from git_sim.config import Config

    scene = Config(l=False, settings=["user.name", "Bea"])
    assert scene.cmd == "git config user.name Bea"
    scene.construct()
    shown = texts(scene)
    assert ".git/config" in shown and "local" in shown
    assert "name = Bea" in texts(scene, "after")
    assert "name = Ada" not in shown


def test_config_global_compact_drops_the_title(repo):
    from git_sim.config import Config

    settings.compact = True
    scene = Config(l=False, settings=["core.editor", "code --wait"], glob=True)
    scene.construct()
    assert not svg_roles(scene, "title")
    assert "editor = code --wait" in texts(scene, "after")


# ---- check-ignore ------------------------------------------------------------------------


def test_check_ignore_verdicts(repo):
    from git_sim.check_ignore import CheckIgnore

    (repo / "keep.tmp").write_text("x\n")
    scene = CheckIgnore(paths=["error.log", "keep.tmp", "app.py", "debug.log", "cache.db", "a.swp"], verbose=False)
    assert scene.cmd == "git check-ignore error.log keep.tmp app.py debug.log cache.db a.swp"
    assert scene.verdict("error.log") == ("ignored", (".gitignore", 1, "*.log"))
    assert scene.verdict("keep.tmp") == ("unignored", (".gitignore", 5, "!keep.tmp"))
    assert scene.verdict("app.py") == ("none", None)
    # tracked: git itself reports no match, --no-index names the rule
    assert scene.verdict("debug.log") == ("tracked", (".gitignore", 1, "*.log"))
    assert scene.verdict("cache.db") == ("ignored", (".git/info/exclude", 7, "cache.db"))
    kind, rule = scene.verdict("a.swp")
    assert kind == "ignored" and rule[1:] == (1, "*.swp") and os.path.isabs(rule[0])

    scene.construct()
    shown = texts(scene)
    assert ".gitignore" in shown and ".git/info/exclude" in shown
    assert "ignored by .gitignore:1  *.log" in shown
    assert any("un-ignored by .gitignore:5" in t for t in shown)
    assert "not ignored: no rule matches it" in shown
    assert "tracked, so .gitignore doesn't apply" in shown
    assert "<- error.log, debug.log" in shown
    # without -v git prints the ignored paths only, in the order given
    printed = shown[shown.index("git check-ignore prints") + 1 :]
    assert printed[:3] == ["error.log", "cache.db", "a.swp"]


def test_check_ignore_verbose_prints_the_rules(repo):
    from git_sim.check_ignore import CheckIgnore

    scene = CheckIgnore(paths=["error.log", "keep.tmp"], verbose=True)
    assert scene.cmd == "git check-ignore -v error.log keep.tmp"
    scene.construct()
    shown = texts(scene)
    assert "git check-ignore -v prints" in shown
    assert ".gitignore:1:*.log  error.log" in shown
    # -v also prints the ! line that un-ignores a path
    assert ".gitignore:5:!keep.tmp  keep.tmp" in shown


def test_check_ignore_without_a_gitignore(repo):
    from git_sim.check_ignore import CheckIgnore

    run_git(repo, "rm", "-q", "--cached", ".gitignore")
    (repo / ".gitignore").unlink()
    scene = CheckIgnore(paths=["error.log"], verbose=False)
    scene.construct()
    shown = texts(scene)
    assert "(no .gitignore in this repository)" in shown
    assert "not ignored: no rule matches it" in shown
    assert any("exits with status 1" in t for t in shown)


def test_check_ignore_folds_a_long_file_around_the_match(repo):
    from git_sim.check_ignore import CheckIgnore

    (repo / ".gitignore").write_text("".join(f"*.ext{i}\n" for i in range(1, 31)))
    scene = CheckIgnore(paths=["a.ext20"], verbose=False)
    scene.construct()
    shown = texts(scene)
    assert "*.ext20" in shown and "*.ext1" not in shown
    assert "... 17 more lines" in shown and "... 8 more lines" in shown


def test_check_ignore_errors(repo, capsys):
    from git_sim.check_ignore import CheckIgnore

    with pytest.raises(SystemExit):
        CheckIgnore(paths=None, verbose=False)
    assert "no path specified" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        CheckIgnore(paths=["../outside.txt"], verbose=False)
    assert "outside repository" in capsys.readouterr().out


def test_check_ignore_compact_keeps_the_cards(repo):
    from git_sim.check_ignore import CheckIgnore

    settings.compact = True
    scene = CheckIgnore(paths=["error.log"], verbose=True)
    scene.construct()
    assert not svg_roles(scene, "title")
    assert "ignored by .gitignore:1  *.log" in texts(scene)


def test_check_ignore_is_on_the_command_line():
    from typer.testing import CliRunner

    from git_sim.__main__ import app

    result = CliRunner().invoke(app, ["check-ignore", "--help"])
    assert result.exit_code == 0
    assert "--verbose" in result.output
    result = CliRunner().invoke(app, ["config", "--help"])
    assert "--global" in result.output
