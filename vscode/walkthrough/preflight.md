## Is this safe?

**git-sim: Pre-flight a Git command...** asks for a command and shows you:

- the risk level: safe, caution, or destructive
- which commits would become unreachable
- which uncommitted changes would be lost, and whether you could get them back
- the command that undoes it
- a text graph of the branches involved

git-sim works this out from your repo, not by guessing, and it's the same check the AI agent hook runs. The report has a **Simulate it** button to see the command on a graph.

In a terminal, the same check is `git-sim preflight <command>`, or `git preflight <command>` after you run `git-sim aliases`.
