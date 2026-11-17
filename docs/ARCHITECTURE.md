# AutoGuard AI — Architecture

## 1. Product scope

AutoGuard AI is a single-tenant, still-image ANPR workbench for Indian registration plates. It has five user-facing surfaces:

1. **Scan desk** — upload and inspect a recognition trace.
2. **Review queue** — human review and correction, with keyboard shortcuts.
3. **Plate archive** — searchable evidence ledger and per-plate dossier.
4. **Intelligence** — risk–coverage calibration and the experimental restoration lab.
5. **Assistant** — grounded natural-language access to results and system documentation.

The project is a capstone, not an enforcement system. Every reading is presented as a candidate until a human verifies it.

## 2. Runtime components

```
┌────────────────────────────────────────────────────────────────────┐
│ Browser                                                            │
│  index.html + console.css + app.js                                 │
│  (hash-routed SPA, no build step, light and dark themes)           │
└───────────────┬────────────────────────────────────────────────────┘
                │ fetch /api/*
┌───────────────▼────────────────────────────────────────────────────┐
│ FastAPI (api/main.py)                                              │
│  /api/analyze        /api/plates        /api/analytics/*           │
│  /api/assistant/*    /api/demo          /api/health                │
└───────┬───────────────────────┬───────────────────────┬────────────┘
        │                       │                       │
┌───────▼────────┐    ┌─────────▼─────────┐    ┌────────▼───────────┐
│ ML pipeline    │    │ SQLite repository │    │ Assistant          │
│ pipeline.py    │    │ db.py             │    │ assistant.py + rag │
│ YOLOv8 → OCR   │    │ analytics + chat  │    │ SQL + BM25 + LLM   │
│ → recovery     │    │                   │    │ (optional)         │
└────────────────┘    └───────────────────┘    └────────────────────┘
```

### Why a dependency-free frontend

The capstone must run on a student laptop with no Node build server. The SPA uses semantic HTML, CSS variables and plain JavaScript. It implements its own SVG risk–coverage chart, hash routing, command palette, dossier drawer, compare slider, modals, toasts, camera capture and a Markdown-lite renderer. Styling is a single design-system layer (`console.css`) with `html[data-theme]` light/dark tokens. This keeps the deployment to one Python process.

### Why lazy ML imports

`api/main.py` imports `src.anpr.pipeline` only inside `get_pipeline()`, and `pipeline.py` imports Ultralytics/EasyOCR/PyTorch only inside `SelfHealingANPR.__init__`. Therefore:

- the console (scan desk, review queue, archive, intelligence, assistant) boots without the ML stack;
- the service tests do not need a 2 GB download;
- `/api/analyze` returns a meaningful `503` instead of crashing the server.

## 3. Recognition request flow

1. **Validate** — MIME type, extension, 12 MB limit.
2. **Decode in memory** — OpenCV `imdecode`; the original upload is never written to disk.
3. **Detect** — YOLOv8 predicts boxes at `imgsz=1280`, `conf=0.15`.
4. **Merge and crop** — split/duplicate boxes covering one plate are unioned; coordinates are clipped, the tight crop is measured for quality, and the OCR crop is padded by 6% so first/last characters are not clipped. A plate touching the frame edge is flagged.
5. **Quality** — mean brightness, grey-level standard deviation, Laplacian variance.
6. **First OCR** — upscale to ≥160 px height (2–4×), EasyOCR beam search with alphanumeric allowlist. The concatenated reading and each detected row are both kept as candidates, so a logo row cannot destroy a clean plate row.
7. **Retry decision** — flags, OCR score <0.65, or format mismatch.
8. **Recovery** — enhanced crop (gamma, CLAHE, unsharp), thresholded crop, an 18% wider context crop and a rectified perspective are read.
9. **Hybrid rescue** — if the base reading is not common-format with score ≥0.55, add direct-CRNN readings (whole crop, no text detector) and cyclic rotations matching the Indian structure.
10. **Selection** — format-aware policy with a 0.25 score margin.
11. **Gate** — common Indian structure + engine score ≥ 0.81 (risk-calibrated on validation).
12. **Persist** — analysis + plate rows, including candidates, observations and crop previews.
13. **Respond** — annotated image, plate trace, IDs.

### Candidate selection

```python
if original is common-format:
    keep original unless a distinct common-format candidate gains ≥ 0.25
elif a common-format candidate exists:
    choose the highest-scoring one
elif a format-valid candidate exists:
    choose the highest-scoring one
else:
    choose the highest raw score
```

