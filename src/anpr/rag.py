"""A small, dependency-free BM25 retrieval index for the assistant.

The corpus is deliberately tiny (six Markdown documents), so a full vector
database would add installation friction without improving the capstone.  The
same interface can later be backed by FAISS or ChromaDB.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "been", "it", "its", "this", "that", "these", "those",
    "with", "as", "at", "by", "from", "can", "could", "should", "would", "do",
    "does", "did", "not", "no", "what", "why", "how", "which", "who", "when",
    "where", "me", "my", "we", "our", "you", "your", "i", "if", "then", "than",
    "there", "their", "about", "into", "over", "under", "also", "may", "might",
}


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall((text or "").lower()) if token not in STOPWORDS and len(token) > 1]


@dataclass(frozen=True)
class Chunk:
    doc: str
    title: str
    section: str
    text: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class Citation:
    doc: str
    title: str
    section: str
    snippet: str
    score: float

    def as_dict(self) -> dict:
        return {
            "doc": self.doc,
            "title": self.title,
            "section": self.section,
            "snippet": self.snippet,
            "score": round(self.score, 3),
        }


class KnowledgeBase:
    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory else Path(__file__).parent / "knowledge"
        self.chunks: list[Chunk] = []
        self._df: dict[str, int] = {}
        self._avgdl = 1.0
        self._loaded = False

    def load(self) -> "KnowledgeBase":
        if self._loaded:
            return self
        chunks: list[Chunk] = []
        if self.directory.exists():
            for path in sorted(self.directory.glob("*.md")):
                raw = path.read_text(encoding="utf-8")
                doc_title = path.stem.replace("_", " ").title()
                section = "Overview"
                lines: list[str] = []
                for line in raw.splitlines():
                    if line.startswith("# "):
                        doc_title = line[2:].strip()
                        continue
                    if line.startswith("## "):
                        self._flush(chunks, path.name, doc_title, section, lines)
                        section = line[3:].strip()
                        lines = []
                        continue
                    lines.append(line)
                self._flush(chunks, path.name, doc_title, section, lines)
        self.chunks = chunks
        df: dict[str, int] = {}
        for chunk in chunks:
            for token in set(chunk.tokens):
                df[token] = df.get(token, 0) + 1
        self._df = df
        self._avgdl = sum(len(chunk.tokens) for chunk in chunks) / max(len(chunks), 1)
        self._loaded = True
        return self

    @staticmethod
    def _flush(chunks: list[Chunk], doc: str, title: str, section: str, lines: Iterable[str]) -> None:
        text = "\n".join(lines).strip()
        if len(text) < 40:
            return
        chunks.append(
            Chunk(
                doc=doc,
                title=title,
                section=section,
                text=text,
                tokens=tuple(tokenize(text)),
            )
        )

    def _idf(self, token: str) -> float:
        n = len(self.chunks)
        df = self._df.get(token, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 3, min_score: float = 0.0) -> list[Citation]:
        self.load()
        tokens = tokenize(query)
        if not tokens or not self.chunks:
            return []
        k1, b = 1.6, 0.75
        scored: list[tuple[float, Chunk]] = []
        for chunk in self.chunks:
            length = len(chunk.tokens)
            counts: dict[str, int] = {}
            for token in chunk.tokens:
                counts[token] = counts.get(token, 0) + 1
            score = 0.0
            for token in tokens:
                tf = counts.get(token, 0)
                if not tf:
                    continue
                idf = self._idf(token)
                denom = tf + k1 * (1 - b + b * length / max(self._avgdl, 1))
                score += idf * (tf * (k1 + 1)) / denom
            if score > min_score:
                scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[Citation] = []
        for score, chunk in scored[:k]:
            snippet = re.sub(r"\s+", " ", chunk.text).strip()
            if len(snippet) > 320:
                head = snippet[:320]
                boundary = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
                snippet = head[: boundary + 1] if boundary > 180 else head.rsplit(" ", 1)[0] + "…"
            results.append(
                Citation(
                    doc=chunk.doc,
                    title=chunk.title,
                    section=chunk.section,
                    snippet=snippet,
                    score=score,
                )
            )
        return results

    def section_text(self, doc: str, section: str) -> str:
        """Full text of one indexed section, for prompts that need more than a snippet."""
        self.load()
        for chunk in self.chunks:
            if chunk.doc == doc and chunk.section == section:
                return chunk.text
        return ""

    def context(self, query: str, k: int = 3) -> tuple[str, list[dict]]:
        citations = self.search(query, k=k)
        if not citations:
            return "", []
        blocks = [
            f"[{index}] {item.title} — {item.section}\n{item.snippet}"
            for index, item in enumerate(citations, start=1)
        ]
        return "\n\n".join(blocks), [item.as_dict() for item in citations]
