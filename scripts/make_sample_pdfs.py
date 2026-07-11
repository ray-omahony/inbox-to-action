"""Generate the PDF test fixtures in samples/.

Creates two files:
  samples/statement_of_work.pdf  — a valid one-page PDF (fictional ACME
                                   statement of work with a signing deadline)
  samples/corrupt.pdf            — deliberately broken, so we can test that
                                   the triage loop skips it gracefully

Re-runnable and committed so the fixtures are reproducible and provably
contain no personal data. Uses only the stdlib to BUILD the PDF (so you can
see exactly what bytes go in) and pypdf only to VERIFY it reads back.

Run: .venv/bin/python scripts/make_sample_pdfs.py
"""

from pathlib import Path

from pypdf import PdfReader

# Resolve relative to this file, not the cwd — same trick as src/triage.py.
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

# Fictional business text. One line carries the date the triage model
# should surface in key_dates, and one line is an explicit action item.
LINES = [
    "STATEMENT OF WORK - SOW-2026-014",
    "Client: ACME Corp - fictional sample document for testing",
    "Provider: Initech Consulting Ltd.",
    "",
    "Scope: Migrate the ACME quarterly reporting pipeline to the new",
    "data warehouse, rebuild the four executive dashboards, and run",
    "two training sessions for the finance team.",
    "",
    "Fees: fixed price of 24,000 USD, invoiced across two milestones.",
    "Start date: 2026-08-03. Final delivery: 2026-10-30.",
    "",
    "ACTION REQUIRED: legal must review the liability cap in section 7,",
    "then countersign by 2026-07-25 to hold the project start date.",
]


def _pdf_escape(text: str) -> str:
    """Escape the three characters that are special inside a PDF string."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_valid_pdf() -> bytes:
    """Assemble a minimal one-page PDF by hand.

    A PDF is just numbered objects plus an xref table of their byte
    offsets. Five objects are enough for one page of text: Catalog ->
    Pages -> Page, a Helvetica font, and a content stream that draws
    each line with the Tj operator.
    """
    content_lines = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
    for line in LINES:
        # Tj draws the string; T* moves down one line (14 points, set by TL).
        content_lines.append(f"({_pdf_escape(line)}) Tj T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))  # xref needs the byte offset of each object
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"

    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    # Entry 0 is the required "free objects" placeholder; each entry is
    # exactly 20 bytes, hence the zero-padding and trailing space.
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, xref_pos)
    )
    return bytes(out)


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)  # survive a checkout without samples/
    valid_path = SAMPLES_DIR / "statement_of_work.pdf"
    valid_path.write_bytes(build_valid_pdf())

    # Round-trip check: if pypdf can't read back the text we just wrote,
    # the fixture is useless — fail here, not mid-triage-run.
    extracted = PdfReader(valid_path).pages[0].extract_text()
    if "countersign by 2026-07-25" not in extracted:
        raise SystemExit(f"round-trip check failed; extracted:\n{extracted}")

    corrupt_path = SAMPLES_DIR / "corrupt.pdf"
    # Valid header, garbage body: PdfReader raises PdfStreamError on this.
    corrupt_path.write_bytes(b"%PDF-1.7\nthis is not really a pdf body\n")

    print(f"Wrote {valid_path} ({valid_path.stat().st_size} bytes) — round-trip OK")
    print(f"Wrote {corrupt_path} ({corrupt_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
