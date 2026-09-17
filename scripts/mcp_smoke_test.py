"""Smoke test: talk to the git-sim MCP server over the real stdio transport."""

import asyncio
import json
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    repo_path = sys.argv[1] if len(sys.argv) > 1 else "."
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "git_sim.mcp_server"]
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            result = await session.call_tool(
                "git_preflight",
                {"command": "git clean -fd", "repo_path": repo_path},
            )
            for block in result.content:
                if block.type == "text":
                    report = json.loads(block.text)
                    print("RISK:", report["risk"])
                    print("SUMMARY:", report["summary"])
                    print("WOULD_LOSE:", report["would_lose"][:5])
                    print("IMAGE_PATH:", report.get("simulation_image"))
                elif block.type == "image":
                    print(f"IMAGE CONTENT: {block.mime_type}, {len(block.data)} b64 chars")


if __name__ == "__main__":
    asyncio.run(main())
