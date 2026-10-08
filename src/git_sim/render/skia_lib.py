"""skia, loaded with a clear message when the system can't load it.

skia-python links to the system's libEGL, libGL, and fontconfig on Linux.
Desktop installs have them; servers, Docker images, CI machines, and WSL
often don't, and the import then fails with a bare ImportError naming a
.so file. git-sim says what is missing and how to install it instead.
"""

import sys

_LINUX_HELP = """\
git-sim error: the skia drawing library couldn't load a system library it needs:
  {error}

Linux needs libEGL, libGL, and fontconfig, which minimal installs such as
servers, Docker images, CI machines, and WSL often lack. Install them with:
  Debian or Ubuntu:  sudo apt install libegl1 libgl1 libfontconfig1
  Fedora or RHEL:    sudo dnf install mesa-libEGL mesa-libGL fontconfig
then run git-sim again."""

_OTHER_HELP = """\
git-sim error: the skia drawing library couldn't load:
  {error}

Installing it again often fixes this: pip install --force-reinstall skia-python"""


def load_skia():
    try:
        import skia
    except ImportError as error:
        missing_library = sys.platform.startswith("linux") and ".so" in str(error)
        help_text = _LINUX_HELP if missing_library else _OTHER_HELP
        print(help_text.format(error=error), file=sys.stderr)
        sys.exit(1)
    return skia
