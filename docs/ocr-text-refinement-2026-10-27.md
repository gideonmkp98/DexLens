# OCR text refinement — 27 October 2026

This follow-up improves the extracted title itself, before catalog retrieval.
It does not substitute a catalog candidate's name for what OCR actually read.

## Findings and changes

- Narrow title crops can cut off initial letters. A padded, doubled grayscale
  version of the complete existing header provides an additional reading when
  primary confidence is below 85, within the same OCR deadline.
- Previously, any successful refinement replaced the primary reading. Readable
  primary title words now remain candidates, so a fragment must compete with
  the original title instead of automatically overwriting it.
- Title geometry previously measured every word's distance from one anchor.
  It now follows neighboring words on the same line. This preserves multiword
  titles while stopping at large gaps before unrelated text. Existing filters
  for smaller evolution instructions and HP labels remain in place.
- The source image, catalog matching rules, OCR timeout and confirmation workflow
  are unchanged. Optional OCR timeouts still preserve primary evidence.

## Regression coverage

Real Tesseract assertions check exact extracted names and collector numbers for
Magnemite, Typhlosion and Battle VIP Pass. Geometry tests cover a multiword title,
a distant unrelated label, smaller evolution text, and an `ex` suffix.

| Fixture | Previous extracted title | Updated extracted title |
| --- | --- | --- |
| `base1-53` | `cnemite` | `Magnemite` |
| `hgss1-110` | `STAGES` | `Typhlosion` |
| `swsh8-225` | `TRAIN` | `Battle VIP Pass` |

Backend verification: **257 tests passed** (one existing Starlette/httpx
deprecation warning); Ruff lint and formatting checks passed for the changed
OCR modules and tests. The API image was rebuilt and the running service was
recreated successfully, with a healthy status.

The complete 46-image regression was rerun on the rebuilt running image:

| Measure | Previous | Updated |
| --- | --- | --- |
| Exact extracted title (case-insensitive) | 27/46 | 34/46 |
| Correct first catalog candidate | 46/46 | 46/46 |
| Incorrect high-confidence catalog result | 0 | 0 |

No previously exact title became incorrect. All extracted collector numbers
remained unchanged, including existing errors. Seven titles became exact;
Professor Oak changed from one incorrect fragment to another and is explicitly
not counted as an improvement. The 46 inputs include catalog images, synthetic
distortions and seven user-scan fixtures; they are not 46 independent photographs.
Raw final results: [ocr-text-regression-2026-10-27.json](ocr-text-regression-2026-10-27.json).

These fixtures are development regressions, not an independent real-world
accuracy measurement. Difficult full-art titles and poorly readable numbers can
still be wrong. Raw OCR diagnostics remain available and are not rewritten with
catalog data. Existing scans need **OCR opnieuw uitvoeren** to refresh stored
text.
