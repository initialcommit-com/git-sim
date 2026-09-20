# git-sim live

`git-sim live` follows a repository and keeps an animated graph of it up to
date. Every change plays as a before / after animation the moment it happens,
whoever made it, and stays in a strip so the session can be stepped back
through or replayed. It runs in a browser (`git-sim live`) or inside VS Code
(the extension's **Live graph** tab and sidebar view, see [vscode.md](vscode.md)).

## Using it

```
$ git-sim live                 # this repository, in the browser
$ git-sim --all live -C ../x   # every branch of another repository
$ git-sim live --no-zones      # the commit graph without the status table
```

Commit, branch, switch, reset, rebase, stash, stage a file: the page plays
each change and adds it to the strip. Click a change to see it again, `[` and
`]` step through them, **Replay all** plays the session end to end, **Follow**
returns to following the latest change, **Clear** forgets the recorded changes
and starts from the current state. Shift+click opens a change as a page of
its own. Each change is saved as a standalone interactive page under
`git-sim media-dir`, in `<repo>/live/<session>/`.

## Saving and sharing a session

- **Save session** writes the whole session as one HTML file: every change,
  the strip, the viewer, nothing to install. Attach it to a pull request,
  email it, drop it in a chat; it opens anywhere, steps through the changes,
  and can still record the video below. The same file is kept current as
  `session.html` in the session folder while live mode runs.
- **Record video** plays the session's changes one after another and
  records them frame by frame (MP4 where the browser can encode it, WebM
  otherwise, 1600 px wide, paced as the page plays). Esc stops early. That
  is the thing to post on X, Bluesky or LinkedIn, which do not carry links
  as long as a graph.
- `git-sim live --sessions` lists the repository's recorded sessions and
  `git-sim live --replay` opens the latest (`--session <folder>` for another)
  in the browser. In VS Code, **git-sim: Open a recorded live session...**.

Options: `--no-zones`, `--interval <seconds>` (default 1), `--port <n>`,
`--json` (one JSON line per change, for editors), `--once` (draw the current
state and exit), `--sessions`, `--replay [--session <path>]`, `-C <repo>`. The global `--open-in local` opens the page
served by git-sim itself instead of the hosted one, and `-d` opens nothing
and just prints the addresses. Global options (`--all`, `-n`, `--light-mode`,
`--media-dir`) apply to every drawing; live mode shows up to three branch
labels per commit unless `--max-branches-per-commit` says otherwise.

## How it works

**Watching.** Nothing inside `.git` is watched directly: between polls the
command compares what git reports (HEAD, `for-each-ref`, `status --porcelain`,
`stash list`), so it never fires on git's own housekeeping and never misses a
change made by another program. A change is drawn once the repository has held
still for a moment, so a rebase or a pull is one change, not twenty.

**Naming the change.** New entries in the HEAD reflog name the command that
ran (`commit: ...` → `git commit`, `reset: moving to X` → `git reset X`,
`checkout: moving from A to B` → `git checkout B`, or `git checkout -b B` when
B is new). Changes that leave no reflog entry are read from the difference of
the two readings: a branch or tag created, deleted or renamed, a stash pushed
or popped, files staged, unstaged, edited, created or deleted, remote-tracking
branches fetched.

**Drawing the change.** The repository is drawn after the change (the commit
graph with git log's branch selection, plus the untracked / modified / staged
table) and the drawing from before it is merged with the new one into a
single SVG carrying the same attributes a simulation carries: elements are
matched by what they stand for (a commit by its sha, a pill by its name, an
arrow by the commits it joins, a file by its name). A matched element that
only translated slides; one whose shape changed fades out and back in; one
present only before fades out; one present only after fades in. The two
drawings usually frame the camera differently, so the earlier one is first
re-projected into the later one's pixel space using the camera data the SVG
painter writes on the `<svg>` root. The interactive viewer plays the result
unchanged, which is why a live change looks exactly like a simulation and can
be shared the same way.

**Serving it.** In the browser mode a small HTTP server on `127.0.0.1` serves
the page, `/history`, `/svg/<n>`, `/page/<n>` and an `/events` stream
(server-sent events). By default the page that opens is the one hosted at
`initialcommit.com/tools/git-sim/live`, with the local server's address and a
per-session key in the URL fragment (`#live=http://127.0.0.1:PORT&k=KEY`),
which the browser never sends to the site: the site serves the page, the
graphs come from the local server, exactly the split shared simulations
use. The local server allows cross-origin requests from the viewer's origin
only and refuses every data request without the key, so a page you happen
to visit cannot read your repository graph off localhost. Chrome and Edge
ask once for permission to reach the local network; if a browser refuses,
the hosted page offers the local copy (`--open-in local` opens it directly).
The hosted page's strip, stylesheet and script are exported from the
package by `python -m git_sim.render.html <dir>` along with the viewer's
assets, so the two copies are the same code.

In `--json` mode there is no server: the command prints one line per change
and exits when its stdin closes, so an editor's process never outlives the
window. Set `GIT_SIM_LIVE_DEBUG=1` to have each detected change logged on
stderr.
