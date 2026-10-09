## What would this do?

`Ctrl+Alt+G` opens a prompt with `git-sim ` already typed. Finish the command the way you would in a terminal:

```
git-sim rebase main
git-sim reset --hard HEAD~2
git-sim merge feature
git-sim stash
```

The command plays out in an editor tab on a before / after graph of your repo. A rebase replays one commit at a time, a reset shows which commits fall out of reach, a merge shows whether it fast-forwards, and a stash moves files between the working directory and the stash.

Drag the slider or press play. Hover a commit for its message, author, date, and parents, and click it to copy its hash. Ctrl + mouse wheel zooms. The **Share** menu copies a link or saves the graph as an image or a page.

You can also select a command in a file, like a README or a script, and choose **Simulate the selected command** from the right-click menu. In the terminal, select a command and choose **Simulate a Git command...** from the right-click menu. Or use the beaker button in the Source Control view's toolbar.
