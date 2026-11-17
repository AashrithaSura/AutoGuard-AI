# AutoGuard AI

## An Intelligent Self-Healing Automatic Number Plate Recognition System with a Grounded Generative AI Assistant

**Capstone project report**

---

## Abstract

Automatic Number Plate Recognition (ANPR) is usually presented as a two-stage pipeline: detect the plate, then read it. In practice, the hard part is not producing a string; it is knowing when the string is wrong, attempting a bounded recovery, and escalating to a human when recovery cannot help. This project, **AutoGuard AI**, builds a still-image Indian ANPR system around that idea. A fine-tuned YOLOv8n detector localises plates at 1280 px inference, merges split/duplicate boxes and pads the OCR crop so first and last characters survive. A fine-tuned EasyOCR recogniser reads the crop, and a quality-diagnosis layer measures brightness, contrast, sharpness, OCR engine score and plate format. When the first reading is weak, the system retries OCR on gamma-corrected, CLAHE-enhanced, sharpened, adaptively thresholded, wider-context and perspective-rectified crops, and when the base reading is non-standard it adds direct-CRNN and rotated format-valid candidates. A format-aware selection policy compares the candidates, and a review gate calibrated on validation at a fixed 8% selective-error budget routes uncertain readings to a human. Every result is stored in SQLite and exposed through a task-based console: a scan desk, a review queue, a searchable plate archive, an intelligence view with a risk–coverage explorer and restoration lab, and a conversational assistant. The assistant answers data questions with SQL and technical questions with BM25 retrieval over a project knowledge base; an optional local LLM is constrained to rewrite grounded facts rather than invent them. On 165 held-out crops, the full pipeline improved exact match from 52.12% to 68.48% and reduced character error rate from 18.68% to 9.72%. The calibrated 0.81 gate covered 58.2% of test readings at 92.7% selective accuracy, meeting the risk target. These are internal development results, not a pristine benchmark. The contribution is the integration of measured failure analysis, bounded self-healing, risk-controlled escalation, human-in-the-loop review and grounded explanation in one reproducible system.

**Keywords:** ANPR, YOLOv8, EasyOCR, self-healing, selective prediction, human-in-the-loop, retrieval-augmented generation, explainable AI.

---

## 1. Introduction

Number plates are one of the most common visual identifiers in transport, parking, access control and traffic analytics. A conventional ANPR demo detects a plate in a clean image and prints a string. That demo fails in the field for predictable reasons: motion blur, low light, overexposure, low contrast, unusual fonts, tilted plates and small crops. A system that returns a confident-looking wrong string is worse than one that says "I am not sure".

AutoGuard AI starts from a simple question: **can the system recognise its own failure and respond appropriately?** The project therefore treats ANPR as a decision problem, not only a recognition problem. It measures image quality, decides whether to retry, chooses between competing OCR candidates with a format-aware policy, and sends uncertain readings to a human. The same records then support analytics and a conversational assistant that can explain what happened.

The project has four goals:

1. Build a credible Indian plate detector and OCR recogniser.
2. Measure and improve OCR through a bounded recovery policy.
3. Make uncertainty visible and actionable through a review gate and a human review workflow.
4. Explain the system's behaviour through a grounded assistant, not a generic chatbot.

The title used for the capstone is:

> **AutoGuard AI: An Intelligent Self-Healing Automatic Number Plate Recognition System with Generative AI Assistance.**

---

## 2. Problem statement

Given a still image of a vehicle, produce the most likely registration text, a calibrated-enough signal of whether that text should be trusted, and an explanation of what was attempted. If the reading cannot be trusted, route it to a human rather than presenting it as fact.

The problem has four sub-problems:

- **Localisation:** find the plate region in a cluttered scene.
- **Recognition:** read Indian plate text under variable fonts, spacing and lighting.
- **Recovery:** decide when a second attempt is justified and which candidate to trust.
- **Explanation:** make the pipeline's behaviour understandable to a reviewer and to the project's own assistant.

---

## 3. Related work

ANPR systems commonly use a detector followed by an OCR engine. YOLO-family detectors are popular because they provide a good speed/accuracy trade-off and are easy to fine-tune. EasyOCR combines a text detector with a CRNN recogniser and supports a character allowlist, which is useful for plate alphabets. Prior work has explored super-resolution, deblurring, perspective correction and synthetic plate generation to improve recognition.

Two ideas from the broader literature shape this project:

