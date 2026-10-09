## What just happened?

**git-sim: Live graph** opens a graph that follows your repo. Every change plays the moment it happens, whether you did it in the terminal, in the Source Control view, or an AI agent did it. New commits fade in, branch labels slide over, deleted branches fade out, and staged files move to their column.

Each change is kept in the strip above the graph:

- click a change to see it again, or press `[` and `]` to step through them
- **Replay all** plays the whole session
- **Save session** saves the session as one HTML page that opens anywhere
- **Record video** records the replay as an MP4 or WebM

The live graph is also a view in the sidebar (the git-sim icon in the Activity Bar). Drag it next to your AI chat or your terminal and it follows along. The sidebar leaves out the table of untracked, modified, and staged files. Change that with `git-sim.liveZones`.

**git-sim: Open a recorded live session...** lists your repo's past sessions and opens one.
