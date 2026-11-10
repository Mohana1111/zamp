"""
Step 3: Edge cases test suite.
Tests:
1. Empty file (0 bytes, empty.txt)
2. 0-byte PDF (empty.pdf)
3. Corrupt PDF (corrupt.pdf)
4. Huge image (large generated image ~10MB)
5. Non-invoice PDF ('ASA Case Study - Candidate Guide.pdf' from repo root)
6. Wrong extension (.exe, .zip, .xyz)
7. Unicode filename (Rechnung_Müller_Überweisung_€_100_₹_日本語.pdf)
8. Same file uploaded twice concurrently

Requirements: App must return a clean result/error, NEVER a 500 stack trace or hang.
"""

import sys
import io
import time
import concurrent.futures
from pathlib import Path
from PIL import Image
import httpx

BASE_URL = "http://127.0.0.1:8080"
REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "backend" / "data" / "sample_invoices"

def test_edge_cases():
    results = {}
    print("=== Step 3: Edge Cases Testing ===")

    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        # Reset state first
        client.post("/api/reset")

        # -------------------------------------------------------------------
        # 1. Empty file (0 bytes, empty.txt)
        # -------------------------------------------------------------------
        print("\n--- 1. Testing Empty File (0 bytes, empty.txt) ---")
        try:
            res = client.post(
                "/api/runs/upload",
                files=[("files", ("empty.txt", b"", "text/plain"))],
            )
            print(f"Status: {res.status_code}, Body: {res.text[:200]}")
            results["empty_txt"] = {
                "status": res.status_code,
                "clean": res.status_code in (200, 400, 422),
                "is_500": res.status_code >= 500,
                "body": res.text[:200],
            }
        except Exception as e:
            results["empty_txt"] = {"error": str(e), "clean": False, "is_500": True}

        # -------------------------------------------------------------------
        # 2. 0-byte PDF (empty.pdf)
        # -------------------------------------------------------------------
        print("\n--- 2. Testing 0-byte PDF (empty.pdf) ---")
        try:
            res = client.post(
                "/api/runs/upload",
                files=[("files", ("empty.pdf", b"", "application/pdf"))],
            )
            print(f"Status: {res.status_code}, Body: {res.text[:200]}")
            results["empty_pdf"] = {
                "status": res.status_code,
                "clean": res.status_code in (200, 400, 422),
                "is_500": res.status_code >= 500,
                "body": res.text[:200],
            }
        except Exception as e:
            results["empty_pdf"] = {"error": str(e), "clean": False, "is_500": True}

        # -------------------------------------------------------------------
        # 3. Corrupt PDF
        # -------------------------------------------------------------------
        print("\n--- 3. Testing Corrupt PDF ---")
        corrupt_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\nGARBAGE DATA THAT IS NOT A VALID PDF STRUCTURE \x00\xff\xfe"
        try:
            res = client.post(
                "/api/runs/upload",
                files=[("files", ("corrupt.pdf", corrupt_bytes, "application/pdf"))],
            )
            print(f"Status: {res.status_code}, Body: {res.text[:200]}")
            results["corrupt_pdf"] = {
                "status": res.status_code,
                "clean": res.status_code in (200, 400, 422),
                "is_500": res.status_code >= 500,
                "body": res.text[:200],
            }
        except Exception as e:
            results["corrupt_pdf"] = {"error": str(e), "clean": False, "is_500": True}

        # -------------------------------------------------------------------
        # 4. Huge Image (~5MB PNG with noise)
        # -------------------------------------------------------------------
        print("\n--- 4. Testing Huge Image ---")
        img_buf = io.BytesIO()
        import os
        # Create a large image with noise to prevent compression
        random_bytes = os.urandom(2500 * 2500 * 3)
        img = Image.frombytes("RGB", (2500, 2500), random_bytes)
        img.save(img_buf, format="PNG")
        huge_bytes = img_buf.getvalue()
        print(f"Generated huge image size: {len(huge_bytes) / (1024*1024):.2f} MB")
        try:
            res = client.post(
                "/api/runs/upload",
                files=[("files", ("huge_image.png", huge_bytes, "image/png"))],
                timeout=60.0,
            )
            print(f"Status: {res.status_code}, Body: {res.text[:200]}")
            results["huge_image"] = {
                "status": res.status_code,
                "clean": res.status_code in (200, 400, 422),
                "is_500": res.status_code >= 500,
                "body": res.text[:200],
            }
        except Exception as e:
            results["huge_image"] = {"error": str(e), "clean": False, "is_500": True}

        # -------------------------------------------------------------------
        # 5. Non-invoice PDF ('ASA Case Study — Candidate Guide.pdf')
        # -------------------------------------------------------------------
        print("\n--- 5. Testing Non-invoice PDF (Candidate Guide) ---")
        guide_matches = list(REPO_ROOT.glob("*Candidate Guide*.pdf"))
        if guide_matches:
            guide_path = guide_matches[0]
            with open(guide_path, "rb") as f:
                guide_bytes = f.read()
            print(f"Candidate guide found: {guide_path.name}, size: {len(guide_bytes) / (1024*1024):.2f} MB")
            try:
                res = client.post(
                    "/api/runs/upload",
                    files=[("files", (guide_path.name, guide_bytes, "application/pdf"))],
                    timeout=90.0,
                )
                print(f"Status: {res.status_code}, Body: {res.text[:200]}")
                results["candidate_guide"] = {
                    "status": res.status_code,
                    "clean": res.status_code in (200, 400, 422),
                    "is_500": res.status_code >= 500,
                    "body": res.text[:200],
                }
            except Exception as e:
                results["candidate_guide"] = {"error": str(e), "clean": False, "is_500": True}
        else:
            print(f"Warning: Candidate Guide not found in {REPO_ROOT}")

        # -------------------------------------------------------------------
        # 6. Wrong extensions (.exe, .zip, .xyz)
        # -------------------------------------------------------------------
        print("\n--- 6. Testing Wrong Extensions (.exe, .xyz) ---")
        for bad_ext in ["malicious.exe", "data.xyz"]:
            try:
                res = client.post(
                    "/api/runs/upload",
                    files=[("files", (bad_ext, b"NOT AN INVOICE", "application/octet-stream"))],
                )
                print(f"File {bad_ext} -> Status: {res.status_code}, Body: {res.text[:200]}")
                results[bad_ext] = {
                    "status": res.status_code,
                    "clean": res.status_code in (200, 400, 422),
                    "is_500": res.status_code >= 500,
                    "body": res.text[:200],
                }
            except Exception as e:
                results[bad_ext] = {"error": str(e), "clean": False, "is_500": True}

        # -------------------------------------------------------------------
        # 7. Unicode filename
        # -------------------------------------------------------------------
        print("\n--- 7. Testing Unicode Filename ---")
        unicode_name = "Rechnung_Müller_Überweisung_€_100_₹_日本語.pdf"
        sample_01_bytes = open(SAMPLES_DIR / "01_happy_shree_ganesh_inr.pdf", "rb").read()
        try:
            res = client.post(
                "/api/runs/upload",
                files=[("files", (unicode_name, sample_01_bytes, "application/pdf"))],
            )
            print(f"Status: {res.status_code}, Body: {res.text[:200]}")
            results["unicode_filename"] = {
                "status": res.status_code,
                "clean": res.status_code in (200, 400, 422),
                "is_500": res.status_code >= 500,
                "body": res.text[:200],
            }
        except Exception as e:
            results["unicode_filename"] = {"error": str(e), "clean": False, "is_500": True}

        # -------------------------------------------------------------------
        # 8. Concurrent Upload of Same File
        # -------------------------------------------------------------------
        print("\n--- 8. Testing Concurrent Upload of Same File ---")
        client.post("/api/reset")
        sample_bytes = open(SAMPLES_DIR / "01_happy_shree_ganesh_inr.pdf", "rb").read()

        def do_upload(i):
            with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
                return c.post(
                    "/api/runs/upload",
                    files=[("files", (f"concurrent_01_{i}.pdf", sample_bytes, "application/pdf"))],
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(do_upload, 1)
            fut2 = executor.submit(do_upload, 2)
            res1 = fut1.result()
            res2 = fut2.result()

        print(f"Concurrent Res1: {res1.status_code}, Res2: {res2.status_code}")
        results["concurrent_upload"] = {
            "res1_status": res1.status_code,
            "res2_status": res2.status_code,
            "clean": res1.status_code in (200, 400, 422) and res2.status_code in (200, 400, 422),
            "is_500": res1.status_code >= 500 or res2.status_code >= 500,
        }

    print("\n=== Edge Cases Summary ===")
    failed_cases = []
    for test_name, res_info in results.items():
        clean = res_info.get("clean")
        is_500 = res_info.get("is_500")
        if not clean or is_500:
            failed_cases.append((test_name, res_info))
            print(f"  [FAIL] {test_name}: {res_info}")
        else:
            print(f"  [PASS] {test_name}: {res_info.get('status', 'OK')}")

    return failed_cases

if __name__ == "__main__":
    failures = test_edge_cases()
    if failures:
        print(f"\nCompleted with {len(failures)} failures.")
        sys.exit(1)
    else:
        print("\nALL Step 3 Edge Cases PASSED cleanly!")
        sys.exit(0)
