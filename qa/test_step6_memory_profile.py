"""
Step 6: Measure peak RSS memory of the server process while processing:
1. Scanned PNG (06_scanned_muller_no_po_eur.png - 3.25MB)
2. Big PDF (ASA Case Study — Candidate Guide.pdf - 4.52MB)
Compare vs 512 MB Render free tier limit.
"""

import os
import sys
import json
import time
import threading
from pathlib import Path
import psutil
import httpx

BASE_URL = "http://127.0.0.1:8080"
REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "backend" / "data" / "sample_invoices"


def get_server_process():
    """Finds the python process listening on port 8080."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            connections = proc.net_connections(kind='inet')
            for conn in connections:
                if conn.laddr and conn.laddr.port == 8080 and conn.status == psutil.CONN_LISTEN:
                    return proc
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return None


class MemorySampler:
    def __init__(self, proc: psutil.Process, interval: float = 0.05):
        self.proc = proc
        self.interval = interval
        self.running = False
        self.samples = []
        self._thread = None

    def start(self):
        self.running = True
        self.samples = []
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def _sample_loop(self):
        while self.running:
            try:
                # Include child processes if any
                rss = self.proc.memory_info().rss
                for child in self.proc.children(recursive=True):
                    try:
                        rss += child.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                self.samples.append(rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(self.interval)

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        return max(self.samples) if self.samples else 0


def profile_memory():
    proc = get_server_process()
    if not proc:
        print("[ERROR] Could not find server process on port 8080!")
        sys.exit(1)

    print(f"Found server process PID: {proc.pid} ({proc.name()})")

    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        # Reset server state
        client.post("/api/reset")
        time.sleep(1.0)

        # Baseline RSS
        baseline_rss = proc.memory_info().rss
        baseline_mb = baseline_rss / (1024 * 1024)
        print(f"Baseline RSS Memory: {baseline_mb:.2f} MB")

        # 1. Profile Scanned PNG
        print("\n--- Profiling Scanned PNG (06_scanned_muller_no_po_eur.png) ---")
        png_path = SAMPLES_DIR / "06_scanned_muller_no_po_eur.png"
        png_bytes = open(png_path, "rb").read()
        png_size_mb = len(png_bytes) / (1024 * 1024)
        print(f"PNG File size: {png_size_mb:.2f} MB")

        sampler = MemorySampler(proc)
        sampler.start()
        res_png = client.post("/api/runs/upload", files=[("files", ("06_scanned_muller_no_po_eur.png", png_bytes, "image/png"))])
        peak_png_rss = sampler.stop()
        peak_png_mb = peak_png_rss / (1024 * 1024)
        print(f"PNG upload status: {res_png.status_code}")
        print(f"Peak RSS during Scanned PNG: {peak_png_mb:.2f} MB (Delta: +{peak_png_mb - baseline_mb:.2f} MB)")

        time.sleep(1.0)
        intermediate_rss = proc.memory_info().rss / (1024 * 1024)
        print(f"Post-PNG RSS: {intermediate_rss:.2f} MB")

        # 2. Profile Big PDF
        print("\n--- Profiling Big PDF (ASA Case Study Candidate Guide) ---")
        guide_matches = list(REPO_ROOT.glob("*Candidate Guide*.pdf"))
        if not guide_matches:
            print("[ERROR] Candidate guide PDF not found!")
            sys.exit(1)
        pdf_path = guide_matches[0]
        pdf_bytes = open(pdf_path, "rb").read()
        pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
        print(f"PDF File size: {pdf_size_mb:.2f} MB ({pdf_path.name})")

        sampler = MemorySampler(proc)
        sampler.start()
        res_pdf = client.post("/api/runs/upload", files=[("files", (pdf_path.name, pdf_bytes, "application/pdf"))])
        peak_pdf_rss = sampler.stop()
        peak_pdf_mb = peak_pdf_rss / (1024 * 1024)
        print(f"PDF upload status: {res_pdf.status_code}")
        print(f"Peak RSS during Big PDF: {peak_pdf_mb:.2f} MB (Delta: +{peak_pdf_mb - intermediate_rss:.2f} MB)")

        # Overall Peak
        overall_peak_mb = max(peak_png_mb, peak_pdf_mb)
        render_limit_mb = 512.0
        utilization_pct = (overall_peak_mb / render_limit_mb) * 100.0
        headroom_mb = render_limit_mb - overall_peak_mb

        print("\n==========================================")
        print("=== Step 6: Memory Profile Summary ===")
        print(f"Baseline Server RSS:    {baseline_mb:.2f} MB")
        print(f"Peak RSS (Scanned PNG): {peak_png_mb:.2f} MB")
        print(f"Peak RSS (Big PDF):     {peak_pdf_mb:.2f} MB")
        print(f"Max Peak RSS:           {overall_peak_mb:.2f} MB")
        print(f"Render Free Tier Limit: {render_limit_mb:.2f} MB")
        print(f"Memory Utilization:     {utilization_pct:.1f}%")
        print(f"Safety Headroom:        {headroom_mb:.2f} MB")

        if overall_peak_mb > render_limit_mb:
            print(f"[FAIL] Server exceeded 512MB Render limit by {overall_peak_mb - render_limit_mb:.2f} MB (Risk of OOM)!")
        else:
            print(f"[PASS] Server stayed well within 512MB limit with {headroom_mb:.2f} MB margin.")

        # Save results to a json file for report generation
        results_data = {
            "baseline_mb": round(baseline_mb, 2),
            "png_file_mb": round(png_size_mb, 2),
            "peak_png_mb": round(peak_png_mb, 2),
            "pdf_file_mb": round(pdf_size_mb, 2),
            "peak_pdf_mb": round(peak_pdf_mb, 2),
            "overall_peak_mb": round(overall_peak_mb, 2),
            "render_limit_mb": render_limit_mb,
            "utilization_pct": round(utilization_pct, 1),
            "headroom_mb": round(headroom_mb, 2),
        }
        with open(REPO_ROOT / "qa" / "memory_results.json", "w", encoding="utf-8") as f:
            json.dump(results_data, f, indent=2)


if __name__ == "__main__":
    profile_memory()
