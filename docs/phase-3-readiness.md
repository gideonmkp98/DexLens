# Fase 3: controle en overdracht

Gecontroleerd op 25 oktober 2026. Conclusie: de uploadbasis is geschikt om lokaal door te ontwikkelen naar fase 4.

## Gecontroleerde workflow

- Browser: bestand kiezen, preview bekijken, verwijderen, hetzelfde bestand opnieuw kiezen, uploaden en resultaat bekijken.
- Browser: een tekstbestand met `.png`-extensie uploaden geeft een begrijpelijke validatiefout; vervangen door een geldige afbeelding en opnieuw uploaden werkt.
- Het resultaat toont de daadwerkelijk opgeslagen JPEG van de API, met de verwachte afmetingen (1200 × 1800), bestandsgrootte en vervaltijd.
- Herladen en herstarten van de API behouden de scan in MariaDB en het gedeelde uploadvolume.
- Een ongeldige scanlink toont de pagina voor een ontbrekende/verlopen scan.
- De resultaatpagina is visueel gecontroleerd in de smalle browserweergave. Geen fysieke telefoon/camera of drag-and-drop getest.
- Live API-controle: health, sets, setdetail, globale zoekopdracht en kaartdetail retourneren HTTP 200. Pikachu geeft 230 resultaten bij een pagina van 2 kaarten.

## Hersteld

- CORS wordt ook toegepast op vroegtijdige 413-responses, zodat de browser de echte uploadfout kan tonen.
- Afgebroken multipartverwerking gebruikt het exceptiontype waarmee de parser tijdelijke bestanden sluit.
- Opslagfouten geven een gecontroleerde `STORAGE_ERROR` (500), in plaats van een ongeldige-afbeeldingmelding of ongecontroleerde fout.
- Tijdelijke uploadbestanden worden ook bij fouten opgeruimd.
- Databasewerk voor uploads draait buiten de async eventloop. Een overbodige refresh na commit is verwijderd: een fout in die extra leesactie kon een al opgeslagen afbeelding verwijderen.
- Meerdere bestanden in één API-aanroep worden expliciet geweigerd.
- Scanmetadata heeft `Cache-Control: no-store`, net als de afbeelding.
- SQLite-tests delen nu correct één in-memory database over testthreads. Niet-SQLite testdatabases moeten op `_test` eindigen.
- De scan-ID kan afbreken op smalle schermen.

## Opruiming

Beide Compose-configuraties bevatten een `cleanup` service. Die gebruikt dezelfde database en hetzelfde uploadvolume als de API, start na de API-healthcheck en controleert ieder uur:

1. Verlopen scans: afbeelding verwijderen, daarna databasevermelding verwijderen. Bij een verwijderfout blijft de vermelding bestaan voor een volgende poging.
2. Achtergebleven bestanden: uitsluitend herkende app-bestandsnamen zonder databasereferentie, ouder dan minimaal 24 uur of de langere ingestelde bewaartermijn. Recente bestanden, gekoppelde afbeeldingen, symlinks en onbekende namen blijven staan.

Toegang stopt direct op de vervaltijd; fysieke verwijdering volgt normaal binnen één uur. De eerste uitvoering is gecontroleerd in de servicelog. De uurlijkse timer is niet een uur lang afgewacht.

## Verificatie

- 92 backendtests geslaagd met een expliciete SQLite in-memory testdatabase.
- Tests dekken onder andere JPEG/PNG/WebP, EXIF-rotatie, transparantie, kleurconversie, verkleinen, metadata verwijderen, animaties, corruptie, pixel- en uploadlimieten, verlopen scans, ontbrekende bestanden, database-/schijffouten en veilige opruiming.
- Ruff lint en formatter: geslaagd.
- Frontend typecheck, ESLint, Prettier en productiebuild: geslaagd.
- Dockerimages gebouwd; API en MariaDB healthy; frontend en cleanup draaien.
- Beide Compose-configuraties valideren; MariaDB staat op Alembic `0003 (head)`.
- De testsuite heeft één bestaande deprecation warning rond Starlette/httpx; geen falende tests.

## Grens van deze fase

Deze controle bevestigt uploaden, normaliseren, bewaren, teruglezen en opruimen. Kaartdetectie, perspectiefcorrectie, OCR en herkenning zijn nog niet aanwezig. Gebruik in de volgende fase het bestaande scan-ID en de genormaliseerde afbeelding als invoer. Bepaal eerst of kaartuitsnijden/rechtzetten vóór OCR onderdeel van die fase wordt; een succesvolle upload betekent nog niet dat de kaart recht in beeld staat.

De app blijft een lokale ontwikkelversie: scanlinks hebben geen gebruikersauthenticatie of eigendomscontrole. Voor publieke beschikbaarheid zijn die toegangsregels en limieten op uploadverkeer nog nodig. Er is geen belastingtest of fysieke mobiele cameratest uitgevoerd.

Wijzigingen zijn lokaal aangebracht en niet gecommit of gepusht.
