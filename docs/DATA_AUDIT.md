# ANPR2 Dataset Audit

Read-only inspection of the raw data folders on 2026-11-10.

- 1,698 image files across `google_images`, `State-wise_OLX`, and `video_images`.
- 1,697 Pascal VOC XML annotation files; 1,697 annotated plate boxes with plate text.
- 984 distinct annotated text strings before pairing/duplicate filtering.
- 47 exact-duplicate image groups (47 extra copies); no exact-duplicate groups had conflicting labels.
- 219 plate-text groups repeat, accounting for 713 extra annotations; the largest groups contain 41 video frames for one plate.
- Two XML image references did not resolve by XML `<filename>`; one can be paired using its XML basename (`ML39.xml` -> `ML39.jpg`); `MH5.xml` has no matching image.
- Annotation boxes parsed without malformed/out-of-image coordinates against declared XML dimensions.
- Potential OCR-label anomalies to inspect: `CRETA`, `BLUR`, and `HP2020TR6255G`.

Preparation policy: do not modify raw data; pair by referenced filename then XML basename fallback; drop orphan annotations/unlabeled images from supervised training; deduplicate by image SHA-256; keep all frames for the same normalized plate text in one split; retain a reviewer list for suspicious OCR labels.
