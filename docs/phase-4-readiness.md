# Fase 4: Kaartdetectie, uitsnijden en perspectiefcorrectie

Gecontroleerd op 25 oktober 2026. Conclusie: Fase 4 is succesvol geïmplementeerd, geverifieerd en gereed voor Fase 5 (OCR en kaartherkenning).

---

## 1. Wat is geïmplementeerd

### Automatische kaartdetectie (`card_detector.py`)
- Verwerkt de bestaande genormaliseerde scan via het scan-ID met OpenCV (`opencv-python-headless`).
- Meervoudige randdetectiestrategieën (Canny met mediaandrempels, adaptieve Gaussische drempels, Otsu-thresholding en morfologische sluiting).
- Contouren worden benaderd met Douglas-Peucker (`cv2.approxPolyDP`) om convexe vierhoeken te vinden.
- Kandidaten worden geëvalueerd en gescoord op basis van:
  - Verhouding ten opzichte van de standaard Pokémon-kaartmaat (63 mm × 88 mm, verhouding ~0,7159).
  - Vloeiend oppervlak (15% tot 85% van het actieve beeldframe).
  - Parallellisme van tegenoverliggende zijden.
  - Nabijheid tot het beeldcentrum.
- Detectiefalen is een normale uitkomst: wanneer er geen overtuigende kandidaat is, wordt `detected: false` geretourneerd met een duidelijke toelichting en een bruikbare standaardselectie (12% inset).
- De heuristische kwaliteitsscore wordt expliciet als ruwe score gepresenteerd en niet als gekalibreerde waarschijnlijkheid.

### Coördinatencontract & Server-side validatie
- **Coördinatenstelsel**: Genormaliseerde coördinaten `[0.0, 1.0]` voor `x` en `y`, gerelateerd aan de opgeslagen genormaliseerde afbeelding.
- **Hoekvolgorde**: `top_left`, `top_right`, `bottom_right`, `bottom_left` (met de klok mee).
- **Server-side validatie (`validate_corners`)**:
  - Precies 4 punten (`Point(x, y)`).
  - Eindige getallen binnen `[0.0, 1.0]`.
  - Geen overlappende of te dicht bij elkaar liggende punten (minimale afstand 1%).
  - Geen kruisende zijden (geen "bow-tie" vorm).
  - Strikt convexe vierhoek (geen inhammen of reflexhoeken).
  - Minimaal oppervlak (Shoelace-oppervlakte minimaal 0,5% van het beeld).

### Uitsnijden & Perspectiefcorrectie (`crop_service.py`)
- Voert een perspectieftransformatie (`cv2.getPerspectiveTransform` en `cv2.warpPerspective`) uit op de originele genormaliseerde bronafbeelding.
- Behoudt de originele bronafbeelding volledig intact.
- Voorkomt onnodig opblazen van kleine selecties en limiteert de maximale uitvoerzijde tot 2000 px.
- Ondersteunt expliciet 90° draaien (0°, 90°, 180°, 270°) om liggende of ondersteboven gefotografeerde kaarten te corrigeren.
- Genereert elke uitsnede naar een unieke bestandsnaam (`{scan_id}_crop_{uuid_hex}.jpg`).
- Behoudt een eerdere geldige uitsnede op schijf intact totdat de databasetransactie voor de nieuwe uitsnede succesvol is vastgelegd. Bij een transactiefout wordt de niet-gepubliceerde kandidaat direct opgeruimd en blijft de eerdere uitsnede onaangetast.
- Oude/vervangen uitsneden worden pas veilig opgeruimd nadat de nieuwe versie succesvol in de database is gecommitteerd.

### Frontendinteractie & Workflow (`CornerSelector.tsx` & `/scan/[id]`)
- **Interactieve hoekenselectie**:
  - SVG-polygoonoverlay over de bronafbeelding zonder letterboxing-afwijkingen.
  - 4 interactieve handvatten (LB, RB, RO, LO) met pointer capture voor muis en touch.
  - Toegankelijke toetsenbordbediening (Tab en pijltjestoetsen, Shift voor grotere stappen).
  - Realtime visuele waarschuwing bij concave of kruisende hoeken.
