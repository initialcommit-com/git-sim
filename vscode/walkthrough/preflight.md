## Is this safe?

**git-sim: Pre-flight a Git command** asks for a command and shows a report:

- the risk level: safe, caution or destructive;
- exactly which commits would become unreachable;
- which uncommitted changes would be lost, and whether they can be recovered;
- how to undo the command;
- a text graph of the branches involved.

It is computed from the repository by code, never guessed, and it is the same
check the AI agent hook runs. The report has a **Simulate it** button.

In a terminal the same check is `git-sim preflight <command>`, or
`git preflight <command>` after `git-sim aliases`.
