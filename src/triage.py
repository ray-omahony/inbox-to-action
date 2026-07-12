"""
Inbox-to-Action: AI document triage tool.

Reads .txt/.md/.pdf files from an input folder, triages each with the
Claude API, and writes a Markdown digest sorted by urgency. Files that
can't be read or triaged appear in the digest as "needs human review"
items instead of vanishing.

Usage:
    python src/triage.py --input samples/ --output output/digest.md
"""

import argparse
import json
import logging
import os
from datetime import date
from pathlib import Path

import anthropic
from pypdf import PasswordType, PdfReader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_KEYS = {
    "summary", "category", "urgency", "urgency_reason",
    "suggested_action", "key_dates", "confidence",
}

URGENCY_ORDER = {"high": 0, "medium": 1, "low": 2}
URGENCY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}

MODEL = "claude-opus-4-8"
# Pricing per million tokens (input, output) — used only for the cost log.
# Check https://platform.claude.com/docs/en/pricing if you change MODEL.
INPUT_PRICE_PER_MTOK = 5.00
OUTPUT_PRICE_PER_MTOK = 25.00

# Resolve the prompt path relative to THIS file, not the current working
# directory — so the script works no matter where you run it from.
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "triage_prompt.md"


def load_prompt_template() -> str:
    """Load the triage prompt from prompts/triage_prompt.md.

    Why a separate file? So you can improve the prompt without touching
    code — and show clients your 'prompt engineering' is maintainable.
    """
    return PROMPT_PATH.read_text(encoding="utf-8")


def extract_text(filepath: Path) -> str:
    """Return plain text from a .txt, .md, or .pdf file.

    This function is the single translation boundary for file-format
    errors: every pypdf failure is converted to ValueError here, so the
    main loop's except (ValueError, OSError) never has to know pypdf exists.
    """
    suffix = filepath.suffix.lower()
    if suffix in {".txt", ".md"}:
        return filepath.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            # strict=False (the default) tolerates minor spec violations —
            # real-world PDFs are messy and we'd rather get the text than be pedantic.
            reader = PdfReader(filepath)
            if reader.is_encrypted:
                # Many "protected" PDFs use an empty user password (print
                # restrictions only) — try that before giving up.
                if reader.decrypt("") == PasswordType.NOT_DECRYPTED:
                    raise ValueError(f"{filepath.name} is password-protected")
            # extract_text() never raises for image-only pages — it returns "",
            # so joining and checking for emptiness is the scanned-PDF detector.
            text = "\n".join(page.extract_text() for page in reader.pages).strip()
        except ValueError:
            # Our own password-protected error above — already in the main
            # loop's contract, so let it through untouched.
            raise
        except Exception as e:
            # Deliberately broad: this function is the documented translation
            # boundary, and pypdf raises outside its own hierarchy (e.g. bare
            # NotImplementedError for unsupported encryption schemes). A
            # boundary that only translates the failures we predicted would
            # still let one weird PDF kill the whole batch.
            raise ValueError(f"unreadable PDF ({type(e).__name__}: {e})") from e
        if not text:
            raise ValueError("no extractable text — scanned/image-only PDF?")
        return text
    # Unknown extension: raise so the caller can skip this file with a
    # warning instead of sending garbage (or crashing) mid-batch.
    raise ValueError(f"Unsupported file type: {suffix}")


def fill_template(template: str, filename: str, text: str) -> str:
    """Substitute {filename} and {document_text} into the prompt.

    We deliberately do NOT use str.format() here: the template contains a
    literal JSON example full of { } braces, which format() would try to
    interpret as placeholders and crash with a KeyError. Plain .replace()
    only touches the two exact placeholders we care about.
    """
    return template.replace("{filename}", filename).replace("{document_text}", text)


def review_record(filename: str, reason: str) -> dict:
    """Uniform 'needs human review' record for any failure path.

    Used by triage_document (API/JSON failures) and main (extraction
    failures) so failed documents always reach the digest instead of
    vanishing into a log line.
    """
    return {
        "filename": filename,
        "summary": f"Could not process automatically ({reason})",
        "category": "other",
        "urgency": "high",  # unknown docs get looked at first, not lost
        "urgency_reason": "Automatic processing failed — needs human review.",
        "suggested_action": "Review this document manually.",
        "key_dates": [],
        "confidence": "low",
        "needs_review": True,  # digest renders these visually distinct
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def triage_document(
    client: anthropic.Anthropic, prompt_template: str, filename: str, text: str
) -> dict:
    """Send one document to Claude, return validated triage JSON.

    Failure policy (from CLAUDE.md): one retry, then return a
    'needs human review' record — a bad response must never crash the batch
    or be silently dropped.
    """
    prompt = fill_template(prompt_template, filename, text)

    last_error = "unknown"
    for attempt in (1, 2):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,  # triage JSON is small; no need for more
                messages=[{"role": "user", "content": prompt}],
            )

            # Cost visibility: the API reports exact token counts on every
            # response, so we log real numbers instead of guessing.
            usage = response.usage
            cost = (
                usage.input_tokens * INPUT_PRICE_PER_MTOK
                + usage.output_tokens * OUTPUT_PRICE_PER_MTOK
            ) / 1_000_000
            logger.info(
                "%s: %d in / %d out tokens, ~$%.4f",
                filename, usage.input_tokens, usage.output_tokens, cost,
            )

            # response.content is a LIST of blocks (text, tool_use, ...).
            # Pull out the first text block rather than assuming content[0].
            raw = next(
                (block.text for block in response.content if block.type == "text"),
                "",
            )
            result = json.loads(raw)
            if not isinstance(result, dict):
                # json.loads accepts arrays, strings, numbers... the model must give
                # us an OBJECT. Raise ValueError so the existing retry/flag policy
                # applies — same failure family as "missing keys".
                raise ValueError(f"expected a JSON object, got {type(result).__name__}")

            # Trust but verify: an LLM can return valid JSON that's still
            # missing fields. Catch that here, not deep in the digest code.
            missing = REQUIRED_KEYS - result.keys()
            if missing:
                raise ValueError(f"response missing keys: {sorted(missing)}")
            # urgency drives the digest's sort key, where a non-string
            # (e.g. ["high"]) would crash AFTER all the API money is spent.
            if not isinstance(result["urgency"], str):
                raise ValueError(
                    f"urgency must be a string, got {type(result['urgency']).__name__}"
                )

            # Bookkeeping fields are OURS — overwrite them all so a document
            # can't steer the model into spoofing them (needs_review would
            # fake the digest's human-review banner).
            result["needs_review"] = False
            result["filename"] = filename
            result["cost_usd"] = round(cost, 4)
            result["input_tokens"] = usage.input_tokens
            result["output_tokens"] = usage.output_tokens
            return result

        # Two failure families, one policy: API errors (network, rate limit,
        # server) and bad-response errors (invalid JSON, missing keys) both
        # get one retry. Anything else is a real bug and should crash loudly.
        except (anthropic.APIError, json.JSONDecodeError, ValueError) as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.warning("%s: attempt %d failed — %s", filename, attempt, last_error)

    logger.error("%s: giving up after retry, flagging for human review", filename)
    return review_record(filename, last_error)


