## What would this do?

`Ctrl+Alt+G` opens a prompt with `git-sim ` already typed. Finish it as you
would in a terminal:

```
git-sim rebase main
git-sim reset --hard HEAD~2
git-sim merge feature
git-sim stash
```

The command plays out in an editor tab on a before / after graph of your real
repository: a rebase replays one commit at a time, a reset shows what falls out
of reach, a merge shows whether it fast-forwards, a stash moves files between
the working directory and the stash.

Drag the slider or press play. Hover a commit for its message, author, date and
parents; click to copy its sha; ctrl + wheel zooms. Share copies a link or an
image.

Also: select a command in a script, a README or the terminal and choose
**Simulate the selected command** from the context menu, or the beaker button
in the Source Control view's title bar.
