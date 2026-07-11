# CLAUDE.md — Inbox-to-Action

## Project overview
A Python CLI tool that reads documents (PDF, TXT, MD) from an input folder, sends each to the Claude API for triage (summary, category, urgency, suggested action as strict JSON), and compiles a Markdown digest sorted by urgency.

## Who is building this
Ray — experienced infrastructure/ops engineer (Linux, AWS, monitoring), **learning Python and software best practices**. When writing code:
- Explain *why*, not just *what* — short comments on non-obvious choices
- Prefer readable code over clever code
- Point out best practices as we go (error handling, logging, project structure)
- When I make a mistake, tell me directly and explain the fix

## Tech constraints
- Python 3.11+, standard library where possible
- Dependencies: `anthropic`, `pypdf` only (keep it lean)
- API key from `ANTHROPIC_API_KEY` env var — NEVER hardcode keys
- The triage prompt lives in `prompts/triage_prompt.md` — load it from the file, don't embed it in code

## Code standards
- Type hints on all functions
- `logging` module, not print() (except final user-facing output)
- Every API call wrapped in try/except with a retry (1 retry, then flag the doc as "needs human review")
- Validate the JSON response has all required keys before using it
- Log token usage and estimated cost per document

## Project structure
```
src/triage.py        # main CLI script
prompts/             # the LLM prompt (edit here, not in code)
samples/             # test input files
output/              # generated digests (gitignored except example)
```

## Commands
- Run: `python src/triage.py --input samples/ --output output/digest.md`
- We'll add tests later with pytest — remind me when the core works

## Git workflow
- Small commits with clear messages ("Add PDF text extraction", not "updates")
- Remind me to commit after each working feature
