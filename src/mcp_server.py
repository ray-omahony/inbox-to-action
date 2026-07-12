"""MCP server: lets Claude Desktop triage a folder of documents on request.

MCP (Model Context Protocol) is how Claude Desktop talks to local tools.
This server exposes one tool, triage_folder — Desktop launches this script
as a subprocess and exchanges JSON-RPC messages with it over stdio.

CRITICAL for stdio servers: stdout belongs to the protocol. A stray
print() here would corrupt the message stream and disconnect the server.
All human-facing output must go through logging (which writes to stderr).

Run manually (for debugging):  .venv/bin/python src/mcp_server.py
Normally it is launched by Claude Desktop via claude_desktop_config.json.
"""

import logging
import os
from pathlib import Path

import anthropic
from mcp.server.fastmcp import FastMCP

# Same-directory import: Desktop launches us with src/ as the script dir,
# so triage.py is importable without packaging ceremony.
import triage

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("inbox-to-action")


@mcp.tool()
def triage_folder(folder: str) -> str:
    """Triage every document (.txt, .md, .pdf) in a folder and return a
    Markdown digest sorted by urgency.

    Each document gets a summary, category, urgency rating, and a concrete
    suggested action. Unreadable files are flagged for human review rather
    than skipped. Costs roughly one cent per document in Claude API usage.

    Args:
        folder: Path to a folder of documents (e.g. /Users/ray/Desktop/inbox).
    """
    # Tool errors are returned as text, not raised: Claude reads the message
    # and can tell the user what to fix, instead of seeing an opaque failure.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return (
            "Error: ANTHROPIC_API_KEY is not set for the MCP server. "
            "Add it to the server's env in claude_desktop_config.json."
        )

    input_dir = Path(folder).expanduser()
    if not input_dir.is_dir():
        return f"Error: {folder} is not a folder (or doesn't exist)."

    client = anthropic.Anthropic()
    results = triage.triage_folder(client, input_dir)
    logger.info("Triaged %d document(s) in %s", len(results), input_dir)
    return triage.build_digest(results)


if __name__ == "__main__":
    # stdio is the transport Claude Desktop expects; mcp.run() blocks and
    # serves until Desktop closes the pipe.
    mcp.run()
