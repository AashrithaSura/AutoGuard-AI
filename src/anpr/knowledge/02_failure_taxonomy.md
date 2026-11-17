# Failure taxonomy

## Motion and focus blur

**Signal:** Laplacian variance below 75 on the plate crop. A low value means edges are soft. **Typical cause:** camera movement, vehicle movement, missed focus, heavy compression, or a plate that is small in the frame. **Recovery:** unsharp masking after upscaling; adaptive thresholding can sometimes restore character edges. **Limit:** if character strokes have merged, sharpening creates artefacts rather than information. The correct action is a better frame or human review.

## Low light

**Signal:** mean grey level below 65. **Typical cause:** night capture, shadow, underexposure. **Recovery:** gamma correction (gamma between 1.15 and 2.0) followed by CLAHE on the LAB lightness channel. **Limit:** amplifying a dark crop also amplifies sensor noise.

## Overexposure

**Signal:** mean grey level above 205. **Typical cause:** headlights, sunlight reflection, or a brightly lit white plate. **Recovery:** CLAHE may recover local contrast; thresholding may separate characters from a blown-out background. **Limit:** clipped highlights contain no recoverable detail.

## Low contrast

**Signal:** grey-level standard deviation below 35. **Typical cause:** dirty plate, low-contrast paint, shadow across the plate. **Recovery:** CLAHE and adaptive thresholding. **Limit:** a plate whose characters are the same intensity as its background cannot be recovered by contrast enhancement alone.

## Low OCR confidence

**Signal:** mean EasyOCR engine score below 0.65, or below the calibrated 0.81 review-gate threshold. **Typical cause:** ambiguous characters (0/O, 1/I, 8/B, 5/S), unusual fonts, partial occlusion, or a crop that includes extra text. **Recovery:** enhanced and thresholded passes, plus format-aware candidate selection. **Limit:** the score is not calibrated; a confident wrong reading is possible.

## Format check failure

**Signal:** the selected reading does not match an Indian state plate pattern or a BH-series pattern. **Typical cause:** a missing or inserted character, a non-standard plate, a dealer plate, or OCR reading surrounding text. **Recovery:** prefer a candidate that matches a known state code, a two-digit district and a four-digit suffix. **Limit:** legitimate non-standard plates and personalised plates will fail this check.

## Low detector confidence

**Signal:** detector box confidence below 0.25. **Typical cause:** extreme angle, partial plate, unusual plate design, or a false positive such as a model-name badge. **Recovery:** none at the OCR stage; flag the box for review. **Limit:** a wrongly localised crop cannot be repaired by OCR enhancement.

## No plate detected

**Signal:** the detector returns no boxes above the threshold. **Typical cause:** plate too small, severe blur, night scene, or a vehicle type not represented in training data. **Recovery:** none in the current still-image pipeline. **Limit:** this is a detector recall problem, not an OCR problem, and should be reported separately.

## Why failure categories matter

Aggregating failure reasons turns a pile of bad readings into an actionable quality report. If most failures are "possible blur", the capture protocol is the problem. If most are "format check failed", the candidate-selection rules or the plate population may be the problem. If most are "low OCR confidence" on otherwise sharp crops, the recogniser needs more training data for that script or font.
