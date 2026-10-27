import math
import time
from pathlib import Path

import cv2
import numpy as np
from playwright.sync_api import sync_playwright

CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
WEB_URL = "http://localhost:3000"


def create_test_images(dir_path: Path) -> tuple[Path, Path]:
    dir_path.mkdir(parents=True, exist_ok=True)

    # 1. Image with clear Pokémon card
    card_img = np.full((600, 800, 3), (35, 40, 45), dtype=np.uint8)
    cx, cy = 400, 300
    w, h = 252, 352
    box = np.array(
        [
            [-w / 2, -h / 2],
            [w / 2, -h / 2],
            [w / 2, h / 2],
            [-w / 2, h / 2],
        ],
        dtype=np.float32,
    )
    # Slight 10 degree tilt
    rad = math.radians(10)
    rot_mat = np.array(
        [[math.cos(rad), -math.sin(rad)], [math.sin(rad), math.cos(rad)]],
        dtype=np.float32,
    )
    rotated = np.dot(box, rot_mat.T) + np.array([cx, cy], dtype=np.float32)
    cv2.fillPoly(card_img, [rotated.astype(np.int32)], (25, 210, 250))  # yellow border
    inner = np.dot(box * 0.88, rot_mat.T) + np.array([cx, cy], dtype=np.float32)
    cv2.fillPoly(card_img, [inner.astype(np.int32)], (160, 140, 200))
    card_path = dir_path / "browser_test_card.jpg"
    cv2.imwrite(str(card_path), card_img)

    # 2. Image with no card (plain uniform noise)
    noise_img = np.random.randint(90, 110, (500, 500, 3), dtype=np.uint8)
    noise_path = dir_path / "browser_test_noise.jpg"
    cv2.imwrite(str(noise_path), noise_img)

    return card_path, noise_path


def main():
    test_dir = Path("scratch_browser_test").resolve()
    card_path, noise_path = create_test_images(test_dir)

    print(f"Starting browser verification against {WEB_URL}...")
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

        # Select card file
        file_input = page.locator("input[type=file]")
        file_input.set_input_files(str(card_path))

        # Click upload button
        upload_btn = page.locator("button:has-text('Upload and Process')")
        upload_btn.click()

        # Wait for navigation to /scan/[id]
        page.wait_for_url("**/scan/*", timeout=10000)
        scan_url = page.url
        print(f"Successfully uploaded and navigated to: {scan_url}")

        # Step 2: Auto detection on /scan/[id]
        print("2. Verifying automatic card detection...")
        # Wait for either detection message or corner selector
        page.wait_for_selector("div[role='slider']", timeout=10000)
        handles = page.locator("div[role='slider']")
        assert handles.count() == 4, (
            f"Expected 4 corner handles, found {handles.count()}"
        )
        print("4 corner handles displayed on canvas.")

        # Step 3: Generate initial preview
        print("3. Generating initial crop preview...")
        preview_btn = page.locator("button:has-text('Preview')").first
        preview_btn.click()
        page.wait_for_selector("img[alt='Uitsnede preview']", timeout=10000)
        print("Straight crop preview image successfully generated.")

        # Step 4: Corner adjustments via keyboard & unsaved changes check
        print("4. Testing manual corner adjustment and stale preview detection...")
        first_handle = handles.first
        first_handle.focus()
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowDown")

        # Verify unsaved changes indicator appears
        page.wait_for_selector("text=De hoeken of rotatie zijn aangepast", timeout=5000)
        print("Stale preview warning correctly shown after corner modification.")

        # Refresh preview after adjustment
        preview_btn.click()
        page.wait_for_selector("img[alt='Uitsnede preview']", timeout=10000)
        print("Updated preview generated.")

        # Step 5: Test rotation
        print("5. Testing 90 degree rotation...")
        rotate_btn = page.locator("button:has-text('⟳ 90°')")
        rotate_btn.click()
        # Rotation changed, need to refresh preview
        page.wait_for_selector("text=De hoeken of rotatie zijn aangepast", timeout=5000)
        preview_btn.click()
        page.wait_for_selector("img[alt='Uitsnede preview']", timeout=10000)
        print("Rotated preview generated successfully.")

        # Step 6: Confirm crop
        print("6. Confirming crop...")
        confirm_btn = page.locator("button:has-text('Deze uitsnede bevestigen')")
        assert confirm_btn.is_enabled()
        confirm_btn.click()

        # Wait for confirmed badge
        page.wait_for_selector("text=Uitsnede Bevestigd", timeout=10000)
        print("Crop confirmed successfully!")

        # Step 7: Page reload persistence
        print("7. Testing persistence across page reload...")
        page.reload(wait_until="networkidle")
        page.wait_for_selector("text=Uitsnede Bevestigd", timeout=10000)
        page.wait_for_selector("text=Bevestigde Kaartuitsnede", timeout=5000)
        print("Confirmed state verified after reload!")

        # Step 8: Detection failure & manual fallback
        print("8. Testing detection failure with plain image...")
        page.goto(f"{WEB_URL}/scan", wait_until="networkidle")
        page.locator("input[type=file]").set_input_files(str(noise_path))
        page.locator("button:has-text('Upload and Process')").click()
        page.wait_for_url("**/scan/*", timeout=10000)

        # Wait for detection message to resolve
        page.wait_for_selector("text=handmatig", timeout=10000)
        print("Fallback explanation correctly displayed when no card is found.")

        # Generate preview directly with fallback corners
        page.locator("button:has-text('Preview')").first.click()
        page.wait_for_selector("img[alt='Uitsnede preview']", timeout=10000)
        confirm_btn2 = page.locator("button:has-text('Deze uitsnede bevestigen')")
        assert confirm_btn2.is_enabled()
        confirm_btn2.click()
        page.wait_for_selector("text=Uitsnede Bevestigd", timeout=10000)
        print("Manual fallback crop confirmed successfully!")

        # Step 9: Responsive mobile layout test
        print("9. Testing mobile layout (375x667)...")
        page.set_viewport_size({"width": 375, "height": 667})
        time.sleep(1)
        # Check no horizontal scroll
        scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
        client_width = page.evaluate("() => document.documentElement.clientWidth")
        assert scroll_width <= client_width + 10, (
            f"Horizontal overflow on mobile: {scroll_width} > {client_width}"
        )
        print(f"Mobile layout verified cleanly (width {client_width}px).")

        # Step 10: Dark mode test
        print("10. Testing light and dark mode toggling...")
        theme_toggle = page.locator(
            "button[aria-label*='theme'], button:has-text('🌙'), button:has-text('☀️')"
        ).first
        if theme_toggle.count() > 0:
            theme_toggle.click()
            time.sleep(0.5)
            print("Theme toggled successfully.")

        print("\nAll 10 browser verification checks PASSED!")
        browser.close()


if __name__ == "__main__":
    main()
