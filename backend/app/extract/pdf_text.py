"""Read the text of a business's PDF documents. Deterministic: no language model.

Two things matter for what comes next (the model reading the text):

1. Columns survive. In a bank statement, an amount under "Debit" and the same
   amount under "Credit" mean opposite things, so each piece of text is placed
   at a column proportional to its position on the page (like `pdftotext -layout`).
2. Arabic reads in logical order. PDFs store Arabic glyphs left to right in
   visual order; we reverse each Arabic run glyph by glyph. A lam-alef ligature
   is one glyph holding two letters, so it stays intact (character-level
   reversal would turn "الأغذية" into "األغذية"). Short vowel marks are dropped.

Usage: python -m app.extract.pdf_text <documents_folder> [doc_name]
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

# The six documents every application needs, and the one that exists only if
# the business keeps financial statements (its absence is a fact, not a gap).
REQUIRED_DOCS = (
    "bank_statement",
    "cr_certificate",
    "credit_report",
    "financing_application",
    "receivables_aging",
    "tax_compliance",
)
OPTIONAL_DOCS = ("income_statement",)

POINTS_PER_COLUMN = 3.5  # A4 width (595 pt) -> about 170 text columns; narrow enough for shrunk table text
LINE_TOLERANCE = 3.0     # glyphs whose tops differ by less than this share a line
SEGMENT_GAP = 3.0        # a horizontal gap wider than this starts a new segment

_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_AMOUNT = re.compile(r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?%?")
_LATIN_OR_DIGIT = re.compile(r"[A-Za-z0-9]")
# Short vowel marks (harakat) sit on top of a letter at the same x, so sorting by
# position scrambles them; they carry no information a lender needs, so drop them.
_HARAKAT = re.compile(r"[\u064B-\u0652\u0670]")
_UNMAPPED = re.compile(r"\(cid:\d+\)")  # glyphs the PDF font has no text for


def _is_arabic(text: str) -> bool:
    return bool(_ARABIC.search(text))


def _rtl_runs(glyphs: list[str]) -> list[str]:
    """Reverse each run of Arabic glyphs (with the spaces, hyphens and brackets
    between them) and leave Latin text and numbers in reading order."""
    out: list[str] = []
    i = 0
    while i < len(glyphs):
        if not _is_arabic(glyphs[i]):
            out.append(glyphs[i])
            i += 1
            continue
        j = i
        # extend the run over Arabic glyphs and the neutral marks inside it
        while j + 1 < len(glyphs) and (
            _is_arabic(glyphs[j + 1])
            or (glyphs[j + 1] in " -()" and any(_is_arabic(g) for g in glyphs[j + 2 : j + 4]))
        ):
            j += 1
        # brackets just outside the run belong to it, e.g. ")ةاكاحم("
        if i > 0 and glyphs[i - 1] in "()" and out and out[-1] == glyphs[i - 1]:
            out.pop()
            i -= 1
        if j + 1 < len(glyphs) and glyphs[j + 1] in "()":
            j += 1
        # brackets are already stored mirrored by the PDF writer, so no swap
        out.extend(glyphs[i : j + 1][::-1])
        i = j + 1
    return out


def _segment_text(chars: list[dict]) -> str:
    glyphs = [g for c in chars if (g := _HARAKAT.sub("", _UNMAPPED.sub("", c["text"])))]
    first_strong = next(
        (g for g in glyphs if _is_arabic(g) or _LATIN_OR_DIGIT.search(g)), ""
    )
    if _is_arabic(first_strong) and not any(_LATIN_OR_DIGIT.search(g) for g in glyphs):
        # a purely Arabic cell: the whole cell reads right to left
        return "".join(glyphs[::-1]).strip()
    return "".join(_rtl_runs(glyphs)).strip()


def _page_lines(page) -> list[str]:
    # vowel marks sit on top of a letter and would break gap measurement; drop them first
    chars = sorted((c for c in page.chars if not _HARAKAT.fullmatch(c["text"])),
                   key=lambda c: (c["top"], c["x0"]))
    rows: list[list[dict]] = []
    for c in chars:
        if rows and abs(rows[-1][0]["top"] - c["top"]) < LINE_TOLERANCE:
            rows[-1].append(c)
        else:
            rows.append([c])

    lines = []
    for row in rows:
        row.sort(key=lambda c: c["x0"])
        segments: list[list[dict]] = [[row[0]]]
        for prev, cur in zip(row, row[1:]):
            if cur["x0"] - prev["x1"] > SEGMENT_GAP:
                segments.append([cur])
            else:
                segments[-1].append(cur)

        line = ""
        for seg in segments:
            text = _segment_text(seg)
            if not text:
                continue
            if _AMOUNT.fullmatch(text):
                # amounts are right-aligned in their cells: anchor on the right edge,
                # which stays put however long the text to their left is
                col = round(seg[-1]["x1"] / POINTS_PER_COLUMN) - len(text)
            else:
                col = round(seg[0]["x0"] / POINTS_PER_COLUMN)
            pad = max(col - len(line), 2 if line else 0)
            line += " " * pad + text
        if line.strip():
            lines.append(line.rstrip())
    return lines


def read_pdf(path: Path) -> str:
    """All pages of one PDF as layout-preserving text."""
    with pdfplumber.open(path) as pdf:
        pages = ["\n".join(_page_lines(p)) for p in pdf.pages]
    return "\n\n".join(f"--- page {i} ---\n{t}" for i, t in enumerate(pages, 1))


@dataclass
class DocumentSet:
    """The text of every document found in one business's folder."""

    texts: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)  # required documents not found
    scanned: dict[str, Path] = field(default_factory=dict)  # image-only PDFs: need a vision read

    def has(self, name: str) -> bool:
        return name in self.texts or name in self.scanned


def has_text_layer(path: Path) -> bool:
    with pdfplumber.open(path) as pdf:
        return any(p.chars for p in pdf.pages)


def load_documents(folder: Path) -> DocumentSet:
    docs = DocumentSet()
    for name in REQUIRED_DOCS + OPTIONAL_DOCS:
        path = folder / f"{name}.pdf"
        if path.exists() and not has_text_layer(path):
            docs.scanned[name] = path
        elif path.exists():
            docs.texts[name] = read_pdf(path)
        elif name in REQUIRED_DOCS:
            docs.missing.append(name)
    return docs


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    folder = Path(sys.argv[1])
    docs = load_documents(folder)
    names = [n for n in ([sys.argv[2]] if len(sys.argv) > 2 else docs.texts) if n in docs.texts]
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    for n in names:
        print(f"===== {n} =====\n{docs.texts[n]}\n")
    if docs.scanned:
        print("Scanned (image only, needs a vision read):", ", ".join(docs.scanned))
    if docs.missing:
        print("Missing required documents:", ", ".join(docs.missing))


if __name__ == "__main__":
    main()