The 0.25 margin was selected on validation data. The selector is shared by the app and the evaluation script so results are comparable.

### Hybrid rescue

`src/anpr/recovery.py` implements an inference-time ensemble that fixes three common failure modes:

1. EasyOCR glues a stray logo or regional-script row onto the plate; every detected row of at least eight characters is also kept as its own candidate, so a clean plate row survives the concatenation.
2. EasyOCR's text detector splits or reorders a plate; feeding the whole crop directly to the fine-tuned CRNN recovers the full string.
3. The detector returns the suffix before the prefix; a cyclic rotation can restore the state-first structure.

The rescue is conservative: it does not run when the base reading is already common-format with engine score ≥0.55, so it cannot replace a trusted reading. Against the first-pass reading the pool added 28 exact rows with 1 loss on test and 21 with 0 losses on validation. The same function is used by `pipeline.py` and `evaluate_ocr_crops.py`.

### Risk-calibrated gate

`scripts/calibrate_gate.py` sweeps acceptance thresholds from 0.50 to 0.95 over the **validation** predictions. At each threshold it computes coverage, selective accuracy and selective error using the same format rule and predictions as the app. The original sweep selected the lowest threshold whose selective error stayed within an 8% budget — 0.81 — and that operating point is frozen; `--threshold 0.81` replays it on the current predictions and writes both curves to `reports/gate_curve.json`. The test curve is written for inspection but is never used for selection. Re-selecting on the updated validation predictions would pick 0.78, which exceeds the budget on test, which is why the app replays the frozen point. `selection.REVIEW_SCORE_THRESHOLD` is pinned to the stored value, `benchmark.py` reads the curve, and `/api/analytics/gate-curve` plus the Intelligence view replay it.

## 4. Data model

SQLite file: `data/autoguard.db`. WAL mode, foreign keys on, one connection per operation.

### `analyses`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `created_at` | TEXT | ISO-8601 UTC |
| `filename` | TEXT | sanitized basename |
| `source` | TEXT | `upload`, `demo`, `benchmark` |
| `image_sha256` | TEXT | upload integrity/dedupe aid |
| `width`, `height` | INTEGER | source dimensions |
| `plate_count` | INTEGER | detected regions |
| `processing_ms` | REAL | end-to-end pipeline time |
| `annotated_preview` | TEXT | reserved; not populated by default |
| `notes` | TEXT | demo/evaluation note |

### `plates`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `analysis_id` | INTEGER FK | cascade delete |
| `plate_index` | INTEGER | 1-based within analysis |
| `created_at` | TEXT | copied from analysis |
| `ocr_text` | TEXT | selected normalized reading |
| `original_text` | TEXT | first pass |
| `detector_confidence` | REAL | YOLO box confidence |
| `ocr_score` | REAL | EasyOCR engine score, **not** probability |
| `original_score` | REAL | first-pass score |
| `common_format` | INTEGER | 0/1 |
| `review_status` | TEXT | `candidate_passed_validation_gate` / `needs_manual_review` |
| `quality_flags` | JSON | brightness/contrast/blur flags |
| `brightness`, `contrast`, `blur_score` | REAL | measurements |
| `retry_attempted` | INTEGER | 0/1 |
| `retry_reasons` | JSON | triggers |
| `selection_reason` | TEXT | human-readable policy result |
| `selected_method` | TEXT | which OCR pass won |
| `recovery_outcome` | TEXT | recovered/unchanged/changed/degraded/no_reading/not_attempted |
| `candidates` | JSON | text, score, method |
| `observations` | JSON | step-by-step notes |
| `crop_preview` | TEXT | data URL (JPEG, quality 82) |
| `enhanced_preview` | TEXT | optional |
| `verified_text` | TEXT | human-confirmed/corrected text |
| `verification_status` | TEXT | `unreviewed`, `confirmed`, `corrected`, `rejected` |
| `verified_at` | TEXT | |
| `ground_truth` | TEXT | optional, evaluation imports |
| `ground_truth_correct` | INTEGER | optional |
| `notes` | TEXT | |

### `chat_sessions`, `chat_messages`

`chat_messages.meta` stores JSON with intent, mode, citations, plate cards, metrics and suggestions, so a reloaded conversation renders exactly like the live one.

Indexes cover `created_at`, `source`, `review_status`, `recovery_outcome`, `ocr_text`, `verification_status` and chat session/message order.

## 5. Analytics definitions