- **Race Condition & Identity Tracking**:
  - Request identity en revisietellers (`useRef`: `selectionRevisionRef`, `activeDetectionIdRef`, `activePreviewIdRef`).
  - Late detectieresultaten of verouderde previews overschrijven nooit handmatige aanpassingen.
  - Handmatige bewerkingen tijdens een lopend previewverzoek wissen de `hasUnsavedChanges`-status niet voortijdig.
- **Preview & Stale-state detectie**:
  - Preview van de rechtgetrokken kaartuitsnede.
  - Zodra de hoeken of rotatie na een preview worden aangepast, wordt de preview gemarkeerd als verouderd en wordt de bevestigingsknop geblokkeerd tot er een nieuwe preview is gegenereerd.
- **Bevestigde toestand**:
  - Na bevestiging toont de pagina de bevestigde toestand met groene badge, afmetingen, bestandsgrootte en rotatie.
  - Blijft persistent bewaard na herladen van de browser (`crop_status: "confirmed"`).
  - Biedt een knop "Hoeken opnieuw aanpassen" om correcties mogelijk te houden.

### Concurrency & Data-integriteit
- **Atomaire voorwaardelijke updates**:
  - Zowel uitsnijden (`/crop`) als bevestigen (`/confirm`) gebruiken database-updates met `WHERE crop_version = :expected_version AND expires_at > :now`.
  - Conflicterende of verouderde verzoeken worden direct afgewezen met HTTP 409 (`STALE_VERSION` of `CONFIRMED_CONFLICT`) zonder de winnende uitsnede of metadata te overschrijven.
  - Bevestiging verhoogt de versieteller, waardoor een uitsnijdverzoek dat vóór bevestiging is gestart niet stilletjes een reeds bevestigde kaart kan overschrijven.
- **Retentie en hernieuwde vervalcontrole**:
  - Verval (`expires_at`) wordt transactioneel gecontroleerd op het moment van resultaatpublicatie voor detectie, uitsnijden en bevestigen.
  - Verlopen scans leveren HTTP 404 (`SCAN_EXPIRED`) op, gegenereerde kandidaatbestanden worden direct gewist en scans worden nooit per ongeluk heropend of verlengd.

### Retentie & Cleanup
- Uitgebreide `cleanup_scans.py`:
  - Verwijdert zowel de bronafbeelding als alle unieke afgeleide uitsneden (`{scan_id}_crop_{uuid}.jpg` en `{scan_id}_crop.jpg`) bij verlopen scans.
  - Orphan-cleanup beschermt actieve scans en recente in-progress kandidaten (< 24 uur) en verwijdert uitsluitend ongekoppelde bestanden ouder dan 24 uur.

---

## 2. API- en databasewijzigingen

### Database (Alembic migratie `0004_add_scan_crop_fields.py`)
Toegevoegde kolommen aan tabel `scans`:
- `crop_status`: `VARCHAR(32)` (`none`, `detected`, `preview`, `confirmed`), default `"none"`.
- `corners`: `JSON` nullable (bevat `top_left`, `top_right`, `bottom_right`, `bottom_left`).
- `rotation`: `INTEGER`, default `0`.
- `crop_path`: `VARCHAR(255)` nullable (`{scan_id}_crop.jpg`).
- `crop_width`: `INTEGER` nullable.
- `crop_height`: `INTEGER` nullable.
- `crop_file_size`: `INTEGER` nullable.
- `crop_version`: `INTEGER`, default `0` (versieteller ter bescherming tegen race conditions).
- `confirmed_at`: `DATETIME` nullable.

### API Endpoints
- `POST /api/v1/scans/{id}/detect`: Automatische kaartdetectie op de scan.
- `POST /api/v1/scans/{id}/crop`: Genereert een uitsnede op basis van 4 hoeken, rotatiehoek en verplichte `expected_version` (niet-negatief geheel getal, `ge=0`); genereert unieke bestandsnaam `{scan_id}_crop_{uuid}.jpg` en verhoogt `crop_version`.
- `POST /api/v1/scans/{id}/confirm`: Bevestigt de huidige preview; valideert vooraf het bestaan van het fysieke afbeeldingsbestand op schijf (voorkomt spookbevestigingen); bindt bevestiging atomair aan exact hetzelfde `crop_path` en verwachte `crop_version` via voorwaardelijke SQL update en verhoogt `crop_version` ter verzegeling van de bevestigde staat.
- `GET /api/v1/scans/{id}/crop/image`: Retourneert de uitgesneden JPEG met `Cache-Control: no-store` en optionele versieparameter `?v=...`.
- `GET /api/v1/scans/{id}`: Bevat volledige uitsnede- en bevestigingsmetadata.

