"""
Inbox-to-Action: AI document triage tool.

Day 3 state: .txt/.md/.pdf files are extracted and triaged end to end,
and a corrupt file is skipped without killing the batch. Still TODO:
the Markdown digest (Day 4).

Usage:
    python src/triage.py --input samples/ --output output/digest.md
"""

import argparse
import json
import logging
import os
from pathlib import Path

import anthropic
from pypdf import PasswordType, PdfReader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_KEYS = {
    "summary", "category", "urgency", "urgency_reason",
    "suggested_action", "key_dates", "confidence",
}

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

            # Trust but verify: an LLM can return valid JSON that's still
            # missing fields. Catch that here, not deep in the digest code.
            missing = REQUIRED_KEYS - result.keys()
            if missing:
                raise ValueError(f"response missing keys: {sorted(missing)}")

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
    return {
        "filename": filename,
        "summary": f"Could not triage automatically ({last_error})",
        "category": "other",
        "urgency": "high",  # unknown docs get looked at first, not lost
        "urgency_reason": "Automatic triage failed — needs human review.",
        "suggested_action": "Review this document manually.",
        "key_dates": [],
        "confidence": "low",
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


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

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY automatically
    prompt_template = load_prompt_template()

    results: list[dict] = []
    # sorted() makes runs deterministic — easier to eyeball and to test.
    for filepath in sorted(Path(args.input).iterdir()):
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
            # One unreadable file must never kill the batch: warn and move on.
            # TODO (Day 4/5): once build_digest() exists, turn extraction
            # failures into "needs human review" records instead of skipping.
            logger.warning("Skipping %s: %s", filepath.name, e)
            continue
        results.append(triage_document(client, prompt_template, filepath.name, text))

    # Day 1-2 output: print the raw JSON so we can verify the core works.
    # Day 4 replaces this with build_digest() written to args.output.
    print(json.dumps(results, indent=2, ensure_ascii=False))
    logger.info("Processed %d document(s). Digest (Day 4) not built yet.", len(results))


if __name__ == "__main__":
    main()