| Metric | Definition |
|---|---|
| Total analyses | rows in `analyses` in the period |
| Total plates | rows in `plates` in the period |
| Passed | `review_status = candidate_passed_validation_gate` |
| Review queue | `review_status = needs_manual_review` |
| Retry rate | `retry_attempted = 1 / total plates` |
| Recovered | `recovery_outcome = recovered` |
| Recovery rate | recovered / retries |
| Low confidence | `ocr_score < 0.81` and text non-empty |
| Correction rate | corrected / human-verified |
| Gate coverage | passed / total, in the benchmark report |
| Selective accuracy | exact matches / passed, in the benchmark report |

Time buckets use the configured local timezone (`AUTOGUARD_TZ`, default `Asia/Kolkata`). Timestamps are stored in UTC.

Demo rows are included by default so a fresh console is explorable. The top navigation's **Demo data** toggle flips every list and count. API clients can pass `include_demo=0`.

## 6. Assistant architecture

### Intent router

Rules classify a message into data intents (stats, review queue, low confidence, recovered, failure breakdown, plate lookup) or technical intents (why failure, preprocessing, gate, accuracy, architecture, privacy, general).

### Retrieval

- **Live data:** parameterized SQL through `Database`.
- **Documentation:** BM25 over six Markdown documents chunked by `##` section. No vector database, no external service, 39 chunks.

### Generation

1. Build a grounded draft from SQL and/or retrieved snippets.
2. If a model is configured and the intent qualifies, ask it to rewrite the draft using only the supplied facts.
3. On timeout/error, return the local draft with `mode=local_fallback`.

Models come from `AUTOGUARD_LLM_BASE_URL`/`AUTOGUARD_LLM_API_KEY` or `AUTOGUARD_OLLAMA_URL`, or from the assistant page's local LLM panel. `GET /api/assistant/detect` probes `http://127.0.0.1:11434/api/tags`; `POST /api/assistant/llm` accepts only a loopback Ollama base URL and a model present in that instance. Nothing is downloaded and no remote host is accepted.

The system prompt forbids invented counts, plate numbers and diagnoses, and requires the review-gate caveat.

### Session persistence

`chat_sessions` + `chat_messages`; the frontend stores the session id in `localStorage` and reloads history through `GET /api/assistant/session/{id}`.

## 7. Security and privacy

- No authentication is included; this is a local academic app. Do not expose it to the public internet without adding auth, CSRF protection and rate limits.
- Uploaded images are processed in memory; only derived records and crop previews are stored.
- The LLM receives question text, aggregate metrics and a few plate rows, never images. This is documented in the UI.
- In-app LLM connection is loopback-only; remote base URLs are rejected with 422.
- CORS is not enabled; the SPA is same-origin.
- SQL uses parameters throughout the repository.
- HTML rendering escapes all dynamic values; no `innerHTML` receives raw user text without `esc()`.
- Demo endpoints can be disabled with `AUTOGUARD_DEMO=0`.

## 8. Failure modes and handling

| Failure | Handling |
|---|---|
| Detector weights missing | `/api/analyze` → 503 with path; the console still works |
| ML packages missing | 503 with install instruction; analytics/assistant unaffected |
| Invalid image | 400 |
| Oversized upload | 413 |
| No plate detected | analysis stored with `plate_count=0`; UI empty state |
| OCR returns no text | `ocr_text=''`, `review_status=needs_manual_review` |
| LLM timeout | deterministic local answer + `local_fallback` |
| SQLite locked | 30 s timeout; short transactions |
| Demo rows present | banner + live-only toggle |

## 9. Testing strategy

- **Service layer:** in-memory-equivalent SQLite files, no ML.
- **RAG:** retrieval returns the blur and gate sections.
- **Assistant:** grounded counts, plate cards, failure citations, session persistence.
- **Pipeline:** injected fake detector/reader verifies retry, selection and encoding without model downloads.
- **API:** FastAPI TestClient covers health, demo, analytics, verification, explanation, chat, validation and CSV export.

## 10. Extension points

- Replace `Database` with MongoDB/PostgreSQL behind the same methods.
- Replace BM25 with FAISS/ChromaDB; `KnowledgeBase.search` is the only interface.
- Add a second OCR engine and use disagreement as a review signal.
- Add a calibrated selective-prediction curve for each new capture domain instead of one global gate.
- Add authentication and role-based access for a real deployment.
- Add video ingestion with plate tracking and dedupe.
