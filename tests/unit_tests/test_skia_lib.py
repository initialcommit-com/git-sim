"""When skia can't load, git-sim says why and how to fix it instead of a traceback."""

import builtins
import sys

import pytest

from git_sim.render.skia_lib import load_skia


def fail_import(monkeypatch, message):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "skia":
            raise ImportError(message)
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "skia", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_a_missing_linux_library_names_the_packages_to_install(monkeypatch, capsys):
    fail_import(monkeypatch, "libEGL.so.1: cannot open shared object file: No such file or directory")
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(SystemExit) as exit_info:
        load_skia()
    assert exit_info.value.code == 1
    err = capsys.readouterr().err
    assert "libEGL.so.1" in err
    assert "sudo apt install libegl1 libgl1 libfontconfig1" in err
    assert "sudo dnf install mesa-libEGL mesa-libGL fontconfig" in err


def test_other_failures_suggest_installing_skia_again(monkeypatch, capsys):
    fail_import(monkeypatch, "No module named 'skia'")
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(SystemExit):
        load_skia()
    err = capsys.readouterr().err
    assert "pip install --force-reinstall skia-python" in err
    assert "apt install" not in err


def test_skia_loads_when_it_can():
    assert load_skia().Surface is not None
