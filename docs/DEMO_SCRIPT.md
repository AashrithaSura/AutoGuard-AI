# AutoGuard AI — 6-minute demo script

## Before the demo

```powershell
# from the project root
.\.venv\Scripts\python.exe scripts\seed_demo.py --days 21
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Keep one clear vehicle image and one deliberately difficult/blurry crop ready in a folder. Have the assistant questions copied somewhere for quick pasting.

If the ML stack is not available on the demo machine, the console, review queue and assistant still work with the demo rows. Say that explicitly; it is a deliberate design choice.

---

## 0:00–0:40 — Frame the problem

> "Most ANPR demos stop at detect-and-read. The interesting failure is the confident wrong reading. AutoGuard is built around knowing when it does not know: it diagnoses the crop, retries OCR, applies a review gate, and lets a human correct the result. The assistant is grounded in those same records, not a generic chatbot."

Show the **Scan desk** (`#/scan`).

- Point to the intro panel: what the app is, and the three steps — upload a frame, analyze the batch, verify the read.
- Point to the side cards: five-stage pipeline and the 30-day ledger snapshot.
- Point to **Latest reads** under the intake card: "the six newest crops in the ledger, each one click from its evidence dossier." Turn demo data off first so the rail shows live readings only.
- Open the command palette with `Ctrl/Cmd + K` and jump to another view; this is the console, not a dashboard.
- Say: "These are internal development numbers, not a pristine benchmark. The test split was inspected during development. On the separate 110-crop IURS split, which the OCR never trained on, the shipped checkpoint reads 86.4% exact at 1.7% CER — but public photos are harder, which is why the gate exists."

## 0:40–1:10 — Demo data honesty

The top navigation shows **Demo data: on**.

> "These rows are synthetic and labelled `source='demo'`. The shell says so. I toggle it off and every list and count drops them. I never mix demo rows into an evaluation claim."

Click **Demo data: on** in the top navigation to switch to live only, open the **Plate archive**, then turn it back on.

## 1:10–2:20 — Scan desk

Stay on **Scan desk**. Upload the clear image, or use **Use camera** to capture one live.

Walk through one plate result:

1. **Locate** — detector score, merged-box count and any frame-edge warning. The detector runs at 1280 px and unions split boxes.
2. **Diagnose** — brightness, contrast, Laplacian variance; show a flagged crop.
3. **First read** — original reading and engine score.
4. **Heal** — which trigger fired, which pass won, the score delta. Drag the before/after slider to show the enhanced crop.
5. **Gate** — passed or needs review.

Say:

> "The OCR score is a ranking signal, not a probability. The gate is deliberately conservative. A passed reading is still a candidate until a human verifies it. Padding the crop and merging split boxes is what stops the half-plate reads."

If a plate is uncertain, type the visually checked text and click **Confirm correction**. Point out that the correction is stored in the same record and the review badge updates.

Open **Open dossier** on the result to show the evidence drawer, then close it with `Esc`.

## 2:20–3:00 — Intelligence

Go to **Intelligence** (`#/intel`), **Review gate** tab.

- Point to the two curves: validation and test.
- Drag the threshold slider from 0.5 to 0.95 and watch coverage, selective accuracy and error change.
- Find the dashed marker at **0.81**.

Say:

> "This is the novelty. Instead of hand-picking a confidence cutoff, the gate is chosen on validation under an 8% error budget: the lowest threshold whose selective error stays under 8%. That gave 0.81. On test, which was never used for selection, coverage is 58.2% and selective error is 7.3%, so the budget held. The page shows the whole trade-off, not one number."

Switch to **Restoration lab**, note that it is experimental and not in the production path, and that the UI says so. Then open **Training & data**: point to the 1,845-row composition (532 IURS rows), the baseline-vs-shipped comparison (+16.4 points internal, +31.8 points IURS), the 97-unique-plate composition with the largest plate's 20.6% share, the repeat-read vote (+1.0 point), and the shipped checkpoint timestamps.

