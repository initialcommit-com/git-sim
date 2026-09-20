"""Where git-sim keeps what it writes.

Simulations land under a ``git-sim_media`` folder. By default that folder
lives in the user's cache area, outside any repository, so a run from inside a
project never litters it: ``%LOCALAPPDATA%`` on Windows, ``~/Library/Caches``
on macOS, ``$XDG_CACHE_HOME`` (else ``~/.cache``) elsewhere. ``--media-dir``
or the ``git_sim_media_dir`` environment variable move it. Below the folder,
each repository gets a subfolder by name, then ``images/``.

``git-sim media-dir`` prints the folder in use, for tools (the VS Code
extension watches its ``inbox/`` for pages the agent hook writes).
"""

import os
import pathlib
import sys

import typer

MEDIA_FOLDER = "git-sim_media"


def default_media_root() -> pathlib.Path:
    """The per-user directory the git-sim_media folder is created in."""
    home = pathlib.Path.home()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return pathlib.Path(base) if base else home / "AppData" / "Local"
    if sys.platform == "darwin":
        return home / "Library" / "Caches"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return pathlib.Path(xdg) if xdg else home / ".cache"


def media_folder() -> pathlib.Path:
    """The git-sim_media folder in use. Works before the CLI callback has
    appended the folder and repository name to settings.media_dir, and after."""
    from git_sim.settings import settings

    path = pathlib.Path(os.path.expanduser(str(settings.media_dir)))
    for candidate in (path, *path.parents):
        if candidate.name == MEDIA_FOLDER:
            return candidate
    return path / MEDIA_FOLDER


def inbox_dir() -> pathlib.Path:
    """Where the agent hook leaves a note about each interactive page it wrote
    for an editor to open (one small JSON file per simulation)."""
    return media_folder() / "inbox"


def media_dir():
    """Print the folder simulations are saved in (git-sim_media): the default
    per-user location, or the one given by --media-dir / git_sim_media_dir."""
    typer.echo(media_folder().as_posix())
