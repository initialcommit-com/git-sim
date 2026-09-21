## A human in the loop

AI coding agents run Git on your behalf, and they run it fast. **git-sim: Wire
git-sim into AI coding agents** runs `git-sim install`, which detects the agents
on your machine and writes into each one's own configuration:

- a **pre-flight hook** (Claude Code, Codex CLI, Cursor, GitHub Copilot CLI,
  Gemini CLI, and Copilot in VS Code) that stops the agent before a destructive
  Git command and asks you to approve it, with the facts, a text graph and the
  simulation in front of you;
- the **MCP server**, which also reaches Windsurf, Cline, Roo Code, Amazon Q
  Developer CLI and Claude Desktop, so the agent can check or simulate a
  command itself.

Restart the agents afterwards; they read their configuration at startup. In VS
Code, use Copilot in Agent mode, where hooks and tools apply. When the hook
stops a command, the simulation opens in an editor tab here.

Keep the live graph open beside the agent and you also see everything it does
the moment it does it.
