"""Calling the model: one forced tool call per document, cached on disk, every call logged.

- `AnthropicReader` calls the Anthropic API (needs ANTHROPIC_API_KEY, e.g. in backend/.env).
- `CachedReader` wraps any reader. The key is a hash of (model, prompt version, system prompt,
  instruction, document content, schema), so re-running costs nothing and gives the same
  answer; changing a prompt or a document gives a new key. Cache files are plain JSON
  and can be committed, so anyone can reproduce the evaluation without an API key.
- Every call (or cache hit) is recorded in a `CallLog` with tokens and latency.

Scanned documents have no text, so they are sent as page images instead.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .schemas import PROMPT_VERSION, SYSTEM, TOOLS, instructions

BACKEND_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = BACKEND_DIR / "cache" / "llm"
EXTRACT_MODEL = os.environ.get("NEXTYES_EXTRACT_MODEL", "claude-haiku-5-5")
MAX_TOKENS = 32_000  # a 12-month statement is ~150 lines, ~8k output tokens


@dataclass
class DocInput:
    """What the model sees for one document: text, or page images for a scan."""

    name: str
    text: str | None = None
    pdf_path: Path | None = None  # set for scanned documents

    def content(self) -> list[dict[str, Any]]:
        if self.text is not None:
            return [{"type": "text", "text": f"<document>\n{self.text}\n</document>"}]
        return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}
                for b64 in page_images(self.pdf_path)]

    def fingerprint(self) -> str:
        if self.text is not None:
            return hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        return hashlib.sha256(self.pdf_path.read_bytes()).hexdigest()


def page_images(pdf_path: Path, dpi: int = 150) -> list[str]:
    """Each page of a PDF as a base64 PNG."""
    import io

    import pypdfium2 as pdfium

    out = []
    for page in pdfium.PdfDocument(str(pdf_path)):
        buf = io.BytesIO()
        page.render(scale=dpi / 72).to_pil().convert("L").save(buf, "PNG", optimize=True)
        out.append(base64.b64encode(buf.getvalue()).decode())
    return out


@dataclass
class CallRecord:
    document: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    cached: bool


@dataclass
class CallLog:
    calls: list[CallRecord] = field(default_factory=list)

    def summary(self) -> dict[str, float]:
        live = [c for c in self.calls if not c.cached]
        return {
            "calls": len(self.calls),
            "cache_hits": len(self.calls) - len(live),
            "input_tokens": sum(c.input_tokens for c in self.calls),
            "output_tokens": sum(c.output_tokens for c in self.calls),
            "live_latency_s": round(sum(c.latency_s for c in live), 1),
        }


@dataclass
class Reading:
    """The model's answer for one document."""

    fields: dict[str, Any]
    record: CallRecord


class Reader(Protocol):
    model: str

    def read(self, doc: DocInput, context: dict[str, str | None]) -> Reading: ...


class ReadError(RuntimeError):
    pass


class AnthropicReader:
    def __init__(self, model: str = EXTRACT_MODEL, api_key: str | None = None):
        import anthropic  # imported here so tests and the fake reader don't need the package

        _load_dotenv()
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def read(self, doc: DocInput, context: dict[str, str | None]) -> Reading:
        tool = TOOLS[doc.name]
        from ..tool_call import call_tool

        start = time.perf_counter()
        # Streamed: a 150-line statement is a long answer, and the SDK refuses long
        # non-streaming requests. No temperature (current models and SDK do not take it);
        # repeatability comes from the disk cache. call_tool also copes with models that
        # do not accept a forced tool call.
        fields, resp = call_tool(
            self.client, model=self.model, tool=tool, stream=True, max_tokens=MAX_TOKENS, system=SYSTEM,
            messages=[{"role": "user", "content": [
                *doc.content(), {"type": "text", "text": instructions(doc.name, context)}]}],
        )
        latency = time.perf_counter() - start
        if resp.stop_reason == "max_tokens":
            raise ReadError(f"{doc.name}: answer cut off at {MAX_TOKENS} tokens")
        if fields is None:
            raise ReadError(f"{doc.name}: model did not call the tool")
        return Reading(fields, CallRecord(doc.name, self.model, resp.usage.input_tokens,
                                          resp.usage.output_tokens, round(latency, 2), False))


class CachedReader:
    def __init__(self, inner: Reader, cache_dir: Path = CACHE_DIR):
        self.inner, self.cache_dir, self.model = inner, cache_dir, inner.model

    def key(self, doc: DocInput, context: dict[str, str | None]) -> str:
        parts = [self.model, PROMPT_VERSION, SYSTEM, instructions(doc.name, context),
                 json.dumps(TOOLS[doc.name], sort_keys=True), doc.fingerprint()]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]

    def read(self, doc: DocInput, context: dict[str, str | None]) -> Reading:
        path = self.cache_dir / f"{self.key(doc, context)}.json"
        if path.exists():
            hit = json.loads(path.read_text(encoding="utf-8"))
            rec = CallRecord(**{**hit["record"], "cached": True})
            return Reading(hit["fields"], rec)
        reading = self.inner.read(doc, context)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"document": doc.name, "fields": reading.fields,
                                    "record": reading.record.__dict__}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        return reading


def _load_dotenv() -> None:
    """Read backend/.env (KEY=value lines) without overriding real environment variables."""
    env = BACKEND_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
