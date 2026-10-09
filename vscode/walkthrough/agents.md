## Keep a human in the loop

AI coding agents run Git commands for you, and they run them fast. **git-sim: Wire git-sim into AI coding agents** runs `git-sim wire-agents`, which finds the agents on your machine and sets up two things in each one:

- **A pre-flight hook** for Claude Code, Codex CLI, Cursor, GitHub Copilot CLI, Gemini CLI, and Copilot in VS Code. It stops the agent before a destructive Git command and asks you to approve it, showing what it would lose, how to undo it, and the simulation.
- **The git-sim MCP server**, so the agent can check or simulate a command itself. This also covers Windsurf, Cline, Roo Code, Amazon Q Developer CLI, and Claude Desktop.

Restart your agents afterwards, since they read their settings when they start. In VS Code, use Copilot in Agent mode, which is where hooks and tools apply. When the hook stops a command, its simulation opens in an editor tab here.

Keep the live graph open beside your agent to see everything it does as it happens.
