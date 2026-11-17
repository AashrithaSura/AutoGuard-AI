# AutoGuard AI — viva and interview questions

## Architecture and design

**Q: Why is this not just YOLO + EasyOCR?**
A: Detection and OCR are commodity stages. The project's contribution is the decision layer: quality diagnosis, bounded retry, format-aware candidate selection, a selective review gate, human correction, and grounded explanation. The evaluation measures the recovery policy and the gate, not only the detector.

**Q: Walk me through one image.**
A: Validate and decode in memory → YOLOv8 at 1280 px → merge split boxes, pad the crop, measure brightness/contrast/Laplacian variance → first OCR pass → retry if flagged or weak → enhanced/thresholded/wider-context/rectified candidates → format-aware selection → review gate → SQLite → scan desk/review queue/archive/assistant.

**Q: Why is the detector confidence threshold 0.15?**
A: A missed plate is more costly than an extra box. A false positive can be rejected by a human; a missed plate disappears. The low threshold is a recall-oriented choice, and the UI flags low detector scores.

**Q: Why 0.25 for the candidate margin?**
A: It was selected on validation data to prevent small score fluctuations from replacing an already valid reading. The exact value is less important than the policy: prefer structure, require a meaningful gain to switch. The test split was not used to tune it.

**Q: Why 0.81 for the review gate?**
A: It is not hand-picked. `scripts/calibrate_gate.py` sweeps thresholds on the validation split and selects the lowest one that keeps selective error at or below an 8% risk budget; that is 0.81, stored in `reports/gate_curve.json`. On test this accepts 58.2% of crops with 92.7% selective accuracy, and the risk target held, so the choice generalised. Lowering the threshold improves coverage but spends the error budget; the Intelligence view shows that trade-off live.

