# AutoGuard AI — Console Guide

This document explains every screen in the web console, where its data comes from, and what the user can do there.

The console is a task-based application, not a KPI dashboard. Five views share a top navigation bar: **Scan desk**, **Review queue**, **Plate archive**, **Intelligence** and **Assistant**.

---

## 1. Shell

### Top navigation

- Indigo gradient bar with the brand, five routed views and an active underline. The page header below it repeats the route eyebrow and title.
- The review badge counts readings waiting for a human decision.
- System status pill polls `/api/health`: green when the pipeline is ready, amber while loading, red when weights are missing.
- **Demo data: on/off** toggles `include_demo` for every list and analytics request. It never affects `/api/analyze`.
- **Export ledger** downloads `/api/analytics/export` as CSV.
- **New scan** goes to the scan desk and opens the file picker.

### Page header

- Eyebrow and page title for the current route.
- Benchmark chip with the measured exact match, CER and IURS figures from `/api/analytics/benchmark`.
- **Jump to…** opens the command palette (`Ctrl/Cmd + K`, or `?`).
- Live clock.
- Light/dark toggle (remembered in `localStorage`; `?theme=dark` also works).

### Command palette

- Searches navigation, actions and readings. Typing two or more characters searches the ledger through `/api/plates?q=…`.
- Actions: toggle demo data, switch theme, export CSV, open a vehicle image.
- Keyboard: `↑`/`↓` move, `Enter` open, `Esc` close.
- Vim-style navigation: press `G` then `S`, `R`, `A`, `I` or `C` for scan, review, archive, intelligence or assistant.

### Dossier drawer

Any reading can be opened as an overlay without leaving the current view. The drawer shows the plate chip, status, score ring, annotated source frame, before/after compare, five-step trace, candidate pool, observations and the verification controls. It is used by the scan desk, the archive, recent readings and the palette.

---

## 2. Scan desk (`#/scan`)

The recognition screen.

### Upload

- Drag and drop or click to browse; up to 8 frames per batch, 12 MB each, JPG/PNG/WEBP/BMP.
- **Use camera** captures a still from the browser camera into the same pipeline.
- Images are decoded and processed in memory; the database stores the reading and previews, not the original frame.

### Result card

Each analysed frame returns:

- annotated source frame with detector boxes
- padded plate crop and the enhanced crop behind a **before/after compare slider**
- character-cell plate reading with an engine-score ring
- detector score, merged-box count and a frame-edge warning when applicable
- gate and recovery status pills
- five trace steps: **Locate → Diagnose → First read → Heal → Gate**
- the ranked candidate pool and the selection reason
- observations (plain language)
- a verification box: confirm, correct or reject

Batch tools copy all plate readings or export the batch metadata as JSON. Every saved plate gets an **Open dossier** action.

### Layout

A short intro panel above the work area says what the app is and lists the three steps: upload a frame, analyze the batch, verify the read. Below it the intake card pairs a large drop target with a side column that carries the five-stage pipeline and a 30-day ledger snapshot. The drop target lists the accepted formats and decode limits as chips under the camera button.

Under the intake card, **Latest reads** shows the six newest crops from the live ledger as clickable cards (crop, plate, gate status, score); each opens the dossier. The rail is hidden on short viewports and once a batch finishes, when the result cards stack underneath the intake card instead; the whole view scrolls inside the window without moving the navigation. Every stored reading remains in **Plate archive**, and calibration evidence lives in **Intelligence**.

---

## 3. Review queue (`#/review`)

The human-in-the-loop desk.

### Segments

| Segment | Shows |
|---|---|
| Review queue | `review_status = needs_manual_review` and not decided. |
| Recovered | Retry improved the reading. |
| Corrected | Readings a human corrected (confirmed rows appear under All). |
| All readings | Every stored record. |

### Search

Searches plate text, filename and record id through `/api/plates?q=…`.

### List and inspector

The list shows plate chip, score, status and age. Selecting a row loads the inspector:

- score ring and character cells for the current reading
- annotated source frame
- before/after compare of original vs enhanced crop
- five-step trace
- quality flags and observations
- verify box (edit the text, then confirm or reject)
- **Explain** calls `/api/plates/{id}/explain`
- **Open dossier** for the full record

### Keyboard

`j` / `k` move through the filtered queue, `c` confirms the current reading, `x` rejects it. Typing in the verify field disables shortcuts.

### Status rules

- Corrected: `verification_status = corrected`
- Confirmed: `verification_status = confirmed`
- Rejected: `verification_status = rejected`
- Needs review: `review_status = needs_manual_review` and `verification_status = unreviewed`
- **Reopen** clears a decision and returns the record to the queue (`/api/plates/{id}/reopen`)

---

## 4. Plate archive (`#/archive`)

The evidence ledger for every stored reading.

- Columns: plate, status, engine score bar, source frame, captured age and **Open**.
- Filters: search, status segments (All / Needs review / Recovered / Corrected) and demo inclusion.
- Pagination: 30 rows per page with **Load more**.
- Clicking a row (or Enter) opens the dossier drawer.
- **Export ledger** in the top navigation downloads the CSV; the drawer can copy the plate text or export that one record as JSON.

---

## 5. Intelligence (`#/intel`)

Three tabs, deep-linkable as `#/intel/gate`, `#/intel/restore` and `#/intel/data`.

### Review gate

Replays `reports/gate_curve.json`.