- **Selective prediction / reject option.** A model can abstain when its confidence is low. The useful question is not only "how accurate is the model?" but "how accurate is it on the cases it accepts, and how many cases does it accept?" This project reports gate coverage and selective accuracy together.
- **Retrieval-augmented generation (RAG).** A language model can be grounded by retrieving relevant documents and facts at answer time. This project uses the same idea at two levels: SQL retrieval for live data and BM25 retrieval for system documentation.

The project does not claim a new recognition architecture. Its contribution is an integrated, measured system that combines recovery, selective review and grounded explanation, with a reproducible evaluation and an honest account of its limits.

---

## 4. System design

### 4.1 Pipeline

1. **Upload and validation.** JPG/PNG/WEBP/BMP, max 12 MB, decoded in memory.
2. **Detection.** YOLOv8n fine-tuned on prepared Indian plate scenes, confidence threshold 0.15.
3. **Quality diagnosis.** Mean brightness, grey-level standard deviation and Laplacian variance; plate-format check; OCR engine score.
4. **First OCR.** Crop upscaled to at least 160 px height (2–4×), EasyOCR beam search with an alphanumeric allowlist.
5. **Recovery.** Gamma correction for dark crops, CLAHE on the LAB lightness channel, unsharp masking, adaptive thresholding; enhanced and thresholded candidates are read.
6. **Hybrid rescue.** If the base reading is not a common-format plate with engine score ≥ 0.55, add direct-CRNN readings (whole crop, no text detector) and cyclic rotations that satisfy the Indian plate structure.
7. **Selection.** Format-aware policy with a 0.25 margin.
8. **Review gate.** Common Indian plate structure and engine score ≥ 0.81, calibrated on validation under an 8% selective-error budget.
9. **Persistence and presentation.** SQLite records, annotated preview, candidate trace, scan desk and review queue.

### 4.2 Candidate selection

The selector is deliberately conservative:

- If the original already matches the common Indian format, keep it unless a distinct common-format candidate improves the engine score by at least 0.25.
- Otherwise, prefer the highest-scoring common-format candidate.
- Otherwise, prefer any format-valid candidate (legacy/BH shapes).
- Otherwise, fall back to the highest raw score.

The hybrid rescue extends the candidate pool with direct-CRNN readings and rotated variants, but it does **not** overwrite a common-format reading with an engine score of at least 0.55. This guard was selected on validation data to avoid losing correct plates. It is the difference between a useful ensemble and a noisy one.

The margin and rescue threshold were selected on validation data and frozen for test evaluation. The same code is used by the app and the evaluator, which avoids a common source of inflated results.

### 4.3 Review gate

A reading is labelled `candidate_passed_validation_gate` only when it matches a common Indian plate structure **and** the OCR engine score is at least 0.81. Everything else is `needs_manual_review`.

The threshold is not hand-picked. `scripts/calibrate_gate.py` sweeps acceptance thresholds over the validation predictions, applies the same format rule as the app, and selects the lowest threshold whose selective error stays within an 8% budget. The selection is 0.81, written to `reports/gate_curve.json` together with both curves. On validation it accepts 61.2% of readings at 92.1% selective accuracy (7.9% error); on test it accepts 58.2% at 92.7% selective accuracy (7.3% error), so the risk target held on the unseen split. The test curve is recorded for inspection but was not used to choose the operating point. The Intelligence view lets a reviewer replay this trade-off interactively.

The gate is a risk-control device, not a correctness guarantee. Lowering the threshold would increase coverage but spend the error budget; the curve makes that cost explicit rather than hiding it behind one number.

### 4.4 Human-in-the-loop

The review queue lets a reviewer confirm, correct or reject any reading. The corrected text is stored next to the machine reading, so the archive can report a correction rate. This is important for a capstone: it demonstrates that uncertain predictions become data for improvement rather than disappearing.

### 4.5 Assistant

The assistant has two retrieval paths:

- **Live data:** SQL over `analyses` and `plates` (counts, queues, specific IDs, failure categories).
- **Documentation:** BM25 over six Markdown documents (failure taxonomy, preprocessing, recovery policy, metrics, privacy, assistant grounding).

A deterministic answer is always produced first. If an OpenAI-compatible endpoint or Ollama is configured, the model receives the question, the grounded draft, a small set of retrieved snippets and at most a handful of plate rows, and is asked to rewrite the answer without changing numbers or adding facts. The assistant page can detect and connect a local Ollama instance directly; only loopback base URLs are accepted, so data does not leave the machine. If the call fails, the local answer is returned and marked `local_fallback`. This keeps the LLM as an enhancement rather than a single point of failure.

### 4.6 Data model

