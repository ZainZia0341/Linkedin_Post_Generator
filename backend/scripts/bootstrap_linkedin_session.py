from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import LINKEDIN_BROWSER_PROFILE_DIR


def main() -> None:
    LINKEDIN_BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print("Opening an isolated Playwright Chromium profile for LinkedIn.")
    print("Use a BURNER LinkedIn account only. Do not use your personal account.")
    print("Log in manually and solve any LinkedIn verification screen yourself.")
    print("This script does not read or store your LinkedIn password.")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(LINKEDIN_BROWSER_PROFILE_DIR),
            headless=False,
            viewport={"width": 1365, "height": 900},
        )
        page = context.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        print()
        print("A browser window has opened.")
        print("After you land on the LinkedIn feed, return here and press Enter.")
        input("Press Enter after manual burner login is complete... ")

        context.close()

    print("Session saved to:", LINKEDIN_BROWSER_PROFILE_DIR)
    print("You can now run the app in headless burner mode.")


if __name__ == "__main__":
    main()
