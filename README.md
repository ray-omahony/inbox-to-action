# Inbox-to-Action 📥→✅

**AI-powered document triage for busy teams.**

Drop a folder of messy emails, PDFs, and notes in — get back a clean daily digest telling you what each document is, how urgent it is, and what to do about it.

> Built by Ray O'Mahony — 18 years in enterprise infrastructure & operations (Adobe, Qualcomm). AWS Certified Solutions Architect & Developer.

---

## What it does

For every document in a folder, Inbox-to-Action produces:

| Field | Example |
|---|---|
| **Summary** | "Invoice from Acme Ltd for €1,240, due 15 August." |
| **Category** | Invoice / Support Request / Contract / Meeting Notes / FYI |
| **Urgency** | 🔴 High / 🟡 Medium / 🟢 Low |
| **Suggested action** | "Forward to accounts payable before Friday." |

Then it compiles everything into a single **daily digest** (Markdown) you can read in two minutes.

## Why it's useful

- **Processes 50 documents in ~2 minutes** instead of an hour of manual reading
- **Costs under a cent per document** — measured $0.007–0.009/doc with Claude Opus 4.8; every run logs its exact token usage and cost
- **Nothing leaves your machine** except the document text sent to the API — no third-party SaaS, no subscriptions
- Works on `.pdf`, `.txt`, and `.md` files

## Quick start

```bash
git clone https://github.com/ray-omahony/inbox-to-action.git
cd inbox-to-action
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key-here"
python src/triage.py --input samples/ --output output/digest.md
```

## Example

**Input:** (see `samples/` for the actual files)
- A rambling customer complaint email
- A supplier invoice PDF
- Untidy meeting notes

**Output:** [`output/example_digest.md`](output/example_digest.md)

*(Add a before/after screenshot here — this is the money shot for your portfolio.)*

## How it works

1. **Extract** — pulls plain text from each file (`pypdf` for PDFs)
2. **Analyze** — sends the text to Claude with a carefully structured prompt (see [`prompts/triage_prompt.md`](prompts/triage_prompt.md)) that forces a strict JSON response
3. **Validate** — checks the JSON against a schema; malformed responses are retried once, then flagged for human review (never silently dropped)
4. **Report** — assembles all results into a single digest, sorted by urgency

## Design decisions

- **Strict JSON output with validation** — LLMs occasionally return malformed data; production tools must handle that, not hope it away
- **Per-document cost logging** — every run prints token usage and estimated cost, so there are no billing surprises
- **Graceful failures** — a corrupt PDF skips with a warning; one bad file never kills the batch

## Use it from Claude Desktop (MCP)

The tool doubles as an [MCP](https://modelcontextprotocol.io) server, so Claude Desktop can triage a folder mid-conversation ("triage everything in ~/Desktop/inbox and tell me what's urgent"). Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "inbox-to-action": {
      "command": "/bin/zsh",
      "args": ["-c", "source ~/.zshrc 2>/dev/null; exec /path/to/inbox-to-action/.venv/bin/python /path/to/inbox-to-action/src/mcp_server.py"]
    }
  }
}
```

The `zsh -c 'source ~/.zshrc; ...'` wrapper matters: MCP hosts launch servers with a minimal environment, so the `ANTHROPIC_API_KEY` from your shell profile must be loaded by the launch command itself.

## Roadmap

- [x] MCP server wrapper so Claude Desktop can triage folders directly
- [ ] `.eml` email file support
- [ ] Email inbox integration (IMAP)
- [ ] Configurable categories per client

## License

MIT
