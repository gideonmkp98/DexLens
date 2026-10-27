# Recognition and automatic crop fixes

## Changes

- Detect coloured outer borders using saturation as well as brightness/edges.
  Prefer a large plausible card over an internal illustration rectangle, including
  close-ups. The user still reviews the four corners before confirmation.
- Retry uncertain headers using clean and enlarged text regions; exclude evolution
  instruction lines. Read narrow collector-number strips separately from rules text.
- Retrieve up to 100 summaries per name hypothesis, enrich the strongest candidates'
  sets deterministically, and compare denominators without leading-zero differences.
- For incomplete numbers, optionally compare artwork from at most 32 named candidates.
  Downloads are restricted to TCGdex assets, four concurrent requests, a six-second
  total deadline, and a bounded thumbnail cache. Photos remain local. Provider image
  failures preserve text search. Artwork agreement alone never establishes high
  confidence or automatically confirms a card.
- Persist field evidence with migration 0007 so reloads preserve uncertainty and
  source regions. OCR reruns update previous OCR values without replacing manual edits.
- Correct the Steelix evaluation reference to Fusion Strike 139 (swsh8-139).

## Regression coverage

Real photo fixtures cover Charizard 4/130, Gastly 048/088, Pikachu 60/64, and the
low-resolution Steelix photo. Tests cover outer-border detection, denominator
normalization, best-candidate enrichment, visual discrimination, optional image
failure and host restrictions, and evidence persistence.

## Limits

This is a bounded heuristic recognizer, not a trained visual identification model.
Identical artwork on reprints, finishes, languages or editions requires checking
printed details. Low-resolution text can remain unreadable. Name queries are capped
at 100 results and image comparison at 32 candidates; this is not a full catalog
download. Automatic crop accuracy beyond the tested images is not guaranteed.