def build_digest(results: list[dict]) -> str:
    """Assemble all triage results into a Markdown digest.

    High urgency first, then a section per document, then a footer with
    token/cost totals. Builds a list of lines and joins once at the end —
    repeated `s += ...` copies the whole string every time.
    """
    lines: list[str] = []
    lines.append(f"# Inbox Triage Digest — {date.today().isoformat()}")
    lines.append("")

    if not results:
        # Still return a complete, valid digest: a zero-byte output file
        # looks like a crash, and main() stays branch-free.
        lines.append("No documents were processed.")
        lines.append("")

    # Unknown urgency values sort to the TOP (0) so a human sees them.
    # Filename as the secondary key makes ordering a property of this
    # function, not of whoever built the list. sorted() never mutates
    # the caller's list.
    ordered = sorted(
        results,
        key=lambda r: (URGENCY_ORDER.get(r["urgency"], 0), r["filename"]),
    )

    for result in ordered:
        urgency = result["urgency"]
        emoji = URGENCY_EMOJI.get(urgency, "⚪")
        lines.append(f"## {emoji} {result['filename']}")
        lines.append("")
        if result.get("needs_review", False):
            lines.append("**NEEDS HUMAN REVIEW** — automatic processing failed.")
            lines.append("")
        lines.append(result["summary"])
        lines.append("")
        lines.append(f"- **Urgency:** {urgency} — {result['urgency_reason']}")
        lines.append(f"- **Category:** {result['category']}")
        lines.append(f"- **Suggested action:** {result['suggested_action']}")
        dates = result["key_dates"]
        # Key PRESENCE is validated, but the model could still return a
        # string — and ", ".join() on a string prints one char per comma.
        key_dates = (
            ", ".join(str(d) for d in dates)
            if isinstance(dates, list) and dates
            else "none"
        )
        lines.append(f"- **Key dates:** {key_dates}")
        lines.append("")

    # .get() defaults so a record missing bookkeeping keys degrades to
    # zero instead of crashing the whole digest.
    total_tokens = sum(
        r.get("input_tokens", 0) + r.get("output_tokens", 0) for r in results
    )
    total_cost = sum(r.get("cost_usd", 0.0) for r in results)
    lines.append("---")
    lines.append("")
    lines.append(
        f"*{len(results)} documents processed · {total_tokens} tokens · "
        f"estimated cost ${total_cost:.4f}*"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="AI document triage")
    parser.add_argument("--input", required=True, help="Folder of documents")
    parser.add_argument("--output", required=True, help="Digest output path")
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        # is_dir() is False for both "doesn't exist" and "is a file" —
        # one check covers both user mistakes.
        logger.error("Input path %s is not a directory (or doesn't exist).", args.input)
        raise SystemExit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("Set the ANTHROPIC_API_KEY environment variable first.")
        raise SystemExit(1)

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY automatically
    prompt_template = load_prompt_template()

    results: list[dict] = []
    # sorted() makes runs deterministic — easier to eyeball and to test.
    for filepath in sorted(input_dir.iterdir()):
        if filepath.name.startswith("."):  # .DS_Store etc. — macOS drops these everywhere
            # debug, not warning: dotfiles are almost never real documents,
            # but a trace should exist for the rare .report.pdf case.
            logger.debug("Skipping dotfile %s", filepath.name)
            continue
        if not filepath.is_file():
            continue
        try:
            text = extract_text(filepath)
        except (ValueError, OSError) as e:
            # One unreadable file must never kill the batch — and it must not
            # vanish either: it goes into the digest as a review item.
            logger.warning("Flagging %s for human review: %s", filepath.name, e)
            results.append(review_record(filepath.name, str(e)))
            continue
        results.append(triage_document(client, prompt_template, filepath.name, text))

    digest = build_digest(results)
    output_path = Path(args.output)
    # Create the parent dir if missing. exist_ok=True makes this a no-op
    # when it already exists — no check-then-create race, one line.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(digest, encoding="utf-8")
    logger.info("Processed %d document(s); digest written to %s", len(results), output_path)
    print(f"Digest written to {output_path}")


if __name__ == "__main__":
    main()
