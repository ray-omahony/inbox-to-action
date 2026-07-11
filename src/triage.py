"""
Inbox-to-Action: AI document triage tool.

This is a SKELETON. Build it step by step with Claude Code — the structure
and TODOs below are your roadmap. Writing it yourself (with Claude Code
explaining each part) is the point: you'll be able to defend every line
in a client call.

Usage:
    python src/triage.py --input samples/ --output output/digest.md
"""

import argparse
import json
import logging
import os
from pathlib import Path

# TODO (Day 1): pip install anthropic pypdf, then import them here
# from anthropic import Anthropic
# from pypdf import PdfReader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_KEYS = {
    "summary", "category", "urgency", "urgency_reason",
    "suggested_action", "key_dates", "confidence",
}


def load_prompt_template() -> str:
    """Load the triage prompt from prompts/triage_prompt.md.

    TODO (Day 1): read the file and return its contents.
    Why a separate file? So you can improve the prompt without touching
    code — and show clients your 'prompt engineering' is maintainable.
    """
    raise NotImplementedError


def extract_text(filepath: Path) -> str:
    """Return plain text from a .pdf, .txt, or .md file.

    TODO (Day 3): 
    - .txt / .md -> just read the file
    - .pdf -> use pypdf's PdfReader, join text from all pages
    - unknown extension -> raise ValueError (caller will skip + warn)
    """
    raise NotImplementedError


def triage_document(client, prompt_template: str, filename: str, text: str) -> dict:
    """Send one document to Claude, return validated triage JSON.

    TODO (Day 1-2):
    - Fill the template's {filename} and {document_text} placeholders
    - Call client.messages.create(...) — check the current recommended
      model at https://docs.claude.com/en/docs/about-claude/models
    - Parse response as JSON
    - Validate all REQUIRED_KEYS are present
    - On failure: retry ONCE, then return a 'needs human review' record
    - Log input/output tokens from the API response for cost tracking
    """
    raise NotImplementedError


def build_digest(results: list[dict]) -> str:
    """Assemble all triage results into a Markdown digest.

    TODO (Day 4):
    - Sort by urgency (high first)
    - Emoji indicators: 🔴 high, 🟡 medium, 🟢 low
    - Section per document: filename, summary, action, key dates
    - Footer: total docs processed, total tokens, estimated cost
    """
    raise NotImplementedError


def main() -> None:
    parser = argparse.ArgumentParser(description="AI document triage")
    parser.add_argument("--input", required=True, help="Folder of documents")
    parser.add_argument("--output", required=True, help="Digest output path")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("Set the ANTHROPIC_API_KEY environment variable first.")
        raise SystemExit(1)

    # TODO (Day 2-3): 
    # 1. client = Anthropic()  (reads the env var automatically)
    # 2. prompt_template = load_prompt_template()
    # 3. Loop over files in args.input:
    #    - extract_text() in try/except — skip bad files with a warning,
    #      never let one corrupt PDF kill the whole batch
    #    - triage_document() and collect results
    # 4. digest = build_digest(results)
    # 5. Write digest to args.output, log the path

    logger.info("Skeleton ready — build me with Claude Code!")


if __name__ == "__main__":
    main()
