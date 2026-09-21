## Install git-sim

The extension is a thin client: git-sim itself reads your repository, works out
what a command would do, and draws it. Install it once, on your PATH:

```
pipx install git-sim
```

or `uv tool install git-sim`, or `pip install git-sim`. Python 3.10 or newer
and Git are required.

If git-sim lives somewhere unusual, point the `git-sim.executable` setting at
it. The status bar entry turns from "git-sim: not found" to "git-sim" when the
extension can run it.

Nothing in your repository is ever modified by git-sim. Simulations and live
sessions are saved in your user cache folder (`git-sim media-dir` prints it).
