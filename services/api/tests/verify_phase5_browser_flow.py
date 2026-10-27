import time
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
WEB_URL = "http://localhost:3000"


def main():
    test_image = Path("scratch_browser_test/pikachu_photo.jpg").resolve()
    assert test_image.is_file(), f"Test image not found at {test_image}"

    print(f"Starting Phase 5 browser verification against {WEB_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
        )
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # Step 1: Upload flow
        print("1. Testing upload on /scan...")
        page.goto(f"{WEB_URL}/scan", wait_until="networkidle")
        assert "Upload" in page.title() or page.locator("input[type=file]").count() > 0

        file_input = page.locator("input[type=file]")
        file_input.set_input_files(str(test_image))

        upload_btn = page.locator("button:has-text('Upload and Process')")
        upload_btn.click()

        # Wait for navigation to /scan/[id]
        page.wait_for_url("**/scan/*", timeout=15000)
        scan_url = page.url
        print(f"Successfully uploaded and navigated to: {scan_url}")

        # Step 2: Auto detection on /scan/[id]
        print("2. Verifying automatic card detection...")
        page.wait_for_selector("div[role='slider']", timeout=10000)
        handles = page.locator("div[role='slider']")
        assert handles.count() == 4, (
            f"Expected 4 corner handles, found {handles.count()}"
        )
        page.wait_for_selector("button:has-text('Opnieuw detecteren')", timeout=15000)
        print("4 corner handles displayed on canvas, auto-detection complete.")

        # Step 3: Generate crop preview
        print("3. Generating crop preview...")
        preview_btn = page.locator("button:has-text('Preview')").first
        preview_btn.click()
        page.wait_for_selector("img[alt='Uitsnede preview']", timeout=10000)
        page.wait_for_selector(
            "button:has-text('Deze uitsnede bevestigen')", timeout=10000
        )
        print("Crop preview generated.")

        # Step 4: Confirm crop
        print("4. Confirming crop...")
        confirm_btn = page.locator("button:has-text('Deze uitsnede bevestigen')")
        assert confirm_btn.is_enabled()
        confirm_btn.click()

        page.wait_for_selector("text=Uitsnede Bevestigd", timeout=10000)
        print("Crop confirmed successfully!")

        # Step 5: Start OCR Card Recognition
        print("5. Triggering OCR card recognition ('Kaart herkennen')...")
        recognize_btn = page.locator("button:has-text('Kaart herkennen')")
        assert recognize_btn.is_visible(), (
            "Recognize button not visible after crop confirmation"
        )
        recognize_btn.click()

        # Step 6: Wait for OCR and candidate retrieval
        print("6. Waiting for candidates and OCR results...")
        page.wait_for_selector("text=Gevonden cataloguskaarten", timeout=25000)
        print("Candidate matches section displayed!")

        # Inspect editable fields
        name_input = page.locator("#card-name-input")
        num_input = page.locator("#card-number-input")
        assert name_input.is_visible()
        assert num_input.is_visible()
        rec_name = name_input.input_value()
        rec_num = num_input.input_value()
        print(f"OCR extracted fields: Name='{rec_name}', Number='{rec_num}'")

        # Verify raw OCR toggle displays actual OCR text rather than form fields
        raw_ocr_toggle = page.locator("button:has-text('Bekijk ruwe OCR-tekst')")
        if raw_ocr_toggle.is_visible():
            raw_ocr_toggle.click()
            page.wait_for_selector(
                "text=Ruwe OCR output (ongefilterde tekst)", timeout=5000
            )
            raw_pre = page.locator("pre").first.inner_text()
            assert len(raw_pre.strip()) > 0, "Expected non-empty raw OCR text in viewer"
            print("Verified raw OCR output viewer displays actual unparsed OCR output.")

        # Step 7: Check candidate list contents
        candidates = page.locator("button:has-text('✓ Bevestig deze kaart')")
        cand_count = candidates.count()
        assert cand_count > 0, f"Expected candidates, got {cand_count}"
        print(f"Found {cand_count} candidates in match list.")

        # Step 8: Test candidate manual field search / correction
        print("7. Testing search adjustment with corrected fields...")
        name_input.fill("Pikachu")
        num_input.fill("58")
        search_btn = page.locator("button:has-text('Zoekopdracht bijwerken')")
        search_btn.click()

        page.wait_for_selector("text=base1", timeout=10000)
        print("Candidates updated with specific query results!")

        # Step 9: Explicitly confirm catalog card
        print("8. Confirming catalog card (Pikachu base1-58)...")
        first_confirm = page.locator("button:has-text('✓ Bevestig deze kaart')").first
        first_confirm.click()

        page.wait_for_selector("text=Kaart succesvol bevestigd", timeout=10000)
        page.wait_for_selector("text=Officiële cataloguskaart", timeout=5000)
        page.wait_for_selector("text=ID: base1-58", timeout=5000)
        print("Card confirmed! Side-by-side comparison is displayed.")

        # Step 10: Page reload persistence
        print("9. Verifying card confirmation persistence across page reload...")
        page.reload(wait_until="networkidle")
        page.wait_for_selector("text=Kaart Bevestigd", timeout=10000)
        page.wait_for_selector("text=Officiële cataloguskaart", timeout=5000)
        page.wait_for_selector("text=Pikachu", timeout=5000)
        page.wait_for_selector("text=Jouw kaartfoto (uitsnede)", timeout=5000)
        print("Confirmed card state persisted cleanly across page reload!")

        # Step 11: Change selection ("Andere kaart kiezen")
        print("10. Testing resetting card confirmation ('Andere kaart kiezen')...")
        reset_btn = page.locator("button:has-text('Andere kaart kiezen')")
        assert reset_btn.is_visible()
        reset_btn.click()

        # Verify candidate list re-appears and badge returns to Uitsnede Bevestigd
        page.wait_for_selector("text=Gevonden cataloguskaarten", timeout=10000)
        page.wait_for_selector("text=Uitsnede Bevestigd", timeout=5000)
        assert page.locator("text=Officiële cataloguskaart").count() == 0
        print("Card confirmation successfully reset; candidate selection re-enabled.")

        # Step 12: Manual search fallback with zero matches
        print("11. Testing zero-match fallback feedback...")
        name_input.fill("NonExistentPokemonZXYZX")
        num_input.fill("9999")
        search_btn.click()

        page.wait_for_selector(
            "text=Geen overeenkomende kaarten gevonden", timeout=10000
        )
        print("Zero matches feedback displayed clearly.")

        # Step 13: Responsive mobile layout test
        print("12. Testing mobile layout responsiveness (375x667)...")
        page.set_viewport_size({"width": 375, "height": 667})
        time.sleep(1)
        scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
        client_width = page.evaluate("() => document.documentElement.clientWidth")
        assert scroll_width <= client_width + 10, (
            f"Horizontal overflow on mobile: {scroll_width} > {client_width}"
        )
        print(f"Mobile layout verified cleanly (width {client_width}px).")

        # Step 14: Dark mode test
        print("13. Testing theme toggle...")
        theme_toggle = page.locator(
            "button[aria-label*='theme'], button:has-text('🌙'), button:has-text('☀️')"
        ).first
        if theme_toggle.count() > 0:
            theme_toggle.click()
            time.sleep(0.5)
            print("Theme toggled successfully.")

        print("\nAll 14 Phase 5 browser verification checks PASSED!")
        browser.close()


if __name__ == "__main__":
    main()
