# Dataset Status

## 1. Current production dataset

The model currently shipped with the project was fine-tuned on the corrected Indian plate dataset in `data/prepared_corrected/` plus the plate crops reconstructed from the IURS character set (section 2). Splits for training and model selection use `data/combined_ocr/`; accuracy is reported on the original plate-level test split only.

| Item | Count |
|---|---:|
| Raw XML annotation files | 1,697 |
| Usable unique scene images | 1,649 |
| Exact duplicate copies removed | 47 |
| Plate-text groups | 983 |
| Detection split: train / val / test | 1,319 / 165 / 165 |
| OCR crops: train / val / test | 1,313 / 165 / 165 |
| Unique OCR texts: train / val / test | 784 / 96 / 97 |

Splits are grouped by exact image hash and normalised plate text, so the same plate does not appear in both training and test.

This is the dataset behind the reported results (currently shipped checkpoint, full pipeline including the rectification and per-row candidates):

- OCR exact match: **68.48%**
- Character error rate: **9.72%**
- Review gate: frozen at **0.81**, selected on validation under an 8% selective-error budget (`reports/gate_curve.json`)
- Test coverage: **58.2%**
- Test selective accuracy: **92.7%** (7.3% selective error)

## 2. The 8,168-image IURS set: reconstructed into plate crops

The **IURS ANPRIND Character Detection** dataset has **8,168 images** and **79,792 character boxes** across 36 character classes (`0–9`, `A–Z`). It is published on Mendeley Data under **CC BY 4.0**.

| Split | Images | Character boxes |
|---|---:|---:|
| Train | 7,148 | 69,821 |
| Validation | 680 | 6,649 |
| Test | 340 | 3,322 |
| **Total** | **8,168** | **79,792** |

The 8,168 files are not 8,168 scenes: Roboflow shipped flipped and rotated copies and repeated sources across its own splits. The archive labels *characters*, not plates, so it cannot be used for text recognition as-is.

### Conversion

`scripts/prepare_iurs_plates.py` rebuilds plate-level examples from the character boxes:

1. cluster character boxes into plate groups and split each group into lines ordered top-to-bottom, left-to-right (two-line plates included);
2. keep only strings that satisfy an Indian plate grammar;
3. read every crop in four orientations (normal, vertical flip, 180°, horizontal flip) with the fine-tuned CRNN and keep the orientation whose reading matches the annotated text; drop groups no orientation can read. This removes the mirrored copies and any crop that is rotated in-plane;
4. keep one variant per `(source, text)` and at most two variants per plate text;
5. split by `md5(plate_text)`, not by Roboflow's split, so no plate crosses splits;
6. write two-line plates as one row per line, matching how the pipeline's text detector hands each line to the recogniser.

Output lives in `data/iurs_plates/` (`crops/`, `ocr/train|val|test.csv`, `summary.json`) plus a contact sheet at `reports/iurs_qa_sheet.png`. It is generated, so it can be rebuilt; the raw archive is never modified.

| Item | Count |
|---|---:|
| Source images with a usable plate | 951 |
| Candidate plate groups | 1,989 |
| Kept plates / rows | 694 / 768 |
| Rows: train / val / test | 532 / 126 / 110 |
| Two-line plates (rows) | 74 (148 rows) |
| Unique plate texts | 546 |

An audit found **no full plate text shared** between these splits and the original `prepared_corrected` splits (0 overlap), so the two sources can be combined without full-label leakage. Within IURS, eight test rows are degenerate fragments (`GJ01`, `GJ01T`, `GJ18`, `GJ27T`) that also occur in IURS training; they stay in the 110-crop domain check. `scripts/combine_ocr_datasets.py` writes the combined manifests to `data/combined_ocr/`.

### Is it useful?

It is character-level supervision for the *recogniser*, not a plate-level benchmark: its labels come from character boxes, and the crops are mostly clean frontal plates, so accuracy on it would overstate real-world performance. It is used as extra training material; the model is selected on the original validation split and reported on the original plate-level test split. The 110 IURS rows are reported as a within-source domain check, not an independent benchmark.

## 3. External datasets evaluated and not used

| Dataset | Why not used |
|---|---|
| NPDS / Indian plate detection set | Detection boxes only; no plate text. |
| Ultralytics shared plate set | 331 images, detection only; no text labels. |
| External YOLOv8n plate detector | Lower mAP50-95 than the project detector on the held-out split. |
| Restoration datasets | Synthetic degradation; restoration reduced OCR exact match. |

## 4. What would improve accuracy most

1. **300–1,000 real plate crops with exact text labels** from the target camera domain.
2. **150–500 crops with four corner points** for perspective rectification.
3. A clean, untouched **150–300 image test set** that is never inspected during development.
4. A second OCR reader (for example PaddleOCR) used only as a disagreement signal.
5. Character-level data only after the above are in place.

## 5. Honest claim

> “The current system is trained on 1,649 unique scene images plus 694 plate crops reconstructed from the IURS character set, and reports 68.48% exact-plate accuracy with 9.72% CER on a grouped internal test split. The 8,168-image IURS archive is used only as extra character-supervised training material for the recogniser, not as a benchmark; accuracy is measured on the original plate-level test split.”
