"""Defence against instructions hidden in documents (prompt injection).

Documents come from the applicant, so their text is untrusted. Three layers:

1. Strip: before a text document reaches the model, lines that address an AI reader
   or give it instructions are removed (and recorded). Deterministic, no model involved.
2. Tell: the extraction prompt says document content is data, never instructions, and asks
   the model to report any instruction it sees in `notes` (this also covers scanned pages,
   where there is no text to strip).
3. Contain: even if a model obeyed, each document is read in its own call, the arithmetic is
   Python's, the statement must reconcile, and documents are cross-checked; the planted
   value is still visible to the analyst as a flagged finding.

The patterns are deliberately about the FORM of an instruction to a machine ("ignore your
instructions", "AI reviewer", "record X as Y"), not about any business value, so normal
remarks like "payment received late" are kept.
"""

from __future__ import annotations

import re

_PATTERNS = [
    r"\bignore\b.{0,40}\b(instruction|column|status|above|previous|rules?)\b",
    r"\b(ai|automated|machine)\s+(review|reviewer|reader|system)\b",
    r"\b(assistant|chatgpt|claude|llm|language model)\b",
    r"\bsystem (instruction|prompt|message)\b",
    r"\b(record|set|mark|report)\b.{0,50}\b(as|to)\b.{0,20}\b(true|approved|regular|integrated|offered)\b",
    r"تجاهل.{0,30}(التعليمات|تعليماتك|عمود|الحالة|القواعد)",
    r"(المراجع|المراجعة|المساعد|النظام)\s*(الآلي|الآلية|الذكي)?\s*[:،]",
    r"تعليمات النظام",
    r"سجّ?ل.{0,40}(على أنه|كـ|أن).{0,20}(معتمد|منتظم|مرتبط|مقدمة)",
]
_RX = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def suspicious_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if _RX.search(ln)]


def strip_instructions(text: str) -> tuple[str, list[str]]:
    """The text without lines that instruct an AI reader, and the removed lines."""
    kept, removed = [], []
    for ln in text.splitlines():
        (removed if _RX.search(ln) else kept).append(ln)
    return "\n".join(kept), [r.strip() for r in removed]
