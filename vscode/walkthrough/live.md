## What just happened?

**git-sim: Live graph** opens a graph that follows the repository. After every
change, whoever made it (you in the terminal, the Source Control view, an AI
agent), the graph plays the change the way a simulation does: the new commit
fades in, labels slide over, a dropped branch fades out, a staged file crosses
to its column.

Every change stays in the strip above the graph:

- click one to see it again, `[` and `]` step through them;
- **Replay all** plays the session end to end;
- **Save session** writes the whole session as one HTML file that opens anywhere;
- **Record video** records the replay as an MP4 or WebM to post.

The same graph is a view in the sidebar (the git-sim icon in the Activity Bar).
Drag it into the secondary sidebar under your AI chat, or into the panel next to
the terminal, and it follows along. The sidebar draws the commit graph without
the status table; change that with `git-sim.liveZones`.

**git-sim: Open a recorded live session...** lists past sessions of the
repository and opens one.
