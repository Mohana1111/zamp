"""
Step 1: Verify production serving on port 8080.
Checks:
- / serves index.html
- /assets/* load (both css and js)
- /api/health
- /api/dashboard
- /api/vendors
- /api/settings
- /api/runs
"""
import re
import httpx

BASE_URL = "http://127.0.0.1:8080"

def test_step1():
    print(f"Testing Step 1 against {BASE_URL}...")
    failures = []
    
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # 1. / serves index.html
        res = client.get("/")
        print(f"GET /: status={res.status_code}, content-type={res.headers.get('content-type')}")
        if res.status_code != 200:
            failures.append(f"GET / returned {res.status_code}, expected 200")
        elif "<!doctype html>" not in res.text.lower() and "<html" not in res.text.lower():
            failures.append(f"GET / did not return HTML content: {res.text[:200]}")
        else:
            print("  [PASS] / serves index.html correctly")

        # Extract asset links from index.html
        asset_matches = re.findall(r'src=["\'](/assets/[^"\']+)["\']|href=["\'](/assets/[^"\']+)["\']', res.text)
        asset_paths = [m[0] or m[1] for m in asset_matches]
        print(f"Found assets: {asset_paths}")

        for asset in asset_paths:
            a_res = client.get(asset)
            print(f"GET {asset}: status={a_res.status_code}, length={len(a_res.content)}, content-type={a_res.headers.get('content-type')}")
            if a_res.status_code != 200:
                failures.append(f"GET {asset} failed with {a_res.status_code}")
            elif len(a_res.content) == 0:
                failures.append(f"GET {asset} returned empty content")
            else:
                print(f"  [PASS] {asset} loaded successfully")

        # Test API endpoints
        endpoints = [
            "/api/health",
            "/api/dashboard",
            "/api/vendors",
            "/api/settings",
            "/api/runs",
        ]

        for ep in endpoints:
            api_res = client.get(ep)
            print(f"GET {ep}: status={api_res.status_code}, content-type={api_res.headers.get('content-type')}")
            if api_res.status_code != 200:
                failures.append(f"GET {ep} returned {api_res.status_code}, body: {api_res.text[:200]}")
            else:
                try:
                    data = api_res.json()
                    print(f"  [PASS] {ep} returned valid JSON (type={type(data).__name__})")
                except Exception as e:
                    failures.append(f"GET {ep} returned non-JSON response: {e}")

    print("\n--- Step 1 Summary ---")
    if failures:
        print(f"FAILED with {len(failures)} issues:")
        for f in failures:
            print(f"  - {f}")
        return False
    else:
        print("ALL Step 1 checks PASSED!")
        return True

if __name__ == "__main__":
    import sys
    success = test_step1()
    sys.exit(0 if success else 1)