Back on **Review gate**, point to the **Evidence ledger** interval (61.0–75.1%) and the **Review workload** panel: 58.2 auto-passed, 41.8 reviewed, 4.24 residual errors per 100 plates. Say:

> "That is the honest operating cost: about two in five plates still need a human, and the gate leaves roughly four errors per hundred accepted reads. Both numbers come from the measured test split, not from a vendor claim."

## 3:00–3:50 — Review queue

Go to **Review queue** (`#/review`).

- Show the **Review queue** segment.
- Search a plate or filename.
- Move with `j` / `k`; open **Explain** on a record.

Read the explanation aloud:

> "It lists the quality flags, the retry triggers, the candidates considered, the selection reason, the score change and the recommended action. This is generated from the stored record and the failure taxonomy, not from a generic prompt."

Switch to **Recovered** and **Corrected** segments. Confirm with `c` or reject with `x`, and point out that the review badge in the top navigation updates. Open the dossier and use **Reopen** to put the record back in the queue.

## 3:50–5:10 — Assistant

Go to **Assistant** (`#/assistant`).

Point to the sidebar first: **Recent evidence** lists the latest readings the assistant may cite — click **Inspect** on one to open its dossier without leaving the chat — and **Grounded knowledge** shows the document sections it retrieves from. Then use the starter cards on the empty canvas, or ask, in order:

1. *How many vehicles were analysed today?*
2. *Show me the plates that need manual review.*
3. *Why did plate 12 fail?* (use a real ID from the queue)
4. *What preprocessing was applied?*
5. *What is the review gate and how accurate is it?*
6. *What happens to my uploaded image?*

For one answer, click a **citation** chip. Say:

> "This is RAG over the project's own documentation. The model, when configured, receives the full retrieved sections plus a grounded draft and writes the prose; it does not choose the facts. If it fails, the local answer is still returned. The assistant cannot invent a count or a plate number because it retrieves them first."

If a model key is configured or a local Ollama instance is connected, point to the mode badge: **LLM + grounded context**. In the LLM panel, note that **Auto-connect** attaches to a running local Ollama within ~15 seconds and reattaches after a restart; **Disconnect** pauses it. If no server is running, click **Detect** and show the honest state: "not reachable on this machine; the grounded local answer is used." Then point to **Local grounded mode**.

## 5:10–5:50 — Architecture and evaluation

Show `docs/ARCHITECTURE.md` or the README diagram.

> "YOLOv8n detects, EasyOCR reads, the quality layer decides whether to retry, the selector picks a candidate, the gate routes to review, SQLite stores the record, and the console plus assistant read the same database."

Show the OCR results table:

> "Recovery adds 16.36 points of exact match and cuts CER by 8.9 points. But 31.5% of test crops are still not exact, so the system must route uncertainty to a human. That is the design, not a bug."

## 5:50–6:00 — Close

> "The contribution is the loop: measure failure, attempt bounded recovery, escalate when recovery cannot help, and explain the decision. The LLM is useful, but the system does not depend on it."

---

## Backup answers

**Why not MongoDB?** SQLite is a single file, offline, transactional and enough for the data volume. The repository interface isolates SQL, so a MongoDB implementation is a bounded change.

**Why not React?** The capstone must run on a laptop without a Node build step. The SPA is plain HTML/CSS/JS and still has routing, charts, modals and chat. If the project grows, React can replace the view layer without changing the API.

**Is the LLM hallucinating?** No. The deterministic answer is built first from SQL/BM25; the model then writes the prose from those facts and the full retrieved sections under a strict system prompt. If the model fails, the draft is returned unchanged.

**What is the accuracy?** 68.48% exact match on 165 internal held-out crops with the full recovery pipeline, 9.72% CER. The 0.81 gate, calibrated on validation at an 8% selective-error budget, covers 58.2% of test readings at 92.7% selective accuracy (7.3% error). Internal development estimate; external sample is 40% exact match on 25 crops under the earlier policy.

**What would you do with more time?** A new untouched test set, a second OCR engine, rectification measured on an external sample, more night/blur data, and per-domain gate calibration.
