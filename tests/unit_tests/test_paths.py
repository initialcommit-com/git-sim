"""Where simulations are saved: a per-user folder outside any repository."""

import pathlib

from git_sim import paths


def test_default_root_is_the_user_cache_area(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert paths.default_media_root() == tmp_path / "Local"
    monkeypatch.delenv("LOCALAPPDATA")
    assert paths.default_media_root() == tmp_path / "AppData" / "Local"
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    assert paths.default_media_root() == tmp_path / "Library" / "Caches"
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    assert paths.default_media_root() == tmp_path / ".cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert paths.default_media_root() == tmp_path / "xdg"


def test_media_folder_before_and_after_the_cli_appends_to_it(monkeypatch, tmp_path):
    from git_sim.settings import settings

    monkeypatch.setattr(settings, "media_dir", tmp_path)
    assert paths.media_folder() == tmp_path / "git-sim_media"
    monkeypatch.setattr(
        settings, "media_dir", str(tmp_path / "git-sim_media" / "myrepo")
    )
    assert paths.media_folder() == tmp_path / "git-sim_media"
    assert paths.inbox_dir() == tmp_path / "git-sim_media" / "inbox"


def test_settings_default_is_outside_the_working_directory(monkeypatch):
    from git_sim.settings import Settings

    monkeypatch.delenv("git_sim_media_dir", raising=False)
    default = pathlib.Path(Settings().media_dir)
    assert default == paths.default_media_root()
    assert default != pathlib.Path.cwd()
    monkeypatch.setenv("git_sim_media_dir", "D:/elsewhere")
    assert str(Settings().media_dir).replace("\\", "/") == "D:/elsewhere"