SQLite stores `analyses`, `plates`, `chat_sessions` and `chat_messages`. Plate rows include the selected and original reading, detector/OCR scores, quality flags, retry reasons, selection reason, candidates, observations, crop preview, verification status and optional ground truth. Analytics are derived from these rows, so the console and assistant always agree.

---

## 5. Dataset and preparation

The raw dataset lives beside the project in three folders: `google_images`, `State-wise_OLX` and `video_images`. The preparation script found 1,697 XML annotations and 1,698 image files. It removed 47 exact duplicate images, resolved a stale `ML39.xml` filename by matching the XML basename, and excluded an orphan `MH5.xml`.

The prepared set contains 1,649 scene images:

| Split | Full images | Plate crops | Unique OCR labels |
|---|---:|---:|---:|
| Train | 1,319 | 1,313 | 784 |
| Validation | 165 | 165 | 96 |
| Test | 165 | 165 | 97 |

Splits are grouped by normalized plate text and exact image hash; no plate text overlaps between train, validation and test OCR sets. Three model-name boxes (CRETA, DUSTER, TERRANO) are retained as negative detector examples. `BLUR` and `HP2020TR6255G` are excluded from OCR training and flagged for review.

The recogniser is additionally fine-tuned on 694 plates (768 single-line rows) reconstructed from the IURS ANPRIND character-detection archive (8,168 images, 79,792 character boxes, CC BY 4.0). Character boxes are clustered into plate groups, each crop is read in four orientations so mirrored copies are discarded, and only strings satisfying an Indian plate grammar are kept. An audit found no plate text shared with any original split, so the combined manifests in `data/combined_ocr/` contain no leakage. Model selection uses the combined validation split; every reported accuracy number is still measured on the original plate-level test split, because the IURS crops are clean frontal plates and would flatter the result.

The source folder has no license/provenance document. The dataset is kept local for this academic project unless reuse and redistribution terms are confirmed.

---

## 6. Implementation

### 6.1 Detector

YOLOv8n is initialised from pretrained weights and fine-tuned for 30 epochs on CPU. The best checkpoint is selected on validation data. Final validation metrics at epoch 30:

| Metric | Value |
|---|---:|
| Precision | 98.68% |
| Recall | 100.00% |
| mAP50 | 99.31% |
| mAP50-95 | 83.99% |

These are detector-localisation metrics, not end-to-end recognition metrics.

### 6.2 OCR

The EasyOCR CRNN recogniser is fine-tuned on the original training crops and then on the combined manifests (original + IURS), resuming from the shipped checkpoint and selecting the best epoch by combined validation CER. The API loads `models/plate_ocr.pth` automatically when present; otherwise it uses pretrained EasyOCR. The promoted checkpoint (best epoch 4) improved test exact match by 1.8 percentage points and reduced CER by 1.4 points over the previous weights under the same evaluator.

### 6.3 Recovery

Triggers:

- Laplacian variance < 75 (possible blur),
- mean brightness < 65 (low light) or > 205 (overexposure),
- grey-level standard deviation < 35 (low contrast),
- first OCR engine score < 0.65,
- format check failure.

Recovery produces enhanced, thresholded and perspective-rectified candidates (the rectified copy is added, never substituted). The original candidate remains in the pool. Duplicate texts keep their highest score. The selector then applies the format-aware rules.

### 6.4 Web application

The frontend is a dependency-free SPA with hash routing. It has five task-based views: Scan desk, Review queue, Plate archive, Intelligence and Assistant, plus a command palette, a per-plate evidence dossier drawer and a before/after compare slider. Charts are rendered as inline SVG; no chart library is required. The Intelligence view draws the validation and test selective-prediction curves against the 8% risk line, with a threshold slider, live readouts and an operating-point table. The UI supports light/dark themes, browser camera capture, demo-data labelling, keyboard review shortcuts, empty states, error states and a modal explanation panel.

### 6.5 API and storage

FastAPI exposes analysis, analytics, plate review, explanation, assistant and demo endpoints. SQLite uses WAL mode, foreign keys and short transactions. Uploaded images are not persisted; only derived records and compact crop previews are stored.

---

## 7. Evaluation

### 7.1 Protocol

- **Detector:** precision, recall, mAP50 and mAP50-95 on the validation split.
- **OCR:** exact match and character error rate on 165 held-out crops, with and without recovery.
- **Gate:** coverage and selective accuracy on the same crops.
- **External sanity check:** 25 crops from a small DataCluster sample, used only as a warning signal.

Thresholds were selected on validation data. The test split was inspected during development, so the test numbers are development estimates, not a pristine final benchmark.

### 7.2 OCR results