- **Risk–coverage explorer**: validation (solid) and test (dashed) curves of selective accuracy against coverage, with markers at the current threshold.
- **Threshold slider** (`0.50`–`0.95`, step `0.01`) re-renders the chart and readout locally.
- **Readout**: validation accuracy/coverage, test accuracy/coverage, test error and whether the 8% risk budget is held.
- **Operating points** table lists binned thresholds with validation coverage, test coverage, test accuracy and test error. The validation-selected point is marked; nothing is tuned against test.
- **Evidence ledger** panel repeats the held-out exact match with its 95% Wilson interval, CER, character similarity (1 − CER), single-pass baseline, selective accuracy and crop count.
- **Review workload** turns the gate into staffing terms: auto-passed, sent to review and residual errors per 100 plates, plus the IURS review load.

If the calibration file is missing, the tab explains how to generate it (`python scripts/calibrate_gate.py`) instead of failing the whole view.

### Restoration lab

Experimental super-resolution comparison, outside the production path.

- Upload one low-resolution plate crop.
- Compare bicubic 4×, Real-ESRGAN 4× and the plate-specific RefineNet.
- OCR before/after, sharpness and other available metrics come back from `/api/restore`.

Restoration is not used for production readings because it has not proven a stable OCR gain on real validation crops.

### Training & data

Shows exactly what produced the shipped checkpoint.

- **Training composition**: total rows fit, IURS share and the prepared/IURS split bar, plus the train/val/test row counts read from `data/combined_ocr/summary.json`.
- **What the retrain bought**: baseline vs shipped exact match and CER on the internal prepared split and the external IURS split.
- **Domain check** (side): internal and IURS exact/CER, gate-conditioned IURS accuracy with its coverage.
- **Test composition** (side): crops vs unique plates, multi-crop vehicles, the largest plate's share, accuracy without it, and the per-plate macro average with its 95% interval — so a dominant plate cannot carry the headline.
- **Repeat-read voting** (side): first crop vs character-wise majority vote vs any-crop-correct, the multi-crop lift and the IURS block vote. Offline evaluation from `scripts/eval_frame_vote.py`; not in the production path.
- **Shipped checkpoints**: `plate_ocr.pth` and `plate_detector.pt` with size and modification time checked against the files on disk, directly under the retrain table.
- **Domain caution**: lab crops are close-ups; distant, angled or motion-blurred photos read worse, which is why the score gate routes them to review.

---

## 6. Assistant (`#/assistant`)

The grounded question-answering screen.

### What it answers

- live database questions: counts, review queue, low-confidence readings, recovered plates, failure reasons
- technical questions: pipeline stages, review gate, benchmark definitions, privacy and architecture

### How it is grounded

1. SQL answers live-data questions.
2. BM25 retrieves relevant sections from the project Markdown knowledge base.
3. An optional local LLM receives the **full** retrieved sections plus the deterministic draft and answers in its own words; the draft is a correctness check, not a template.

Without a model the same questions still get a written explanation or a quoted section. Data answers stay deterministic SQL output in both modes.

### Live LLM panel

- **Auto-connect is on by default**: when a local Ollama server with at least one model is reachable, the assistant attaches within about 15 seconds and reattaches after a restart. The panel polls quietly while the assistant view is open.
- **Detect** probes `http://127.0.0.1:11434` (loopback only) and lists installed models. If the server is running with **zero models**, the panel and the Detect toast both say so and show the `ollama pull llama3.2` command — "not detected" is reserved for an unreachable server.
- **Connect** switches to `LLM + grounded context`; **Disconnect** returns to local grounded mode and pauses auto-connect (the panel shows `Paused`) until **Connect** is used again.
- Remote hosts are rejected by the API. When no Ollama server answers, the assistant keeps working from SQL and documents.

### Chat

An empty session shows a short grounding statement and four starter questions (pulled from the backend suggestion list); clicking one sends it. Suggested questions also sit above the composer after an answer. Answers include citations and, where relevant, matching plates. **New chat** starts a fresh session; the last session id is remembered in the browser.

### Sidebar

- **Recent evidence** — the latest stored readings the assistant can cite, with gate status and engine score; **Inspect** opens that plate's dossier without leaving the chat.
- **Grounded knowledge** — the document sections currently indexed for BM25 retrieval, numbered by source document.
- **Capabilities** — what the data assistant and technical assistant answer, and the grounding rule.

The knowledge and capability panels fold away on short viewports so the conversation keeps the height.

---

## 7. Shared behaviour and data sources

| Surface | Endpoint |
|---|---|
| Pipeline status | `GET /api/health` |
| Scan | `POST /api/analyze?save=true` |
| Archive, search, palette readings | `GET /api/plates` |
| Dossier / inspector | `GET /api/plates/{id}` |
| Verify / reopen / delete | `POST /api/plates/{id}/verify`, `POST /api/plates/{id}/reopen`, `DELETE /api/plates/{id}` |
| Explain | `GET /api/plates/{id}/explain` |
| Gate curve | `GET /api/analytics/gate-curve` |
| Benchmark | `GET /api/analytics/benchmark` |
| CSV export | `GET /api/analytics/export` |
| Restoration lab | `POST /api/restore` |
| Assistant | `GET /api/assistant/*`, `POST /api/assistant/chat` |

Other behaviour:

- **Esc** closes the palette, drawer, modal or lightbox.
- Plate crops and annotated frames open in a full-size lightbox.
- The review badge refreshes after verification and reopen actions.
- Toasts confirm copies, exports, decisions and API errors.
- All five views fit a 1440 × 1000 desktop at 100% zoom; scan, review and the gate tab also fit 1440 × 900. On shorter screens Training & data scrolls inside the content area (the gate sidebar always scrolls independently), and the navigation stays fixed. The navigation collapses to icons at narrow widths.
