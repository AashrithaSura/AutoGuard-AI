# Preprocessing and OCR recovery

## Crop extraction

The detector provides a bounding box in source-image coordinates. The box is clipped to the image, then the crop is copied so that enhancement never modifies the source image or the annotated preview. Extremely thin or reversed boxes are discarded.

## Upscaling

The crop is resized with cubic interpolation. The scale factor is chosen so the crop is at least 160 pixels high, clamped between 2x and 4x. EasyOCR's detector needs enough vertical resolution to separate character strokes; small crops are a common cause of dropped characters.

## Gamma correction for dark crops

For a crop with mean brightness below 90, the pipeline builds a lookup table using `(pixel / 255) ** (1 / gamma)`, with gamma between 1.15 and 2.0. A higher gamma brightens shadows. The cap prevents the image from becoming washed out. Gamma is applied before colour-space work so the later steps operate on a more usable exposure.

## CLAHE

Contrast Limited Adaptive Histogram Equalisation is applied to the L channel in LAB colour space. Unlike global histogram equalisation, CLAHE works on small tiles and clips the contrast amplification, which reduces noise blow-up. The pipeline uses a clip limit of 2.0 and an 8x8 tile grid. CLAHE is applied to every retry, even when brightness is acceptable, because local contrast is often the limiting factor for white-on-white or shadowed plates.

## Unsharp masking

A Gaussian blur is subtracted from the image: `sharpened = 1.5 * image - 0.5 * blurred`. This increases edge acutance. It is deliberately mild; aggressive sharpening produces halos around characters and makes OCR worse. Sharpening cannot recover strokes that are not present in the original pixels.

## Adaptive thresholding

A Gaussian adaptive threshold converts the sharpened crop to a binary image. The threshold is computed per neighbourhood, so uneven lighting across a plate is handled better than with a single global cutoff. The binary image is converted back to three channels because EasyOCR expects a colour image. Thresholding is a separate candidate, not a replacement for the sharpened colour crop: sometimes colour carries useful information, sometimes binary removes background clutter.

## Candidate selection

The OCR pass returns text, an engine score, and the method that produced it. Duplicate texts keep their highest score. The selector then applies rules in this order:

1. If the original already matches the common Indian format, keep it unless a distinct common-format candidate improves the engine score by at least 0.25. This prevents small score fluctuations from replacing a good reading.
2. Otherwise, prefer the highest-scoring common-format candidate.
3. Otherwise, prefer any format-valid candidate (this allows legacy and BH-series shapes).
4. Otherwise, fall back to the highest raw score.

The 0.25 margin was selected on the validation split. It is frozen for test evaluation. Wide crops are read left-to-right by sorting text boxes on their left edge; tall crops are read top-to-bottom. This avoids EasyOCR returning characters out of order.

## Review gate

A reading passes the gate only when it matches a common Indian plate structure and its OCR engine score is at least **0.81**. That threshold is calibrated by `scripts/calibrate_gate.py` on validation predictions: the lowest threshold whose selective error stays within an 8% risk budget, stored in `reports/gate_curve.json`. On the corrected validation crops, 61.2% of readings pass at 92.1% selective accuracy; on the test split, 58.2% pass at 92.7% selective accuracy. The gate trades coverage for precision: most uncertain readings go to a human instead of being silently accepted.

## What enhancement cannot fix

Enhancement cannot invent missing characters, undo clipping, remove a physical occlusion, or correct a crop that contains the wrong object. When the characters are not present in the pixels, the honest output is "manual review", not a confident guess.