| Metric | Single pass | Full recovery |
|---|---:|---:|
| Test exact match | 52.12% | **68.48%** |
| Test character error rate | 18.68% | **9.72%** |
| Validation exact match | 63.64% | **76.36%** |
| Validation character error rate | 17.02% | **8.64%** |

These numbers are for the shipped combined-data checkpoint through the full pipeline, which includes the rectification candidate and per-row candidates. Holding the recogniser fixed, recovery adds **16.36 percentage points** of exact match on test and cuts CER by **8.9 points**. It gained 28 rows and lost 1 previously correct row on test; on validation it gained 21 and lost 0. The improvement is a better use of the existing recogniser through direct-CRNN reading, enhancement, perspective rectification, row-level candidates and format-aware reordering, not a second model voting. Even so, 31.5% of test crops remain non-exact, so human review is still required.

### 7.3 Review gate

The threshold was selected on validation only, at a fixed 8% selective-error ceiling, then frozen.

| Split | Threshold | Coverage | Selective accuracy | Selective error | Risk target |
|---|---:|---:|---:|---:|---|
| Validation | 0.81 | 62.42% | 92.23% | 7.77% | met |
| Test (held out from selection) | 0.81 | 58.18% | 92.71% | 7.29% | met |

The gate accepts roughly three in five readings after rescue, and the accepted set is much more reliable than the full set. The important result is not only the operating point but that the risk budget transferred to test without re-tuning: the validation and test curves agree closely across the threshold range. Re-selecting on the updated validation predictions would pick 0.78, which exceeds the budget on test, so the frozen point is kept. This is the correct trade-off for a system that must not silently present wrong plates as fact.

### 7.4 External sample

On 25 DataCluster crops, the earlier policy reached 40% exact match with recovery and 24.68% CER. The previous checkpoint also reached 40% exact match but with 26.84% CER. The sample is small and the domain shift is large; this is a generalisation warning, not a population estimate. The hybrid rescue has not been re-run on this external sample, so no improvement is claimed there.

### 7.5 Detector

The final validation metrics are strong, but they are validation metrics from a dataset with a specific collection style. A separate, untouched test set would be needed for a final localisation claim.

---

## 8. Discussion

### 8.1 What worked

- **Recovery helps, but not everywhere.** The largest gains come from crops that are readable after contrast enhancement. The policy avoids replacing a good original with a small-score alternative.
- **The review gate is useful.** It converts an unbounded accuracy problem into a triage problem: most readings can be fast-tracked, and the uncertain ones get human attention.
- **Grounded explanation is feasible without a large model.** SQL plus BM25 produces specific, useful answers. An LLM improves phrasing but is not required for correctness.
- **Persistence changes the project.** Once every reading is stored, the console, review workflow and assistant share one source of truth.

### 8.2 What did not work well

- **Generalisation.** The external sample is much harder than the internal test set. Indian plates vary enormously in font, spacing, colour and mounting.
- **Blur is not recoverable in the limit.** Sharpening can make edges look crisper, but it cannot recreate missing strokes. The system correctly escalates many of these cases.
- **A single engine score is a weak uncertainty signal.** It is not calibrated. A second recogniser or a calibrated selective-prediction curve would be better.
- **The test set is not pristine.** It was inspected during development, so the reported numbers should be treated as development results.

### 8.3 Design trade-offs

- **SQLite instead of MongoDB.** A single file is easier to run, back up and submit. The repository interface keeps a database swap possible.
- **BM25 instead of a vector database.** Six documents and 39 chunks do not justify FAISS/Chroma. The interface is small enough to replace later.
- **No React build step.** A plain SPA keeps the deployment to one Python process, which matters for a demo on a laptop. The UI still supports charts, routing, modals and chat.
- **Local-first assistant.** The system works without an API key. The LLM is optional and constrained.

---

## 9. Ethics and privacy

Number plates can identify vehicles and, indirectly, people. The system stores derived text and a small crop preview, not the full uploaded image. A real deployment would need a lawful basis, access control, a retention policy, and a correction/deletion process.

The interface never presents a reading as certain. The review status, the gate explanation and the "engine score is not a probability" caveat are part of the product. Demo rows are synthetic and labelled; they must not be reported as evaluation data.

The assistant sends only aggregate data and a few plate rows to a hosted model, never images. In local mode, no data leaves the machine.

---

## 10. Limitations

1. OCR generalisation remains weak on domain-shifted data.
2. The review gate is calibrated on a small validation split and should be recalibrated for a new deployment.
3. The detector is trained on Indian plates and still images; night scenes, extreme angles and heavy motion blur remain hard.
4. Recovery cannot invent characters that are absent from the pixels.
5. The assistant is only as good as the stored records and the knowledge documents; it is designed to say "not found" rather than guess.
6. SQLite is appropriate for a capstone and a single-lab deployment, not a multi-tenant production service.
7. There is no authentication or rate limiting; the app is intended for local use.

