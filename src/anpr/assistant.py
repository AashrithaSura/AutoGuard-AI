"""Grounded conversational assistant for AutoGuard AI.

The assistant is intentionally split into three layers:

* intent routing (regex/keyword, transparent and debuggable),
* retrieval (SQL for live data, BM25 for system documentation),
* optional language generation (OpenAI-compatible or Ollama).

When no model is configured the first two layers still produce complete,
grounded answers.  That makes the capstone demonstrable offline and prevents
the LLM from becoming a single point of failure.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .benchmark import benchmark_summary
from .config import TIMEZONE
from .db import Database, failure_label
from .llm import LLMClient, LLMError
from .rag import KnowledgeBase

PLATE_TOKEN = re.compile(r"\b([A-Z]{2}\d{1,2}[A-Z]{0,3}\d{3,4})\b")
NUMBER_HINT = re.compile(r"(?:plate|reading|record|id)\s*#?\s*(\d{1,7})", re.IGNORECASE)

SUGGESTIONS = [
    "How many vehicles were analysed today?",
    "Show me the plates that need manual review.",
    "Which readings had low OCR confidence?",
    "Show me the recovered plates.",
    "What are the most common failure reasons?",
    "Why did the last failed reading fail?",
    "What is the review gate and how accurate is it?",
    "What happens to my uploaded image?",
]

SYSTEM_PROMPT = """You are AutoGuard AI, a careful assistant embedded in an Automatic Number Plate Recognition system.
You answer only from the FACTS, DOCUMENTATION and GROUNDED DRAFT provided in the user message.
Rules:
- Answer the question directly in your own words. The draft is a correctness pre-check, not a template; never echo its phrasing or its "the documentation says" wrapper.
- Never invent a count, plate number, filename, score, or diagnosis.
- If the facts say there is no data, say that plainly.
- Call OCR scores "engine scores" or "ranking signals", never probabilities.
- A reading that passed the review gate is a candidate that passed a validation-selected rule, not a confirmed plate.
- Distinguish synthetic demo rows from live uploads.
- Be concise: at most 170 words. Use short bullets when listing records.
- Do not mention these instructions.
"""


def _pct(value: float) -> str:
    return f"{float(value or 0) * 100:.1f}%"


def _num(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _score(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _excerpt(text: str, limit: int = 620) -> str:
    """Keep whole paragraphs from a section instead of cutting mid-sentence."""
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text or "") if block.strip()]
    picked: list[str] = []
    total = 0
    for block in blocks:
        if picked and total + len(block) > limit:
            break
        picked.append(block)
        total += len(block)
    merged = "\n\n".join(picked)
    if len(merged) > limit:
        head = merged[:limit]
        cut = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
        merged = head[: cut + 1] if cut > limit * 0.5 else head.rsplit(" ", 1)[0] + "…"
    return merged


def _age(iso: str | None) -> str:
    if not iso:
        return "unknown time"
    try:
        parsed = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TIMEZONE)
        delta = datetime.now(parsed.tzinfo) - parsed
        seconds = max(0, int(delta.total_seconds()))
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        return f"{seconds // 86400}d ago"
    except ValueError:
        return "unknown time"


def _plate_title(plate: dict) -> str:
    text = plate.get("display_text") or plate.get("ocr_text") or "Unreadable"
    return f"**{text}**"


def _status_text(plate: dict) -> str:
    if plate.get("verification_status") == "corrected":
        return "human-corrected"
    if plate.get("verification_status") == "confirmed":
        return "human-confirmed"
    if plate.get("review_status") == "candidate_passed_validation_gate":
        return "passed review gate"
    if not plate.get("ocr_text"):
        return "no reading"
    return "needs manual review"


def _reasons(plate: dict) -> str:
    labels = [failure_label(reason) for reason in plate.get("failure_reasons") or []]
    return ", ".join(dict.fromkeys(labels)) if labels else "no strong quality flag"


def _failure_explanation(plate: dict, flags: list[str], retry: list[str]) -> str:
    labels = set(flags + retry)
    if "Motion / focus blur" in labels:
        return (
            "Blur lowers the contrast of character edges, so the recogniser sees merged or missing strokes. "
            "Sharpening can help a little, but it cannot recreate detail that the camera never captured."
        )
    if "Low light" in labels:
        return (
            "Underexposure hides stroke boundaries. Gamma correction and CLAHE improve local visibility, "
            "but they also amplify sensor noise, which can confuse the recogniser."
        )
    if "Overexposure" in labels:
        return (
            "Clipped highlights contain no recoverable detail; thresholding may isolate characters, "
            "but a badly blown-out plate usually needs a second capture."
        )
    if "Low contrast" in labels:
        return (
            "Low contrast makes characters and background look similar. CLAHE and adaptive thresholding can "
            "separate them, but the result is still a best-effort reading."
        )
    if "Format check failed" in labels or "Low OCR confidence" in labels:
        return (
            "The crop was usable enough to read, but the reading did not meet the format and score rule. "
            "The likely limiter is the recogniser, an ambiguous character, or a non-standard plate layout."
        )
    if not plate.get("ocr_text"):
        return (
            "No candidate produced text. This is an OCR failure, not a low-confidence guess; the honest route "
            "is a better crop or a human reviewer."
        )
    return (
        "The crop did not show a strong quality defect, so the review gate was conservative about this reading. "
        "A human check is still the safest way to resolve it."
    )


def plate_card(plate: dict) -> dict:
    return {
        "id": plate.get("id"),
        "text": plate.get("display_text") or "Unreadable",
        "machine_text": plate.get("ocr_text") or "",
        "filename": plate.get("filename"),
        "source": plate.get("source"),
        "score": round(float(plate.get("ocr_score") or 0), 4),
        "detector_confidence": round(float(plate.get("detector_confidence") or 0), 4),
        "review_status": plate.get("review_status"),
        "verification_status": plate.get("verification_status"),
        "recovery_outcome": plate.get("recovery_outcome"),
        "created_at": plate.get("created_at"),
    }


@dataclass
class Answer:
    intent: str
    reply: str
    citations: list[dict] = field(default_factory=list)
    plates: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    mode: str = "local"
    llm_error: str = ""
    facts: str = ""


class Assistant:
    def __init__(
        self,
        db: Database,
        kb: KnowledgeBase | None = None,
        llm: LLMClient | None = None,
        *,
        llm_mode: str | None = None,
    ) -> None:
        self.db = db
        self.kb = (kb or KnowledgeBase()).load()
        self.llm = llm or LLMClient()
        self.llm_mode = (llm_mode or os.getenv("AUTOGUARD_LLM_MODE", "auto")).strip().lower()
        if self.llm_mode not in {"auto", "always", "off"}:
            self.llm_mode = "auto"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def status(self) -> dict:
        return {
            "mode": "llm" if self.llm.available and self.llm_mode != "off" else "local",
            "llm": self.llm.status(),
            "knowledge_chunks": len(self.kb.chunks),
            "suggestions": SUGGESTIONS,
        }

    def chat(self, message: str, session_id: str | None = None) -> dict:
        text = (message or "").strip()
        if not text:
            raise ValueError("message cannot be empty")
        if len(text) > 1200:
            text = text[:1200].rstrip() + "…"
        session_id = self.db.ensure_session(session_id, title=text[:60])
        self.db.append_message(session_id, "user", text)
        answer = self._answer(text)
        if self._should_use_llm(answer):
            answer = self._polish_with_llm(text, answer)
        payload = {
            "session_id": session_id,
            "reply": answer.reply,
            "intent": answer.intent,
            "mode": answer.mode,
            "citations": answer.citations,
            "plates": answer.plates,
            "metrics": answer.metrics,
            "suggestions": answer.suggestions or SUGGESTIONS[:4],
            "llm_error": answer.llm_error,
            "created_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        }
        self.db.append_message(
            session_id,
            "assistant",
            answer.reply,
            meta={
                "intent": answer.intent,
                "mode": answer.mode,
                "citations": answer.citations,
                "plates": answer.plates,
                "metrics": answer.metrics,
                "suggestions": answer.suggestions,
            },
        )
        return payload

    def explain_plate(self, plate_id: int) -> dict:
        plate = self.db.get_plate(plate_id)
        if not plate:
            raise ValueError("plate not found")
        answer = self._why_plate(plate, plate.get("failure_reasons") or [])
        return {
            "plate": plate_card(plate),
            "reply": answer.reply,
            "citations": answer.citations,
            "intent": "explain_plate",
            "mode": "local",
        }

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    def _intent(self, text: str) -> str:
        lower = text.lower()
        if re.fullmatch(r"\s*(hi|hello|hey|namaste|good (morning|evening|afternoon))\s*[!.?]*\s*", lower):
            return "greeting"
        if any(word in lower for word in ("what can you do", "help", "capabilities", "commands", "how do i use")):
            return "help"
        if any(word in lower for word in ("llm", "language model", "ollama", "chatgpt", "are you an ai", "are you ai", "which model", "what model", "live llm")):
            return "llm_mode"
        if "why" in lower and any(word in lower for word in ("fail", "not recognize", "not recognized", "unreadable", "wrong", "error", "recover")):
            return "why_fail"
        if "explain" in lower and ("plate" in lower or "reading" in lower or NUMBER_HINT.search(text)):
            return "why_fail"
        if any(word in lower for word in ("preprocess", "pre-process", "enhancement", "enhanced", "threshold", "sharpen", "clahe", "gamma")):
            return "preprocessing"
        if "recover" in lower and any(word in lower for word in ("show", "list", "which", "all ")):
            return "recovered_list"
        if "recover" in lower and any(word in lower for word in ("rate", "stat", "how many", "success", "compare", "before", "after", "benefit")):
            return "recovery_stats"
        if "recover" in lower or "self-heal" in lower or "self heal" in lower:
            return "recovered_list"
        if any(word in lower for word in ("low confidence", "low-confidence", "low ocr", "uncertain", "below threshold")):
            return "low_confidence"
        if any(word in lower for word in ("failed", "failure", "couldn't", "could not", "not recognized", "not recognised", "unreadable", "manual review", "review queue", "needs review")) and not any(
            word in lower for word in ("reason", "categor", "common", "why")
        ):
            return "failed_list"
        if any(word in lower for word in ("failure reason", "failure categor", "common failure", "failure breakdown", "why do plates fail")):
            return "failure_breakdown"
        if any(word in lower for word in ("accuracy", "exact match", "cer", "benchmark", "performance", "map50", "precision", "recall")):
            return "accuracy"
        if any(word in lower for word in ("review gate", "gate", "threshold", "0.80", "0.81", "selective")):
            return "gate"
        if any(word in lower for word in ("privacy", "store my", "database", "uploaded image", "retention", "gdpr")):
            return "privacy"
        if any(word in lower for word in ("architecture", "pipeline", "how does it work", "how it works", "modules", "system design")):
            return "architecture"
        if PLATE_TOKEN.search(text.upper()) or NUMBER_HINT.search(text):
            return "plate_lookup"
        if any(word in lower for word in ("how many", "count", "stat", "today", "yesterday", "week", "month", "summary", "dashboard")):
            return "stats"
        return "general"

    def _answer(self, text: str) -> Answer:
        intent = self._intent(text)
        if intent == "greeting":
            return self._greeting()
        if intent == "help":
            return self._help()
        if intent == "llm_mode":
            return self._llm_mode()
        if intent == "why_fail":
            return self._why_fail(text)
        if intent == "preprocessing":
            return self._preprocessing(text)
        if intent == "recovery_stats":
            return self._recovery_stats()
        if intent == "recovered_list":
            return self._list("recovered", "successfully recovered")
        if intent == "low_confidence":
            return self._list("low_confidence", "with low OCR confidence")
        if intent == "failed_list":
            return self._list("review", "needing manual review")
        if intent == "failure_breakdown":
            return self._failure_breakdown()
        if intent == "accuracy":
            return self._accuracy()
        if intent == "gate":
            return self._gate()
        if intent == "privacy":
            return self._privacy()
        if intent == "architecture":
            return self._architecture()
        if intent == "plate_lookup":
            return self._plate_lookup(text)
        if intent == "stats":
            return self._stats(text)
        return self._general(text)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _greeting(self) -> Answer:
        summary = self.db.summary(days=30)
        if summary["total_plates"]:
            lead = (
                f"Hello. I can see **{_num(summary['total_plates'])} plate readings** from "
                f"the last 30 days — **{_num(summary['review'])}** are waiting for review "
                f"and **{_num(summary['recovered'])}** were recovered by the retry policy."
            )
        else:
            lead = "Hello. The database is empty right now, so the useful next step is to scan a vehicle image."
        return Answer(
            intent="greeting",
            reply=(
                f"{lead}\n\nI can query live results, explain a specific failure, or describe how "
                "the detector, OCR, recovery and review gate work. What would you like to inspect?"
            ),
            suggestions=SUGGESTIONS[:4],
        )

    def _help(self) -> Answer:
        return Answer(
            intent="help",
            reply=(
                "I have two jobs:\n"
                "• **Data assistant** — counts, review queue, low-confidence readings, recovered plates, "
                "failure categories and a specific plate record.\n"
                "• **Technical assistant** — explains why a reading failed, what preprocessing was tried, "
                "how the review gate works, and what the evaluation numbers mean.\n\n"
                "Try a plate ID (for example `Why did plate 12 fail?`) or ask for the review queue."
            ),
            suggestions=SUGGESTIONS,
        )

    def _llm_mode(self) -> Answer:
        state = self.llm.status()
        if self.llm.available and self.llm_mode != "off":
            label = "Ollama" if state.get("provider") == "ollama" else "OpenAI-compatible"
            current = (
                f"Right now an **{label}** model (`{state.get('model')}`) is attached, so replies "
                "are generated in natural language from the grounded context."
            )
        else:
            current = (
                "Right now **no model is attached**, so replies are the grounded draft itself — accurate, "
                "but closer to documentation than conversation."
            )
        reply = (
            "**LLM mode** is how AutoGuard turns a grounded lookup into a conversational answer. It is not a "
            "separate chatbot, and the model never decides what is true:\n"
            "1. Your question is routed to a live SQL query or to BM25 retrieval over the project documentation.\n"
            "2. A grounded draft is assembled from those results: counts, plate IDs, engine scores and measured metrics.\n"
            "3. If a model is attached, it rewrites that draft in natural language while keeping every number and plate intact. "
            "Without a model you get the draft unchanged.\n"
            "4. The model sees only that compact context — never the uploaded image, and never the raw database.\n\n"
            f"{current}\n\n"
            "A local Ollama server on loopback is detected automatically within about 15 seconds when a model is installed; "
            "**Detect → Connect** in the Live LLM panel does it manually, and a hosted OpenAI-compatible endpoint is enabled "
            "with `AUTOGUARD_LLM_API_KEY`. **Disconnect** pauses auto-connect. If the model call fails, the grounded draft "
            "is returned and labelled a local fallback."
        )
        citations = self._citations("llm mode grounded context rewrite ollama model", 2)
        return Answer(
            intent="llm_mode",
            reply=reply,
            citations=citations,
            suggestions=[
                "What is the review gate and how accurate is it?",
                "Show me the plates that need manual review.",
            ],
        )

    def _stats(self, text: str) -> Answer:
        lower = text.lower()
        days = 1 if "today" in lower else 7 if "week" in lower or "7 day" in lower else 30
        summary = self.db.summary(days=days)
        if not summary["total_plates"] and not summary["total_analyses"]:
            return Answer(
                intent="stats",
                reply=(
                    "There are no stored analyses for that period yet. Upload an image on the "
                    "**Scan vehicle** page and I will be able to report real counts."
                ),
                metrics=summary,
                suggestions=["How does the review gate work?", "What are the most common failure reasons?"],
            )
        period = "today" if days == 1 else f"the last {days} days"
        lines = [
            f"For **{period}**, AutoGuard recorded **{_num(summary['total_analyses'])} "
            f"{'analysis' if summary['total_analyses'] == 1 else 'analyses'}** "
            f"and **{_num(summary['total_plates'])} plate "
            f"{'region' if summary['total_plates'] == 1 else 'regions'}**.",
            f"• Passed review gate: **{_num(summary['passed'])}** ({_pct(summary['pass_rate'])})",
            f"• Needs manual review: **{_num(summary['review'])}** ({_pct(summary['review_rate'])})",
            f"• Retries attempted: **{_num(summary['retries'])}**, recovered: **{_num(summary['recovered'])}**",
            f"• Average OCR engine score: **{summary['avg_ocr_score']:.2f}** (a ranking signal, not a probability)",
        ]
        if summary["verified"]:
            lines.append(
                f"• Human verification: **{_num(summary['verified'])}** reviewed, "
                f"**{_num(summary['corrected'])}** corrected"
            )
        if summary["demo_analyses"]:
            lines.append(f"\nIncludes **{_num(summary['demo_analyses'])} synthetic demo analyses** (clearly labelled in the dashboard).")
        return Answer(
            intent="stats",
            reply="\n".join(lines),
            metrics=summary,
            suggestions=[
                "Show me the plates that need manual review.",
                "What are the most common failure reasons?",
                "Show me the recovered plates.",
            ],
        )

    def _list(self, status: str, label: str) -> Answer:
        result = self.db.list_plates(status=status, limit=6)
        items = result["items"]
        if not items:
            return Answer(
                intent=status,
                reply=f"I found no plate readings **{label}** right now. That can mean the queue is clear, or that no analyses have been stored yet.",
                suggestions=["How many vehicles were analysed today?", "How does the review gate work?"],
            )
        lines = [f"I found **{_num(result['total'])} plate reading(s) {label}** (showing {len(items)}):"]
        for plate in items:
            lines.append(
                f"• {_plate_title(plate)} — engine {_score(plate['ocr_score'])}, "
                f"`{plate.get('filename')}`, {_age(plate.get('created_at'))} · {_reasons(plate)}"
            )
        lines.append("\nOpen **Recovery Centre** to inspect the candidates and confirm or correct a reading.")
        return Answer(
            intent=status,
            reply="\n".join(lines),
            plates=[plate_card(item) for item in items],
            suggestions=["Why did the last failed reading fail?", "What are the most common failure reasons?"],
        )

    def _recovery_stats(self) -> Answer:
        summary = self.db.summary(days=30)
        breakdown = self.db.recovery_breakdown(days=30)
        methods = self.db.method_breakdown(days=30)
        if not summary["retries"]:
            return Answer(
                intent="recovery_stats",
                reply=(
                    "No recovery retries have been recorded in the last 30 days. A retry is only triggered "
                    "when the crop looks blurry, dark, low-contrast or the first OCR reading is weak."
                ),
                metrics=summary,
            )
        lines = [
            f"In the last 30 days, **{_num(summary['retries'])}** plate readings triggered a recovery retry.",
            f"• **{_num(summary['recovered'])}** were recovered ({_pct(summary['recovery_rate'])} of retries)",
            f"• **{_num(summary['degraded'])}** were degraded by the retry and should be reviewed",
        ]
        for item in breakdown:
            if item["count"] and item["outcome"] not in {"recovered", "not_attempted"}:
                lines.append(f"• {item['label']}: **{_num(item['count'])}**")
        if methods:
            top = methods[0]
            lines.append(f"\nMost common selected pass: **{top['method']}** ({_pct(top['share'])} of selections).")
        lines.append("\nOutcome labels describe what the pipeline observed; only a verified reading establishes correctness.")
        citations = self._citations("recovery outcome labels retry policy", 2)
        return Answer(
            intent="recovery_stats",
            reply="\n".join(lines),
            citations=citations,
            metrics={"summary": summary, "breakdown": breakdown, "methods": methods},
            suggestions=["Show me the recovered plates.", "Why did the last failed reading fail?"],
        )

    def _failure_breakdown(self) -> Answer:
        items = self.db.failure_breakdown(days=30)
        if not items:
            return Answer(
                intent="failure_breakdown",
                reply="There are no recorded failure signals in the last 30 days. That usually means there is no data yet, not that recognition is perfect.",
                suggestions=["How many vehicles were analysed today?", "How does the review gate work?"],
            )
        lines = ["The most common failure signals in the last 30 days are:"]
        for item in items:
            lines.append(f"• **{item['reason']}** — {_num(item['count'])} ({_pct(item['share'])})")
        lines.append(
            "\nThe label is the signal that triggered attention, not proof of the root cause. "
            "A blur flag, for example, still needs a visual check of the crop."
        )
        citations = self._citations("failure taxonomy blur low light contrast format", 2)
        return Answer(
            intent="failure_breakdown",
            reply="\n".join(lines),
            citations=citations,
            metrics={"failures": items},
            suggestions=["Show me the plates that need manual review.", "What preprocessing is applied?"],
        )

    def _why_fail(self, text: str) -> Answer:
        plate = self._find_target(text)
        if not plate and any(word in text.lower() for word in ("last", "latest", "recent")):
            latest = self.db.list_plates(status="review", limit=1)["items"]
            plate = latest[0] if latest else None
        if not plate:
            recent = self.db.list_plates(status="review", limit=4)["items"]
            if recent:
                lines = ["I need a plate ID or a plate reading to explain a specific failure. Recent review-queue items:"]
                for item in recent:
                    lines.append(f"• #{item['id']} {_plate_title(item)} — `{item.get('filename')}`")
                lines.append("\nTry: `Why did plate 12 fail?`")
                return Answer(intent="why_fail", reply="\n".join(lines), plates=[plate_card(p) for p in recent])
            return Answer(
                intent="why_fail",
                reply="I could not find a plate to explain. There are no review-queue records yet, so upload an image first.",
            )
        return self._why_plate(plate, plate.get("failure_reasons") or [])

    def _why_plate(self, plate: dict, reasons: list[str]) -> Answer:
        lines = [
            f"**Plate #{plate['id']} — {plate.get('display_text') or 'Unreadable'}**  ",
            f"Source: `{plate.get('filename')}` · status: **{_status_text(plate)}** · captured {_age(plate.get('created_at'))}.",
            f"Detector confidence **{_score(plate.get('detector_confidence'))}**, OCR engine score **{_score(plate.get('ocr_score'))}** "
            "(a ranking signal, not a probability).",
            "",
            "**What the pipeline observed**",
        ]
        flags = [
            failure_label(item)
            for item in (plate.get("quality_flags") or [])
            if str(item).strip().lower() not in {"none detected", "none", ""}
        ]
        retry = [failure_label(item) for item in (plate.get("retry_reasons") or [])]
        if flags and flags != ["None detected"]:
            lines.append(f"• Quality flags: {', '.join(dict.fromkeys(flags))}.")
        else:
            lines.append("• Quality flags: no strong blur, lighting or contrast issue was detected.")
        if plate.get("retry_attempted"):
            lines.append(f"• Retry triggered by: {', '.join(dict.fromkeys(retry)) or 'weak OCR signal'}.")
        else:
            lines.append("• No recovery retry was triggered at the configured thresholds.")
        candidates = plate.get("candidates") or []
        if candidates:
            rendered = ", ".join(
                f"`{candidate.get('text') or '∅'}` ({_score(candidate.get('score'))}, {candidate.get('method')})"
                for candidate in candidates[:4]
            )
            lines.append(f"• Candidates considered: {rendered}.")
        if plate.get("selection_reason"):
            lines.append(f"• Selection: {plate['selection_reason']}.")
        if plate.get("retry_attempted"):
            delta = float(plate.get("recovery_delta") or 0)
            lines.append(
                f"• Score change after retry: **{delta:+.2f}**; outcome label: **{plate.get('recovery_outcome')}**."
            )
        if not plate.get("ocr_text"):
            lines.append("• The final result has **no readable text**, so this is an OCR failure rather than a low-confidence guess.")
        elif plate.get("review_status") == "needs_manual_review":
            lines.append("• The final reading did **not pass** the validation-selected review gate.")
        else:
            lines.append("• The final reading passed the review gate, but it is still a candidate, not a verified plate.")
        lines.append("")
        explanation = _failure_explanation(plate, flags, retry)
        if explanation:
            lines.append(f"**Why it matters:** {explanation}")
            lines.append("")
        query = " ".join(dict.fromkeys(flags + retry)) if (flags or retry) else "OCR confidence plate format review gate"
        citations = self._citations(query, 2)
        lines.append(
            "**Recommended action:** open the crop in Recovery Centre, compare the candidates, and confirm or correct "
            "the text. Enhancement cannot recover characters that are absent from the pixels."
        )
        return Answer(
            intent="why_fail",
            reply="\n".join(lines),
            citations=citations,
            plates=[plate_card(plate)],
            suggestions=["What preprocessing was applied?", "Show me the review queue.", "Show me the recovered plates."],
        )

    def _preprocessing(self, text: str) -> Answer:
        plate = self._find_target(text)
        methods = self.db.method_breakdown(days=30)
        if plate:
            candidates = plate.get("candidates") or []
            lines = [
                f"**Plate #{plate['id']} — {plate.get('display_text') or 'Unreadable'}** used these OCR passes:",
            ]
            if candidates:
                for candidate in candidates:
                    lines.append(
                        f"• `{candidate.get('method')}` → `{candidate.get('text') or 'no text'}` "
                        f"(engine {_score(candidate.get('score'))})"
                    )
            else:
                lines.append("• No candidate details were stored for this record.")
            lines.append(f"\nRetry attempted: **{'yes' if plate.get('retry_attempted') else 'no'}**.")
            if plate.get("retry_reasons"):
                lines.append("Trigger signals: " + ", ".join(failure_label(item) for item in plate["retry_reasons"]) + ".")
            if plate.get("enhanced_preview"):
                lines.append("An enhanced crop preview is stored with this record.")
            lines.append(
                "\nThe pipeline uses cubic upscaling, gamma correction for dark crops, CLAHE on the LAB lightness "
                "channel, mild unsharp masking, and adaptive thresholding as a separate candidate."
            )
            citations = self._citations("preprocessing gamma CLAHE unsharp adaptive threshold upscale", 2)
            return Answer(intent="preprocessing", reply="\n".join(lines), citations=citations, plates=[plate_card(plate)])
        lines = ["The recovery pass can apply:"]
        lines.append("• **Cubic upscaling** to at least 160 px height (2–4×).")
        lines.append("• **Gamma correction** for crops with mean brightness below 90.")
        lines.append("• **CLAHE** on the LAB lightness channel for local contrast.")
        lines.append("• **Unsharp masking** with a mild 1.5/−0.5 kernel.")
        lines.append("• **Adaptive thresholding** as a separate binary candidate.")
        if methods:
            lines.append("\nMost frequently selected pass in the last 30 days:")
            for item in methods[:3]:
                lines.append(f"• {item['method']} — {_num(item['count'])} ({_pct(item['share'])})")
        citations = self._citations("preprocessing gamma CLAHE unsharp adaptive threshold upscale", 3)
        return Answer(
            intent="preprocessing",
            reply="\n".join(lines),
            citations=citations,
            metrics={"methods": methods},
            suggestions=["Why did the last failed reading fail?", "What is the review gate?"],
        )

    def _plate_lookup(self, text: str) -> Answer:
        plate = self._find_target(text)
        if not plate:
            return Answer(
                intent="plate_lookup",
                reply=(
                    "I could not find that plate in the database. Check the ID or reading, or open "
                    "**Recovery Centre** to browse recent records."
                ),
                suggestions=["Show me the review queue.", "How many vehicles were analysed today?"],
            )
        lines = [
            f"**Plate #{plate['id']} — {plate.get('display_text') or 'Unreadable'}**",
            f"Machine reading: `{plate.get('ocr_text') or '∅'}` · original: `{plate.get('original_text') or '∅'}`",
            f"Status: **{_status_text(plate)}** · recovery: **{plate.get('recovery_outcome')}**",
            f"Detector **{_score(plate.get('detector_confidence'))}** · OCR engine **{_score(plate.get('ocr_score'))}** "
            f"(original {_score(plate.get('original_score'))})",
            f"Source: `{plate.get('filename')}` · {_age(plate.get('created_at'))}",
            f"Quality: {_reasons(plate)}",
        ]
        if plate.get("verified_text"):
            lines.append(f"Human verification: `{plate['verified_text']}` ({plate.get('verification_status')}).")
        if plate.get("retry_reasons"):
            lines.append("Retry reasons: " + ", ".join(failure_label(item) for item in plate["retry_reasons"]) + ".")
        return Answer(
            intent="plate_lookup",
            reply="\n".join(lines),
            plates=[plate_card(plate)],
            suggestions=["Why did this reading fail?", "What preprocessing was applied to it?"],
        )

    def _accuracy(self) -> Answer:
        bench = benchmark_summary()
        ocr = bench["ocr"]
        detector = bench.get("detector") or {}
        lines = [
            "The current internal evaluation is:",
            f"• OCR exact match: **{_pct(ocr['exact_match'])}** with recovery, "
            f"up from **{_pct(ocr['baseline_exact_match'])}** without it.",
            f"• Character error rate: **{_pct(ocr['cer'])}** with recovery, "
            f"down from **{_pct(ocr['baseline_cer'])}**.",
            f"• Review gate coverage: **{_pct(ocr['gate_coverage'])}** of crops; "
            f"**{_pct(ocr['gate_selective_accuracy'])}** of covered readings were exact.",
        ]
        if detector:
            lines.append(
                f"• Detector validation: precision **{_pct(detector.get('precision', 0))}**, "
                f"recall **{_pct(detector.get('recall', 0))}**, "
                f"mAP50 **{_pct(detector.get('map50', 0))}**, "
                f"mAP50-95 **{_pct(detector.get('map50_95', 0))}**."
            )
        lines.append(
            f"\nThese are internal development numbers on {_num(ocr['samples'])} held-out crops. "
            "The test split was inspected during development, so they are not a pristine final benchmark."
        )
        citations = self._citations("metrics exact match character error rate evaluation limitations", 2)
        return Answer(
            intent="accuracy",
            reply="\n".join(lines),
            citations=citations,
            metrics={"benchmark": bench},
            suggestions=["What is the review gate?", "Why are the accuracy numbers modest?"],
        )

    def _gate(self) -> Answer:
        bench = benchmark_summary()["ocr"]
        risk = bench.get("risk_control") or {}
        threshold = float(bench.get("gate_threshold") or 0.81)
        lines = [
            "The review gate is a **selective-prediction rule**: a reading is marked as a candidate only when it "
            f"matches a common Indian plate structure and its EasyOCR engine score is at least **{threshold:.2f}**.",
            f"That threshold was calibrated on validation predictions: it is the lowest one that keeps selective "
            f"error inside an **{_pct(risk.get('target_error', 0.08))}** budget. On the internal test set, "
            f"**{_pct(bench['gate_coverage'])}** of crops passed the gate and "
            f"**{_pct(bench['gate_selective_accuracy'])}** of those were exact "
            f"({_pct(risk.get('test_error', 0))} selective error), so the risk target held.",
            "Everything else is routed to **manual review**. The gate is a coverage-versus-risk trade-off, not a "
            "correctness guarantee, and the engine score is not a probability.",
        ]
        citations = self._citations("review gate threshold selective accuracy coverage", 2)
        return Answer(
            intent="gate",
            reply="\n".join(lines),
            citations=citations,
            metrics=bench,
            suggestions=["Show me the review queue.", "What are the evaluation limitations?"],
        )

    def _privacy(self) -> Answer:
        citations = self._citations("privacy uploaded image retention data protection", 3)
        reply = (
            "Uploaded images are decoded and processed **in memory**. The API does not save the original file. "
            "It stores a compact plate crop preview, the derived text, scores, quality flags and review status in the local SQLite database.\n\n"
            "That is still personal data: a plate can identify a vehicle and, indirectly, a person. A real deployment needs "
            "a lawful basis, access control, a retention period, and a correction/deletion process. The demo rows are synthetic."
        )
        return Answer(intent="privacy", reply=reply, citations=citations)

    def _architecture(self) -> Answer:
        citations = self._citations("architecture pipeline detector OCR recovery dashboard assistant SQLite", 3)
        reply = (
            "The pipeline has five stages:\n"
            "1. **Detect** — YOLOv8n locates plate boxes.\n"
            "2. **Read** — a fine-tuned EasyOCR recogniser reads an upscaled crop.\n"
            "3. **Diagnose** — brightness, contrast, Laplacian variance, OCR score and plate format decide whether to retry.\n"
            "4. **Recover** — enhanced and thresholded crops are read and compared with a format-aware selector.\n"
            "5. **Route** — a review gate sends uncertain readings to a human; every result is stored for analytics and the assistant.\n\n"
            "The backend is FastAPI + SQLite; the frontend is a dependency-free SPA; the assistant uses SQL + BM25 retrieval and can optionally call an LLM."
        )
        return Answer(intent="architecture", reply=reply, citations=citations)

    def _general(self, text: str) -> Answer:
        citations = self._citations(text, 3)
        if citations:
            paragraphs = []
            for item in citations[:2]:
                body = self.kb.section_text(item["doc"], item["section"]) or item["snippet"]
                paragraphs.append(f"**{item['section']}**\n{_excerpt(body)}")
            reply = (
                "Here is what the project documentation says, most relevant first:\n\n"
                + "\n\n".join(paragraphs)
                + "\n\nAsk about live results — counts, failures or a plate ID — and I will query the database instead."
            )
            return Answer(intent="general", reply=reply, citations=citations)
        return Answer(
            intent="general",
            reply=(
                "I can answer questions about stored ANPR results and about how the system works. "
                "Try asking for the review queue, a plate ID, the failure breakdown, or the evaluation metrics."
            ),
            suggestions=SUGGESTIONS[:4],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _find_target(self, text: str) -> dict | None:
        match = NUMBER_HINT.search(text)
        if match:
            plate = self.db.get_plate(int(match.group(1)))
            if plate:
                return plate
        token = PLATE_TOKEN.search(text.upper())
        if token:
            matches = self.db.find_plates(token.group(1), limit=1)
            if matches:
                return matches[0]
        # Bare number in a "why did 12 fail" style question.
        bare = re.search(r"\b(\d{1,6})\b", text)
        if bare and any(word in text.lower() for word in ("plate", "fail", "reading", "record")):
            plate = self.db.get_plate(int(bare.group(1)))
            if plate:
                return plate
        return None

    def _citations(self, query: str, k: int = 2) -> list[dict]:
        return [item.as_dict() for item in self.kb.search(query, k=k)]

    def _should_use_llm(self, answer: Answer) -> bool:
        if not self.llm.available or self.llm_mode == "off":
            return False
        if self.llm_mode == "always":
            return True
        return answer.intent in {
            "general", "architecture", "preprocessing", "why_fail", "accuracy", "gate", "privacy", "help",
            "llm_mode",
        } or bool(answer.citations)

    def _polish_with_llm(self, question: str, answer: Answer) -> Answer:
        context = []
        if answer.citations:
            sections = []
            for item in answer.citations:
                body = self.kb.section_text(item["doc"], item["section"]) or item["snippet"]
                sections.append(f"[{item['title']} — {item['section']}]\n{body[:2400]}")
            context.append("DOCUMENTATION:\n" + "\n\n".join(sections))
        if answer.metrics:
            context.append("METRICS:\n" + _compact_json(answer.metrics))
        if answer.plates:
            context.append("MATCHING PLATES:\n" + _compact_json(answer.plates))
        user = (
            f"QUESTION:\n{question}\n\n"
            f"{chr(10).join(context)}\n\n"
            "GROUNDED DRAFT (internal pre-check — its numbers and plate IDs are correct, but do not copy its wording):\n"
            f"{answer.reply}\n\n"
            "Answer the QUESTION directly and conversationally, in at most 170 words. Start with the answer itself, "
            "not with 'According to the documentation'. Keep every count, plate, score, percentage and filename exactly "
            "as given. Only if the documentation and draft genuinely do not cover the question, say so in one sentence."
        )
        try:
            result = self.llm.complete(SYSTEM_PROMPT, user[:12000], max_tokens=420)
            answer.reply = result.text
            answer.mode = "llm"
            return answer
        except LLMError as exc:
            answer.mode = "local_fallback"
            answer.llm_error = str(exc)[:300]
            return answer


def _compact_json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:4000]
    except (TypeError, ValueError):
        return str(value)[:4000]