**Q: What is the hybrid rescue?**
A: If the base reading is not a common-format plate with score ≥ 0.55, the pipeline adds direct-CRNN readings (bypassing EasyOCR's text detector), enhancement/threshold variants, a perspective-rectified copy, per-row candidates and cyclic rotations that satisfy the Indian structure, then re-runs the selector. It is conservative: on test it gained 28 exact rows and lost 1 previously correct row. On validation it gained 21 and lost 0.

**Q: What does "self-healing" mean here?**
A: The system observes a failure signal, chooses a recovery action (gamma, CLAHE, sharpen, threshold, perspective rectification, direct-CRNN re-read), compares candidates, and records whether the result improved. It does not "fix" the image in a magical sense; it makes a bounded second attempt and escalates if it cannot help.

## Evaluation

**Q: What is your accuracy?**
A: Separate the claims. Detector validation: 98.68% precision, 100% recall, 99.31% mAP50, 83.99% mAP50-95. OCR: **68.48% exact match and 9.72% CER with the full recovery pipeline** on 165 internal held-out crops (52.12% / 18.68% for a single pass). Gate at the calibrated 0.81 threshold: 58.2% coverage and 92.7% selective accuracy on test. These are internal development estimates, not a pristine benchmark.

**Q: Why is exact match only around 68%?**
A: The original OCR training set has 784 unique labels — small for a 36-class sequence task. The retrain adds 532 IURS-reconstructed rows, which helped, but Indian plates vary in font and layout and the external sample is harder still. Rescue fixes ordering, enhancement and segmentation errors but cannot recover missing strokes. The system routes uncertainty to review instead of pretending.

**Q: Why report CER as well as exact match?**
A: Exact match treats one wrong character the same as five. CER gives partial credit and is sensitive to near misses. Reporting both prevents a single number from hiding the error distribution.

**Q: What is selective accuracy?**
A: Accuracy among the cases the gate accepts. It must be reported with coverage, because a gate can always improve selective accuracy by accepting fewer cases. 92.7% at 58.2% coverage is a deliberate risk-control trade-off, fixed before test inspection.

**Q: Is the test set clean?**
A: No. It was inspected during development and thresholds were iterated. The report says so. A pristine claim needs a new untouched set evaluated once after freezing code and thresholds.

**Q: How do you know the rescue helps?**
A: The evaluator runs the same code as the app on the same crops, with and without recovery. On 165 test crops, exact match moves from 52.12% to 68.48% and CER from 18.68% to 9.72%. We also compare row by row: 28 gains, 1 loss among previously correct rows. The per-crop CSV allows inspection of individual wins and losses.

## Generative AI and RAG

**Q: Where is the generative AI?**
A: The assistant has an optional LLM layer for rewriting grounded answers. The facts are retrieved with SQL and BM25 first; the model receives a draft and is instructed not to change numbers or add facts. The assistant page can detect and connect a local Ollama instance without a key; otherwise the deterministic answer is used. This is intentional: the capstone must work offline and must not hallucinate plate data.

**Q: Is this really RAG?**
A: Yes. The technical answers retrieve chunks from a versioned Markdown knowledge base with BM25 and include citations. The data answers retrieve rows from SQLite. The optional LLM is conditioned on both. A vector database would be a drop-in replacement behind `KnowledgeBase.search`.

**Q: Why BM25 instead of FAISS/Chroma?**
A: Six documents and 39 chunks do not justify an embedding service or a large dependency. BM25 is transparent, fast and adequate. The interface is intentionally small so it can be replaced when the corpus grows.

**Q: How do you prevent hallucination?**
A: (1) deterministic draft from SQL/BM25, (2) strict system prompt, (3) only a compact context block, (4) fallback to the draft on error, (5) UI shows the mode, (6) citations expose the source. The model cannot invent a count that is not in the draft without contradicting its instructions, and the fallback keeps the system useful if it does.

**Q: What data goes to the LLM?**
A: The question, aggregate metrics, retrieved documentation snippets and at most a handful of matching plate rows. No images, no full database dump. In local mode nothing leaves the machine.

## Data and engineering

**Q: Why SQLite?**
A: Offline, single file, transactional, zero server. The data volume is small. The `Database` class isolates SQL so MongoDB/PostgreSQL is a bounded change.

**Q: How do you handle concurrent requests?**
A: One SQLite connection per operation, short transactions, WAL mode, 30-second busy timeout. The ML pipeline is the expensive part; it is loaded once and reused.

**Q: What happens if the ML stack is missing?**
A: The API still starts. Health, analytics, recovery and assistant work. `/api/analyze` returns 503 with an install instruction. The ML imports are lazy by design.

**Q: How do you store images?**
A: The original upload is not persisted. The plate record stores a compact JPEG crop preview and, when a retry occurred, an enhanced preview. The annotated image is returned to the browser but not stored by default.

**Q: How do you test without models?**
A: Service tests use SQLite and the assistant with no ML. The pipeline test injects a fake detector and fake reader to verify retry, selection, encoding and gate behaviour. API contract tests use FastAPI's TestClient. A model download is not required for any of these.

## Product and ethics

**Q: What is the user workflow?**
A: Upload → inspect the five-step trace on the scan desk → confirm/correct/reject → see counts update in the review queue and archive → ask the assistant about the result. The scan desk is the entry point, the review queue is the operational surface, and the archive plus Intelligence view provide the evidence.

**Q: What are the privacy risks?**
A: Plates identify vehicles and can indirectly identify people. The app stores derived text and crop previews, not originals. A real deployment needs a lawful basis, access control, retention/deletion, and an audit trail. The UI avoids presenting a reading as certain.

**Q: What would you do with more time?**
A: A new untouched test set, a second OCR engine with disagreement-based review, rectification measured on an external sample, more night/blur training data, calibrating the gate on more domains, and authentication/audit logging.

**Q: What is the strongest part of the project?**
A: The loop from measurement to policy to human review to explanation. The numbers are modest, but the system knows when it does not know, and it can explain why.

**Q: What is the weakest part?**
A: OCR generalisation. The external sample is much harder than the internal test set. That is stated plainly rather than hidden.
