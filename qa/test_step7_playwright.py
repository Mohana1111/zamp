"""
Step 7: Playwright Headless Browser Test.
- Loads http://127.0.0.1:8080/
- Logs in as admin_1 / pass@admin if required
- Verifies dashboard and captures qa/screens/01_dashboard.png
- Triggers sample invoice analysis or uploads sample
- Navigates to Invoices page and captures qa/screens/02_invoices.png
- Opens Invoice Detail Drawer and captures qa/screens/03_detail_drawer.png
- Records console errors, warnings, and visual defects
"""

import sys
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENS_DIR = REPO_ROOT / "qa" / "screens"
SCREENS_DIR.mkdir(parents=True, exist_ok=True)

def run_browser_test():
    console_logs = []
    page_errors = []
    failed_requests = []

    print("=== Step 7: Starting Playwright Headless Browser Test ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Monitor console and errors
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url}: {req.failure}"))

        print("Navigating to http://127.0.0.1:8080/...")
        page.goto("http://127.0.0.1:8080/", wait_until="networkidle", timeout=30000)

        # 1. Check if auth view is shown
        if page.locator("input[placeholder='admin_1']").is_visible():
            print("Auth view detected. Logging in as admin_1...")
            page.fill("input[placeholder='admin_1']", "admin_1")
            page.fill("input[type='password']", "pass@admin")
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle")
            time.sleep(1.5)

        # 2. Verify on Dashboard
        print("Checking Dashboard page...")
        page.wait_for_selector("text=Invoices Processed", timeout=10000)
        dash_shot = SCREENS_DIR / "01_dashboard.png"
        page.screenshot(path=str(dash_shot), full_page=False)
        print(f"  [SAVED] Dashboard screenshot: {dash_shot}")

        # 3. Trigger a sample invoice run if button exists
        sample_btn = page.locator("button:has-text('Try a sample invoice')")
        if sample_btn.is_visible():
            print("Clicking 'Try a sample invoice'...")
            sample_btn.click()
            # Wait for processing
            time.sleep(4.0)
            page.wait_for_load_state("networkidle")

        # Re-take dashboard screenshot with runs
        page.screenshot(path=str(dash_shot), full_page=False)

        # 4. Navigate to Invoices tab
        print("Navigating to Invoices tab...")
        invoices_nav = page.locator("button:has-text('Invoices')").first
        invoices_nav.click()
        time.sleep(1.5)
        page.wait_for_load_state("networkidle")

        inv_shot = SCREENS_DIR / "02_invoices.png"
        page.screenshot(path=str(inv_shot), full_page=False)
        print(f"  [SAVED] Invoices table screenshot: {inv_shot}")

        # 5. Click first invoice row to open detail drawer
        print("Clicking first invoice row to open detail drawer...")
        first_row = page.locator("tbody tr").first
        if first_row.is_visible():
            first_row.click()
            time.sleep(2.0)
            drawer_shot = SCREENS_DIR / "03_detail_drawer.png"
            page.screenshot(path=str(drawer_shot), full_page=False)
            print(f"  [SAVED] Detail drawer screenshot: {drawer_shot}")
        else:
            print("Warning: No invoice rows found to click.")

        browser.close()

    print("\n--- Console and Error Audit ---")
    console_errors = [c for c in console_logs if "[error]" in c]
    console_warns = [c for c in console_logs if "[warning]" in c]

    print(f"Total Console Messages: {len(console_logs)}")
    print(f"Console Warnings: {len(console_warns)}")
    for w in console_warns[:5]:
        print(f"  WARN: {w}")

    print(f"Console Errors: {len(console_errors)}")
    for e in console_errors:
        print(f"  ERR: {e}")

    print(f"Page Errors: {len(page_errors)}")
    for pe in page_errors:
        print(f"  PAGE_ERR: {pe}")

    print(f"Failed Network Requests: {len(failed_requests)}")
    for fr in failed_requests:
        print(f"  FAIL_REQ: {fr}")

    # Write findings to json
    audit_data = {
        "console_errors": console_errors,
        "console_warnings": console_warns,
        "page_errors": page_errors,
        "failed_requests": failed_requests,
        "screenshots": [
            str(SCREENS_DIR / "01_dashboard.png"),
            str(SCREENS_DIR / "02_invoices.png"),
            str(SCREENS_DIR / "03_detail_drawer.png"),
        ]
    }
    with open(REPO_ROOT / "qa" / "browser_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2)

    return len(console_errors) == 0 and len(page_errors) == 0

if __name__ == "__main__":
    success = run_browser_test()
    sys.exit(0 if success else 1)
