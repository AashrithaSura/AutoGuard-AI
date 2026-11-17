# AutoGuard AI system overview

## Purpose

AutoGuard AI is a still-image Automatic Number Plate Recognition (ANPR) system for Indian registration plates. It does not stop at "detect and read". It also measures image quality, decides whether a reading is trustworthy, retries OCR on enhanced crops when the first attempt is weak, records what changed, and routes uncertain results to a human reviewer.

## Five modules

1. **Plate localisation.** A YOLOv8n detector fine-tuned on 1,319 prepared scene images finds plate bounding boxes at 1280 px inference and a low confidence threshold (0.15), because a missed plate is more costly than an extra box that a reviewer can reject. Overlapping boxes that cover one plate are merged, and the OCR crop is padded by 6% so first and last characters are not clipped.
2. **OCR.** EasyOCR's CRNN recogniser is fine-tuned on 784 unique plate labels. The recogniser reads an upscaled crop with a beam-search decoder. Readings are normalised to uppercase letters and digits.
3. **Self-healing recovery.** The pipeline measures brightness, contrast and Laplacian variance (sharpness). It also checks OCR engine score and Indian plate format. Any of these signals can trigger a retry. Retries use gamma correction, CLAHE, unsharp masking and adaptive thresholding, plus a wider-context crop and perspective rectification. The best candidate is chosen by a format-aware policy rather than by raw OCR score alone.
4. **Review and evidence.** Every analysis is persisted in SQLite. The console has a scan desk, a review queue, a searchable plate archive and an intelligence view: throughput and corrections are inspectable per reading, and uncertain readings are queued for a human decision.
5. **Conversational assistant.** The assistant answers questions about stored results and explains the pipeline. It uses intent routing plus a small BM25 retrieval index over this documentation. If an OpenAI-compatible LLM or a local Ollama server is configured, the assistant can rewrite grounded facts into natural language; otherwise a deterministic local answer is used.

## Request flow

An upload is decoded in memory. The detector returns one or more boxes. For each box the pipeline crops the plate, records quality measurements, runs the original OCR pass, and optionally runs two enhanced passes. Candidate selection applies the Indian state-plate format and a 0.25 score margin. The review gate labels the result as passed or needing review. The API stores the analysis and plate rows, then returns annotated previews and a structured trace.

## Important caveat

The OCR engine score is a ranking signal, not a probability that the reading is correct. Passing the review gate means "this reading met a validation-selected rule"; it is not a guarantee. Operational use still requires visual verification or a second independent recogniser.

## Why SQLite

The capstone must run offline on a student laptop. SQLite is a single file, requires no server, supports transactions and JSON text columns, and is more than adequate for hundreds or thousands of analyses. The repository interface isolates SQL so a MongoDB or PostgreSQL implementation can replace it without changing the API.