---

## 3. Uitgevoerde verificaties en tests

### Geautomatiseerde Backend Tests (126 tests)
- **Doelgerichte regressietests (Reparatieslag Fase 4)**:
  - *Fysieke validatie van crop-bestand vóór bevestiging*: Het endpoint `confirm_scan_crop` valideert vóór elke databasemutatie het pad en de fysieke aanwezigheid van het kandidaatbestand op schijf. Ontbrekende bestanden worden afgewezen met HTTP 404 (`CROP_NOT_FOUND`) zonder dat `crop_status`, `crop_version` of `confirmed_at` worden aangepast.
  - *Binding aan exact hetzelfde crop-pad bij bevestiging*: De voorwaardelijke SQL UPDATE bindt atomair aan `crop_path == candidate_crop_path` én `crop_version == expected_version`. Hierdoor kan een gelijktijdige uitsnijding die een nieuw bestand aanmaakt nooit per ongeluk leiden tot de bevestiging van de verkeerde uitsnede.
  - *Verplichte `expected_version`*: `expected_version` is een strikt verplicht niet-negatief geheel getal (`ge=0`). Ontbrekende, null, negatieve of niet-numerieke waarden worden direct afgewezen met HTTP 422. De server-fallback naar de actuele versie is verwijderd.
  - *Echte gelijktijdige verzoeken (MariaDB Concurrency Suite)*:
    - Dedicated testsuite `test_concurrency_mariadb.py` uitgevoerd tegen een geïsoleerde MariaDB testdatabase (`tcg_test`).
    - *Test A (Crop vs Crop)*: Twee gelijktijdige crop-verzoeken overlappen op worker threads met een `threading.Barrier(2)` vóór de databasecommit. Exact één verzoek slaagt (HTTP 200) en het conflicterende verzoek wordt afgewezen met HTTP 409 (`STALE_VERSION`); het verliezende kandidaatbestand wordt direct ontkoppeld en verwijderd.
    - *Test B (Crop vs Bevestiging)*: Een gepauzeerd crop-verzoek kan een tussentijds voltooide bevestiging niet overschrijven (HTTP 409).
    - *Test C (Bevestiging vs Vervanging)*: Een vertraagde bevestiging die vóór de DB-update pauzeert terwijl een vervangende uitsnede committeert, wordt afgewezen met HTTP 409 (`STALE_VERSION`) en bevestigt de nieuwere uitsnede niet.
  - *Databasefout bij publicatie*: Falende commit behoudt de vorige geldige uitsnede en metadata ongewijzigd en ruimt de ongepubliceerde kandidaat netjes op schijf op.
  - *Hernieuwde vervalcontrole*: Een scan die tijdens beeldverwerking of detectie verloopt wordt geweigerd met HTTP 404 (`SCAN_EXPIRED`), kandidaatbestanden worden direct gewist en de scan wordt niet heropend.
  - *Orphan cleanup van unieke bestandsnamen*: Unieke crop-bestanden van actieve scans (`{scan_id}_crop_{uuid}.jpg`) en recente in-progress kandidaten (< 24 uur) blijven behouden; achtergebleven weesbestanden (> 24 uur) worden veilig verwijderd.
- **Bestaande tests**:
  - Synthetische kaarten met bekende hoeken en oriëntaties (recht en geroteerd).
  - Afbeeldingen zonder kaart (bevestigt `detected=false` en fallback hoeken).
  - Geometrische validatie: ongeldige waarden, NaN/oneindig, buiten bereik, overlappende punten, kruisende zijden (bow-tie), concave polygonen en te kleine oppervlaktes.
  - Perspectiefcorrectie, rotaties (0°, 90°, 180°, 270°) en unieke bestandsgeneratie.
  - Verlopen en ontbrekende scans (HTTP 404).
  - Cleanup van verlopen scans (verwijdert bron en uitsnede).