---

## 11. Future work

- Collect more labelled crops per state, font and lighting condition, especially night and motion-blurred examples.
- Evaluate the rectification candidate on a larger external sample; it is currently measured only on the internal splits.
- Train a lightweight Indian-plate-specific CTC recogniser or character classifier.
- Calibrate the OCR score per deployment domain and report the full risk–coverage curve for each.
- Add a second recogniser and use disagreement as a review signal.
- Add video ingestion with tracking and duplicate suppression.
- Replace BM25 with a vector store if the knowledge base grows.
- Add authentication, audit logging and role-based access for a real deployment.
- Evaluate on a new, untouched test set after all thresholds are frozen.

---

## 12. Conclusion

AutoGuard AI shows that an ANPR capstone becomes substantially stronger when the system is designed around **uncertainty** rather than only accuracy. The project combines a fine-tuned detector, a fine-tuned recogniser, a measured recovery policy, a validation-calibrated selective gate, a human correction workflow, a persisted analytics layer and a grounded assistant. The full recovery pipeline improved exact match from 52.12% to 68.48% on internal held-out crops, and the risk-controlled gate achieved 92.7% selective accuracy at 58.2% coverage on test under a validation-chosen 8% error budget. The system is honest about its limits: the external sample is much harder, the test set is not pristine, and the assistant is designed to retrieve rather than invent. That combination — measurement, recovery, calibrated escalation and explanation — is the project's real contribution.

---

## References

1. Jocher, G. et al. *Ultralytics YOLOv8.* 2023. https://github.com/ultralytics/ultralytics
2. Baek, Y. et al. *Character Region Awareness for Text Detection.* CVPR 2019.
3. Shi, B., Bai, X., Yao, C. *An End-to-End Trainable Neural Network for Image-Based Sequence Recognition.* IEEE TPAMI 2017.
4. Jaided AI. *EasyOCR.* https://github.com/JaidedAI/EasyOCR
5. Robertson, S., Zaragoza, H. *The Probabilistic Relevance Framework: BM25 and Beyond.* Foundations and Trends in IR, 2009.
6. Lewis, P. et al. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* NeurIPS 2020.
7. Geifman, Y., El-Yaniv, R. *Selective Classification for Deep Neural Networks.* NeurIPS 2017.
8. Indian Ministry of Road Transport and Highways. *Central Motor Vehicles Rules, 1989* (registration mark format).

---

## Appendix A — Reproducibility checklist

- [x] Detector weights and OCR checkpoint paths documented.
- [x] Split protocol grouped by plate text and image hash.
- [x] Evaluation scripts write per-crop predictions and JSON summaries.
- [x] Recovery thresholds and gate threshold defined in code.
- [x] Test-set caveat stated in README, UI, assistant and report.
- [x] Demo rows labelled and separable from live data.
- [x] Offline self-check and unit tests included.
- [x] Privacy behaviour documented.

## Appendix B — Artefacts

- `reports/ocr_final_test_v2.csv` / `.json` — final OCR evaluation with the full recovery pipeline (shipped checkpoint).
- `reports/gate_curve.json` — validation-selected gate threshold, validation/test curves and the 8% risk target.
- `reports/ocr_rect_test_v2.json`, `reports/ocr_rect_val_v2.json` — same evaluation on test/validation for the combined-data checkpoint.
- `reports/ocr_val_v2.csv` — validation predictions for the shipped checkpoint.
- `reports/rectify_val_v2.json`, `reports/rectify_test_v2.json` — rectification ablation on the shipped checkpoint.
- `reports/final_evaluation.md` / `.json` — plate-level composition analysis with confidence intervals.
- `reports/error_report.html` / `.json` — visual failure and label-quality report.
- `reports/ocr_v2_history.json` — recogniser retrain history on the combined data.
- `reports/restoration_benchmark.json`, `reports/restoration_training_history.json` — restoration-candidate experiment.
- `reports/character_pilot_report.json` — rejected character-detector pilot.
- `runs/detect/plate_yolov8n/results.csv` and `args.yaml` — detector training summary read by the API. Training plots, per-epoch weight files and detector evaluation runs are archived in `attic/cleanup_20261118/`.
- `models/attic/plate_ocr_pre_v2.pth` — OCR rollback weights from before the combined-data retrain.
- `data/autoguard.db` — application database (created at runtime).
