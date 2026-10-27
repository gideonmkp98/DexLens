# Recognition audit — 27 October 2026

The earlier readiness claim overstated the evidence. The implementation failed on
new Geodude and Meganium scans, and the earlier benchmark had no independent
camera photographs. This audit fixes the underlying retrieval and OCR behavior,
and distinguishes regression checks from independent evaluation.

## Root causes and changes

| Area | Failure | Implemented correction |
| --- | --- | --- |
| Title OCR | Whole-region confidence preferred noise such as `RE` and `CE`; fixed crops clipped names on other layouts. | Read a full header and alternative title regions. Select text using word geometry, confidence and completeness; separate distant HP labels. |
| Collector numbers | Texture, light text and clipped footer bands produced wrong or partial pairs. | Independent grayscale/inverted footer readings, dark-ink fallbacks, agreement between readings, and extra checks for severely disproportionate pairs. Reject alphabetic text after promo prefixes. |
| Catalog provider | 13 mappings pointed to nonexistent TCGdex IDs, including `sv3pt5`, `sv1` and `swsh12pt5`; two SV set names were associated with the wrong release. | Correct mappings against the live TCGdex set list, including `MEW → sv03.5`, `SSP → sv08`, `PRE → sv08.5`, `CRZ → swsh12.5`, and `PGO → swsh10.5`. |
| Retrieval | First-page number searches and a ten-card enrichment budget excluded the right printing before image comparison. | Use the small set-summary list and its official printed counts to retrieve number candidates directly. Continue name searches through up to three pages; bounded token/prefix fallback handles damaged names. Protect full-number candidates when selecting the processing budget. |
| Ranking | Shared attacks and HP saturated scores, causing older reprints to tie with the correct printing. | Cap secondary evidence, preserve denominator conflict penalties, discard zero-score results, and downgrade close ties. |
| Artwork | Comparison stopped after too few candidates and missed newer printings with damaged OCR suffixes. | Compare up to 128 on-demand candidate thumbnails when the denominator is missing (32 otherwise). Near-identical artwork can recover a candidate; final confirmation still requires the user. |
| Availability | Optional OCR retries could exhaust the deadline and discard useful primary text. | Preserve successful primary evidence if an optional pass times out; show an incomplete-result warning. Bound Tesseract's internal threads in Docker. |
| Repeated work | Recognition bypassed the catalog's caching strategy. | A bounded read-through cache deduplicates repeated/concurrent metadata, detail and search lookups, with existing TTL/stale-fallback behavior. |

No full-catalog import, startup preload, paid OCR service or external upload of
the user's photograph was introduced. Only provider metadata, selected set
summaries and candidate thumbnails are fetched on demand. Evaluation images in
`tests/fixtures/additional_catalog` are test fixtures, not a runtime card database.

## Verification

The local API Docker image was rebuilt and the running service recreated. Existing
uploads and application data were retained. Unit/integration tests use the separate
test database, not the user's scan database.

The complete live HTTP workflow — upload, automatic corner detection, crop preview,
crop confirmation and recognition — returned the correct first candidate for:

| Input | Expected catalog card | Result |
| --- | --- | --- |
| User Geodude scan, 47/62 | `base3-47` (Fossil) | Correct |
| User Meganium Prime scan, 109/123 | `hgss1-109` | Correct |
| User Meganium scan, 8/214 | `sm8-8` | Correct |
| Catalog Magnemite reference, 53/102 | `base1-53` | Correct |

The original Magnemite upload was not found. The Magnemite check therefore uses a
provider reference and must not be represented as a successful retest of that
original photograph. The browser also displayed Geodude/Fossil as the first match,
with the correct 47/62 number and loaded images.

Raw live results: [recognition-live-workflow.json](recognition-live-workflow.json).

### Final regression run

The final rebuilt API passed **252 backend tests** against the dedicated MariaDB
test database. Ruff lint and formatting checks passed. The dependency's existing
Starlette/httpx deprecation warning remains; there were no test failures.

| Image category | Correct first candidate | Correct in top five |
| --- | --- | --- |
| Seven user-scan regression inputs | 7/7 | 7/7 |
| Existing clean catalog examples | 10/10 | 10/10 |
| Existing synthetic distortions | 10/10 | 10/10 |
| Added catalog examples | 19/19 | 19/19 |
| Total evaluated image cases | **46/46** | **46/46** |

No incorrect high-confidence results occurred in this run. These are development
regressions, not an independent accuracy estimate. Two requested references were
excluded before OCR: `sm3.5-73` has no provider image, and `swsh12.5-GG44` was an
invalid fixture reference. Its actual ID, `swsh12.5gg-GG44`, also has no provider
image, as verified separately. Neither exclusion is counted as a successful test.

Raw results: [recognition-regression-2026-10-27.json](recognition-regression-2026-10-27.json).

### Independent catalog check

Ten cards were sampled deterministically with seed `20261027` across ten sets,
after the main changes. The first run returned **10/10 correct first candidates**,
**10/10 correct in the top five**, and **zero incorrect high-confidence results**.
Median recognition latency was **4.67 seconds**, maximum **7.17 seconds**.

This includes Electabuzz, Politoed, Switch, Volcarona, Dhelmise, Rescue Carrier,
Mimikyu, Aegislash, N's Darumaka and Xatu. Raw OCR names were correct in 7/10 cases;
the collector pair or artwork recovered the remaining identities. This distinction
is important: a correct catalog result does not mean every editable OCR field is
correct. The Mimikyu result correctly remained low confidence after a wrong OCR
number; Xatu remained medium confidence without a recognized number.

These are **clean catalog images, not camera photographs**. Subsequent use of this
sample becomes regression testing. Raw results:
[recognition-holdout-2026-10-27.json](recognition-holdout-2026-10-27.json).

## Limits and follow-up

- The added development corpus was used while improving the implementation and
  cannot be cited as an independent accuracy estimate.
- There is still no large independent collection of real phone photographs with
  blur, glare, sleeves, rotated cards, unusual layouts or non-card inputs. A broad
  real-world accuracy percentage would be unsupported.
- Scores and image similarities are heuristics, not calibrated probabilities.
  Reprints may share artwork. First-edition stamps, holo variants and condition
  are not guaranteed by catalog identification.
- Low-resolution Steelix can be ranked correctly while remaining low confidence;
  the unreadable collector number is not invented.
- Provider outages and missing provider images remain possible; stale cached data
  and manual catalog selection are fallbacks, not evidence of a correct identity.
- Existing stored results are not silently rewritten. Use **OCR opnieuw uitvoeren**
  for an existing scan; new scans use the updated implementation automatically.

The next quality milestone should be a fixed, independently labeled phone-photo
corpus, with separate exact-printing, top-five and false-high-confidence metrics.
Do not tune on that corpus and then call it held-out evidence.

## Reproduction

```powershell
docker compose exec api python -m pytest -q
docker compose exec api python -m tests.benchmark_generalization
docker compose exec api python -m tests.benchmark_holdout
```

The benchmark scripts perform bounded live provider reads and no application DB
writes. `benchmark_generalization` includes the existing ten clean scans, their
ten synthetic distortions, seven user-scan regressions and the added catalog
examples. Unavailable reference images are reported separately, not counted as
successful recognition tests.

Tesseract's thread-limit setting follows its
[official performance guidance](https://tesseract-ocr.github.io/tessdoc/FAQ.html#can-i-increase-speed-of-ocr).
The larger `tessdata_best` model was experimentally compared but was not shipped;
the application continues using the installed English Tesseract model.
