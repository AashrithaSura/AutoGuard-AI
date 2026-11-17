# Metrics, evaluation and limitations

## What the numbers mean

**Detector precision** is the fraction of predicted boxes that overlap a ground-truth plate at the chosen IoU threshold. **Detector recall** is the fraction of ground-truth plates that received a matching box. **mAP50** averages precision across confidence thresholds at 0.50 IoU. **mAP50-95** averages over IoU thresholds from 0.50 to 0.95 and is the stricter localisation score.

**OCR exact match** is the fraction of plate crops whose normalised predicted text equals the annotated text exactly. **Character error rate (CER)** is the Levenshtein edit distance divided by the number of ground-truth characters. CER gives partial credit for near misses; exact match is the operational metric.

**Gate coverage** is the fraction of readings that pass the review gate. **Selective accuracy** is exact-match accuracy among the readings that pass. A gate can always increase precision by rejecting more cases, so coverage and selective accuracy must be reported together.

## Internal results in this project

On 165 held-out test crops, the fine-tuned recogniser with the full recovery pipeline reached **68.48% exact match** and **9.78% CER**, compared with **52.12% / 18.68%** for a single pass. The review gate is calibrated on validation at 0.81 under an 8% selective-error budget; on test it covered **58.2%** of crops and **92.7%** of covered readings were exact (7.3% selective error), so the risk target held. Detector validation performance at the final epoch was approximately **98.7% precision**, **100% recall**, **99.3% mAP50** and **84.0% mAP50-95**.

These are internal estimates. The test split was inspected during development and thresholds were iterated, so the numbers are development results rather than a pristine final benchmark. The external DataCluster sample was much harder: 40% exact match with recovery on 25 crops. That is a warning about generalisation, not a population estimate.

## Why the numbers are modest

Indian plates vary in font, spacing, colour, state code, and mounting angle. The original training set has 784 unique OCR labels, which is small for a character recogniser; the recogniser was later fine-tuned with 532 additional rows reconstructed from the IURS character-box dataset, which improved the held-out result but does not remove the domain gap. Blurry and low-resolution crops remain difficult. EasyOCR's recogniser was trained on scene text, not specifically on Indian plates, and fine-tuning on a small set can overfit the training distribution.

## What would improve the result

- Collect more labelled crops per state and per plate style, especially night and motion-blurred examples.
- Add a plate-corner detector so rectification starts from learned corners instead of edge contours.
- Train a lightweight character classifier or a CTC model on synthetic plates with Indian fonts.
- Calibrate the OCR score on more domains and keep the risk budget fixed while coverage is measured.
- Evaluate on a new, untouched test set after all thresholds are frozen.
- Add a second recogniser and use disagreement as a review signal.

## Privacy and ethics

Number plates can identify vehicles and, indirectly, people. The system stores derived text and a small crop preview, not the full uploaded image. The demo data is synthetic. Real deployment would need a lawful basis, a retention policy, access control, and a way to correct or delete records. The interface never presents a reading as certain: the review status and the "score is not a probability" caveat are part of the product, not fine print.

## Reproducibility

Every threshold used by the app is defined in `src/anpr/selection.py` or in the pipeline's quality function. The evaluation scripts write per-crop predictions and JSON summaries. The database schema is created automatically. The assistant's knowledge base is plain Markdown in `src/anpr/knowledge`, so explanations can be reviewed and versioned like code.
