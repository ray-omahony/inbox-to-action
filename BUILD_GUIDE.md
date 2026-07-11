# Build Guide — your 7-day plan

Work through this **with Claude Code** on your Mac. The CLAUDE.md file in this
folder tells Claude Code you're learning — it will explain as it goes. Your
job: understand every line well enough to explain it to a client.

## Day 0 — Setup (30 min)
```bash
cd ~/Projects        # or wherever you keep code
mv ~/Downloads/inbox-to-action .   # this starter kit
cd inbox-to-action
git init
git add .
git commit -m "Initial project skeleton"
```
Create the GitHub repo: github.com → New repository → "inbox-to-action" →
**public** (it's a portfolio piece). Then:
```bash
git remote add origin https://github.com/YOURUSERNAME/inbox-to-action.git
git push -u origin main
```
Get an API key at console.anthropic.com (add ~€5 credit — this whole project
will cost under €2 to build and test). Then:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # add to ~/.zshrc to persist
```

## Day 1-2 — Core API call
Open Claude Code in the project folder (`claude`) and start with:
> "Read CLAUDE.md and src/triage.py. Help me implement load_prompt_template()
> and triage_document() for .txt files only. Explain the Anthropic SDK call
> as we go — I want to understand it, not just paste it."

✅ Done when: one .txt file goes in, valid JSON comes out.
`git commit -m "Working triage for txt files"` — push it.

## Day 3 — PDFs + the folder loop
> "Now implement extract_text() with pypdf support, and the main loop.
> Make sure one bad file can't crash the batch."

✅ Done when: `python src/triage.py --input samples/ --output output/digest.md`
processes all three sample files without dying.

## Day 4 — The digest
> "Implement build_digest() — sorted by urgency, with the cost footer."

✅ Done when: the output digest reads cleanly and shows cost. Copy your best
run to `output/example_digest.md` and commit it — that's portfolio evidence.

## Day 5-6 — Polish (this is where money is made)
- Update README: your GitHub username, real cost numbers from your runs
- Take a screenshot: messy sample files on the left, clean digest on the right
- Ask Claude Code: "Review this whole project as a senior engineer.
  What would embarrass me in a code review?" — fix what it finds
- Add 2-3 pytest tests (ask Claude Code to teach you the basics)

## Day 7 — The demo
- Record 60 seconds with QuickTime: show the samples folder, run the command,
  scroll the digest. No talking-head needed, just captions.
- This video + the GitHub link = your Upwork portfolio item #1

## Week 2 stretch — MCP wrapper
Ask Claude Code: "Wrap this as an MCP server so Claude Desktop can triage a
folder on request." Now you have an *agent tools* portfolio piece — rare on
Upwork, and squarely on your Claude SME path.

## Rules for working with Claude Code (learning mode)
1. Never accept code you don't understand — ask "explain that line"
2. Type the small stuff yourself; let Claude Code do boilerplate
3. Commit after every working feature (Claude Code will remind you —
   it's in CLAUDE.md)
4. When something breaks, try to read the error yourself FIRST, then ask