- **Resultaten**:
  - In Docker container tegen MariaDB `tcg_test`: **126 geslaagd** in 3,17s.
  - Op host tegen SQLite fallback: **123 geslaagd, 3 overgeslagen** (de 3 MariaDB-concurrency tests worden netjes overgeslagen op SQLite).

### Codekwaliteit & Builds
- **Ruff**: Linting en formatting 100% geslaagd (0 fouten).
- **TypeScript**: `tsc --noEmit` 100% geslaagd (0 typesfouten).
- **ESLint**: Next.js ESLint 100% geslaagd (0 waarschuwingen).
- **Prettier**: Code style check 100% geslaagd.
- **Next.js Productiebuild**: Standalone build succesvol gebouwd en geoptimaliseerd.
- **Docker Compose**: Zowel `docker-compose.yml` als `docker-compose.dev.yml` valideren; Docker images voor `api`, `cleanup` en `web` succesvol gebouwd en actief.

### Browserflow verificatie (Playwright & Google Chrome)
Uitgevoerd via `services/api/tests/verify_browser_flow.py`:
1. Upload van kaartfoto via `/scan` met automatische navigatie naar `/scan/[id]`.
2. Automatische detectie met weergave van 4 hoeken.
3. Genereren van initiële rechte preview.
4. Handmatig verplaatsen van hoeken via het toetsenbord; controle dat stale-preview waarschuwing verschijnt en preview wordt vernieuwd.
5. Roterend corrigeren via 90° draaiknop.
6. Bevestigen van de uitsnede.
7. Herladen van de browserpagina; bevestiging blijft behouden en wordt direct getoond.
8. Upload van een foto zonder kaart; bevestiging dat detectiefout netjes wordt gemeld, standaardselectie verschijnt en handmatige uitsnede alsnog succesvol kan worden bevestigd.
9. Mobiele schermweergave (375 × 667 px) gecontroleerd: geen horizontale overflow.
10. Dark/light mode omschakeling gecontroleerd.

---

## 4. Reële verwachtingen en beperkingen van detectie & uitsnijden

1. **Heuristische detectie vereist visuele controle**: Automatische contour- en randdetectie is een heuristiek. Hoewel synthetische kaarten op een donkere achtergrond betrouwbaar worden gevonden, kunnen echte foto's met reflecties op sleeves, patronen op speelmatten of zwak randcontrast een afwijkende of onvolledige contour opleveren. De gebruiker dient het resultaat altijd visueel te controleren in de preview.
2. **Kwaliteit van rechtzetten hangt af van geselecteerde hoeken**: De perspectieftransformatie projecteert wiskundig de vier gekozen hoeken naar een rechthoek. Als de hoeken niet exact op de kaarthoeken zijn geplaatst, kan de uitsnede lichte trapezium- of perspectiefvervorming bevatten of een randje achtergrond meenemen.
3. **Tekstoriëntatie**: Geometrische contourdetectie detecteert de rechthoekige vorm van de kaart, maar kan niet bepalen of een kaart ondersteboven of 90° gekanteld gefotografeerd is. De 90°-draaiknoppen zijn bedoeld om dit visueel te corrigeren.
4. **Kwaliteitsscore**: De geretourneerde score is een geometrische heuristiek (verhouding, oppervlakte, parallellisme, positie) en geen gekalibreerde kans op correcte detectie.

---

## 5. Overdracht naar Fase 5 (OCR & Kaartherkenning)

Gereed voor de start van Fase 5:
- De bevestigde uitsnede is direct beschikbaar via het API-endpoint:
  `GET /api/v1/scans/{id}/crop/image`
- De status kan worden gecontroleerd via:
  `GET /api/v1/scans/{id}` (`crop_status === "confirmed"`)
- De uitsnede representeert de door de gebruiker gecontroleerde en bevestigde rechthoekige projectie, geschikt als invoer voor OCR-tekstextractie en catalogusmatching.
