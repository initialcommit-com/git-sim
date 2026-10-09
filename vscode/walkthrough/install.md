## Install git-sim

The extension runs the git-sim command line tool, which reads your repo, works out what a command would do, and draws it. Install it once:

```
pipx install git-sim
```

Or `pip install git-sim`, or `uv tool install git-sim`. git-sim needs Python 3.10 to 3.14 and Git.

Minimal Linux systems (servers, containers, WSL) may also need the graphics libraries git-sim draws with. On Debian, Ubuntu, or WSL:

```
sudo apt install libegl1 libgl1 libfontconfig1
```

The status bar changes from "git-sim: not found" to "git-sim" once the extension finds it. If git-sim isn't on your `PATH`, set `git-sim.executable` to its full path.

git-sim never changes your repo. Simulations and live sessions are saved in your user cache folder (`git-sim media-dir` shows where).
