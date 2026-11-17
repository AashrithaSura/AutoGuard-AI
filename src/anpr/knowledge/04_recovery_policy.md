# Recovery policy and review workflow

## Triggers

A recovery retry is triggered when at least one of these is true:

- the crop's Laplacian variance is below 75 (possible blur);
- mean brightness is below 65 (low light) or above 205 (overexposure);
- grey-level standard deviation is below 35 (low contrast);
- the original OCR engine score is below 0.65;
- the original reading does not match the Indian plate format.

These thresholds are engineering triggers, not probabilities. They were chosen to catch visibly degraded crops without retrying every clean plate. Retrying every plate would roughly triple CPU time.

## What is attempted

Additional candidates are produced from the crop: an enhanced colour version (gamma, CLAHE, unsharp mask), an adaptive-thresholded version, and, whenever a plate quadrilateral is detected, a perspective-rectified copy. All are upscaled before OCR. The original candidate remains in the pool and the original crop is never replaced. When the base reading is not a common-format plate with score at least 0.55, direct-CRNN readings (bypassing EasyOCR's text detector) and format-valid rotations are added as well. Duplicate readings collapse to the highest score for that text.

## How the winner is chosen

The format-aware selector described in the preprocessing document is used. It prefers a standard Indian state plate over a legacy-shaped or malformed reading. If the original is already standard, a challenger must beat it by at least 0.25 engine score. That margin was selected on the validation split to reduce churn between near-equal candidates.

## Outcome labels

- **Recovered** — the selected reading differs from the original and either gains a common Indian format or improves the engine score by at least 0.05.
- **Unchanged** — a retry ran but the selected text is the same.
- **Changed, low margin** — the text changed, but the score difference is smaller than 0.05 and no format gain was observed.
- **Degraded** — the selected reading lost at least 0.05 engine score relative to the original.
- **Still unreadable** — no OCR candidate produced text.
- **No retry needed** — the original passed the trigger checks.

These labels describe what the pipeline observed. They are not ground-truth accuracy labels; only a verified plate text can establish correctness.

## Human review

Every reading can be confirmed, corrected, or rejected in the Review queue (or from its evidence dossier). A correction is stored next to the machine reading, so the archive can report the correction rate. Exporting the CSV produces a review record suitable for an appendix or a lab notebook.

## Operational rule

Do not use the system to issue fines, gate access, or identify a person without an independent verification step. The plate text is personal data in many jurisdictions. Uploaded images are processed in memory and are not retained by default; only the derived plate record and a small crop preview are stored.
