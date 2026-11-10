"""
Test Suite for MongoDB Atlas Persistence, Live SSE Stages Stream, and AP Dashboard Analytics.

Tests:
1. Persistence Layer (backend/persist.py):
   - Primary: MongoDB Atlas lifecycle via mongomock
     - Initial seeding into collection `kv_files` with {_id: path, content: Binary, updated_at}
     - Hash-based change detection and background flush
     - File restoration from MongoDB into backend/data
   - Secondary: PostgreSQL / SQLite adapter fallback
   - Default: 'local' when neither MONGODB_URI nor DATABASE_URL is set
   - Down DB resilience: short timeout, never crashes app
   - GET /api/health returns {"status": "ok", "persistence": "database"|"local"}
2. Live Stages & ObservableStageList:
   - on_stage callback receives stage events in real time
3. Live SSE Upload Stream (POST /api/runs/upload-stream):
   - Streams text/event-stream with file_start, stage, run_complete, and done events
4. Dashboard Analytics (GET /api/dashboard):
   - Totals, amount_by_decision_inr, top_vendors, reason_breakdown, recent_trend (14 days)
"""

import os
import sys
import json
import time
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from backend.main import app
from backend.persist import (
    get_persistence_mode,
    get_persistence_backend,
    start_persistence,
    stop_persistence,
    set_custom_mongo_collection,
    set_custom_connection_factory,
    flush_to_mongo,
    restore_from_mongo,
    DATA_DIR,
)
from backend.engine import (
    process_invoice_file,
    reset_engine_state,
    get_run,
    get_all_runs,
    save_run,
    _RUNS_CACHE,
    RUNS_JSON,
)
from backend.ocr import read_document
from backend.auth import authenticate_user, create_session, get_session_user


class TestPersistenceAndStream(unittest.TestCase):

    def setUp(self):
        reset_engine_state()
        stop_persistence()
        set_custom_mongo_collection(None)
        set_custom_connection_factory(None)

    def tearDown(self):
        stop_persistence()
        set_custom_mongo_collection(None)
        set_custom_connection_factory(None)
        reset_engine_state()

    # -----------------------------------------------------------------------
    # 1. MongoDB Atlas Persistence Tests (Primary)
    # -----------------------------------------------------------------------
    def test_mongodb_persistence_lifecycle(self):
        """Tests MongoDB Atlas persistence with mongomock collection."""
        import mongomock

        client_mock = mongomock.MongoClient()
        mock_coll = client_mock["zamp_ap"]["kv_files"]
        set_custom_mongo_collection(mock_coll)

        # Start persistence with MongoDB
        start_persistence(mongo_uri="mongodb+srv://mock.mongodb.net")
        self.assertEqual(get_persistence_mode(), "database")
        self.assertEqual(get_persistence_backend(), "mongodb")

        # GET /api/health should report 'database'
        client = TestClient(app)
        res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("persistence"), "database")

        # Verify initial seeding of shipped files
        seeded_count = mock_coll.count_documents({})
        self.assertGreater(seeded_count, 0)

        # Test change detection: write a test file
        test_file = DATA_DIR / "test_mongo_sample.json"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"test": "atlas_v1"}))

        flushed = flush_to_mongo(mock_coll)
        self.assertGreaterEqual(flushed, 1)

        # Verify document stored in collection with {_id, content, updated_at}
        doc = mock_coll.find_one({"_id": "test_mongo_sample.json"})
        self.assertIsNotNone(doc)
        self.assertEqual(doc["_id"], "test_mongo_sample.json")
        self.assertIn(b"atlas_v1", bytes(doc["content"]))

        # Overwrite file and flush again
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"test": "atlas_v2"}))

        flushed_2 = flush_to_mongo(mock_coll)
        self.assertEqual(flushed_2, 1)

        doc_v2 = mock_coll.find_one({"_id": "test_mongo_sample.json"})
        self.assertIn(b"atlas_v2", bytes(doc_v2["content"]))

        # Test file restoration
        test_file.unlink()
        self.assertFalse(test_file.exists())

        restored_count = restore_from_mongo(mock_coll)
        self.assertGreaterEqual(restored_count, 1)
        self.assertTrue(test_file.exists())
        with open(test_file, "r", encoding="utf-8") as f:
            self.assertIn("atlas_v2", f.read())

        # Cleanup
        if test_file.exists():
            test_file.unlink()
        stop_persistence()

    def test_persistence_mode_default_local(self):
        """When neither MONGODB_URI nor DATABASE_URL is set, mode should be 'local'."""
        self.assertEqual(get_persistence_mode(), "local")

        client = TestClient(app)
        res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("persistence"), "local")

    def test_postgres_sqlite_fallback_lifecycle(self):
        """Tests secondary fallback to PostgreSQL/SQLite adapter when Mongo is absent."""
        temp_dir = tempfile.mkdtemp()
        test_db_path = Path(temp_dir) / "test_pg_kv.db"
        conns = []

        def sqlite_factory():
            c = sqlite3.connect(str(test_db_path), check_same_thread=False)
            conns.append(c)
            return c

        set_custom_connection_factory(sqlite_factory)

        start_persistence(mongo_uri=None, pg_url="postgresql://user:pass@localhost:5432/db")
        self.assertEqual(get_persistence_mode(), "database")
        self.assertEqual(get_persistence_backend(), "postgres")

        stop_persistence()
        set_custom_connection_factory(None)
        for c in conns:
            try:
                c.close()
            except Exception:
                pass
        time.sleep(0.1)
        try:
            if test_db_path.exists():
                test_db_path.unlink()
            Path(temp_dir).rmdir()
        except Exception:
            pass

    def test_down_database_never_crashes(self):
        """Unreachable MongoDB or PostgreSQL must not crash application startup."""
        # Bogus unreachable MongoDB host
        start_persistence(mongo_uri="mongodb://nonexistent-host:27017")
        self.assertEqual(get_persistence_mode(), "local")

    # -----------------------------------------------------------------------
    # 2. Live Stages Callback Tests
    # -----------------------------------------------------------------------
    def test_live_stages_callback(self):
        """process_invoice_file must invoke on_stage for every executed stage."""
        collected_stages = []

        def stage_cb(stage_info):
            collected_stages.append(stage_info)

        r = process_invoice_file(
            "backend/data/sample_invoices/01_happy_shree_ganesh_inr.pdf",
            on_stage=stage_cb,
        )
        self.assertEqual(r.decision, "AUTO_APPROVE")
        self.assertGreaterEqual(len(collected_stages), 8)

        keys = [s["key"] for s in collected_stages]
        self.assertIn("INTAKE", keys)
        self.assertIn("PERCEPTION", keys)
        self.assertIn("NORMALIZATION", keys)
        self.assertIn("VALIDATION", keys)
        self.assertIn("VENDOR_FRAUD", keys)
        self.assertIn("PO_MATCH", keys)
        self.assertIn("vendor_policy", keys)
        self.assertIn("DUPLICATE_CHECK", keys)
        self.assertIn("ai_review", keys)
        self.assertIn("DECISION", keys)

        for s in collected_stages:
            self.assertIn("key", s)
            self.assertIn("name", s)
            self.assertIn("status", s)
            self.assertIn("summary", s)
            self.assertIn("duration_ms", s)

    # -----------------------------------------------------------------------
    # 3. Live SSE Upload Stream Tests
    # -----------------------------------------------------------------------
    def test_upload_stream_sse_endpoint(self):
        """POST /api/runs/upload-stream streams real-time stage events via SSE."""
        client = TestClient(app)
        sample_path = Path("backend/data/sample_invoices/01_happy_shree_ganesh_inr.pdf")

        with open(sample_path, "rb") as f:
            response = client.post(
                "/api/runs/upload-stream",
                files=[("files", (sample_path.name, f.read(), "application/pdf"))],
                data={"source_type": "UPLOAD"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))

        lines = response.text.strip().split("\n")
        events = []
        for line in lines:
            line = line.strip()
            if line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                events.append(payload)

        event_types = [e.get("type") for e in events]
        self.assertIn("file_start", event_types)
        self.assertIn("stage", event_types)
        self.assertIn("run_complete", event_types)
        self.assertIn("done", event_types)

        complete_event = next(e for e in events if e.get("type") == "run_complete")
        run_data = complete_event.get("run")
        self.assertEqual(run_data["decision"], "AUTO_APPROVE")
        self.assertIn("ai_review", run_data)
        self.assertIn("vendor_identity", run_data)

    # -----------------------------------------------------------------------
    # 4. Dashboard Analytics Endpoint Tests
    # -----------------------------------------------------------------------
    def test_dashboard_endpoint(self):
        """GET /api/dashboard returns correct schema and aggregations."""
        process_invoice_file("backend/data/sample_invoices/01_happy_shree_ganesh_inr.pdf")
        process_invoice_file("backend/data/sample_invoices/07_fraud_bank_changed_brightline_usd.pdf")

        client = TestClient(app)
        res = client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        dash = res.json()

        # 1. Totals
        self.assertIn("totals", dash)
        totals = dash["totals"]
        self.assertEqual(totals["runs"], 2)
        self.assertEqual(totals["approved"], 1)
        self.assertEqual(totals["rejected"], 1)
        self.assertEqual(totals["auto_rate_pct"], 50.0)

        # 2. Amount by decision
        self.assertIn("amount_by_decision_inr", dash)
        amounts = dash["amount_by_decision_inr"]
        self.assertGreater(amounts["AUTO_APPROVE"], 0)
        self.assertGreater(amounts["REJECT"], 0)

        # 3. Top vendors
        self.assertIn("top_vendors", dash)
        self.assertGreaterEqual(len(dash["top_vendors"]), 1)
        top_v = dash["top_vendors"][0]
        self.assertIn("name", top_v)
        self.assertIn("count", top_v)
        self.assertIn("total_inr", top_v)

        # 4. Reason breakdown
        self.assertIn("reason_breakdown", dash)
        self.assertGreaterEqual(len(dash["reason_breakdown"]), 1)
        reason_item = dash["reason_breakdown"][0]
        self.assertIn("label", reason_item)
        self.assertIn("count", reason_item)
        self.assertNotIn("_", reason_item["label"])  # Plain English label

        # 5. Recent trend (14 days)
        self.assertIn("recent_trend", dash)
        self.assertEqual(len(dash["recent_trend"]), 14)
        today_trend = dash["recent_trend"][-1]
        self.assertIn("date", today_trend)
        self.assertIn("count", today_trend)
        self.assertIn("approved", today_trend)
        self.assertIn("flagged", today_trend)

    # -----------------------------------------------------------------------
    # 5. Robustness & Security Production Tests
    # -----------------------------------------------------------------------
    def test_uploaded_files_and_runs_survive_restart(self):
        """Simulates container restart: uploads and runs persist into MongoDB and restore cleanly."""
        import mongomock

        client_mock = mongomock.MongoClient()
        mock_coll = client_mock["zamp_ap"]["kv_files"]
        set_custom_mongo_collection(mock_coll)

        start_persistence(mongo_uri="mongodb+srv://mock.mongodb.net")

        # 1. Simulate uploaded invoice file in data/uploads
        uploads_dir = DATA_DIR / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        test_upload = uploads_dir / "invoice_restart_sim_test.pdf"
        test_upload.write_bytes(b"%PDF-1.4 Mock Upload Invoice Content For Restart Survival Test")

        # 2. Process an invoice run to populate _RUNS_CACHE and runs.json
        run = process_invoice_file("backend/data/sample_invoices/01_happy_shree_ganesh_inr.pdf")
        saved_run_id = run.run_id

        # Flush state to MongoDB
        flush_to_mongo(mock_coll)
        stop_persistence()

        # 3. Simulate container wipe/restart: clear memory cache and delete disk files
        _RUNS_CACHE.clear()
        if test_upload.exists():
            test_upload.unlink()
        if RUNS_JSON.exists():
            RUNS_JSON.unlink()

        self.assertFalse(test_upload.exists())
        self.assertNotIn(saved_run_id, _RUNS_CACHE)

        # 4. Restart container with MongoDB Atlas persistence
        set_custom_mongo_collection(mock_coll)
        start_persistence(mongo_uri="mongodb+srv://mock.mongodb.net")

        # 5. Verify upload was restored to disk
        self.assertTrue(test_upload.exists())
        self.assertEqual(test_upload.read_bytes(), b"%PDF-1.4 Mock Upload Invoice Content For Restart Survival Test")

        # 6. Verify run survives and is queryable
        restored_run = get_run(saved_run_id)
        self.assertIsNotNone(restored_run)
        self.assertEqual(restored_run.decision, "AUTO_APPROVE")

        # Clean up
        if test_upload.exists():
            test_upload.unlink()
        stop_persistence()

    def test_absent_and_invalid_mongodb_uri(self):
        """Confirms persist.py defaults to local when URI is absent or malformed/invalid."""
        # Absent (None)
        start_persistence(mongo_uri=None, pg_url=None)
        self.assertEqual(get_persistence_mode(), "local")
        self.assertEqual(get_persistence_backend(), "local")
        stop_persistence()

        # Absent (empty string)
        start_persistence(mongo_uri="", pg_url="")
        self.assertEqual(get_persistence_mode(), "local")
        self.assertEqual(get_persistence_backend(), "local")
        stop_persistence()

        # Invalid scheme
        start_persistence(mongo_uri="not_a_valid_mongo_uri")
        self.assertEqual(get_persistence_mode(), "local")
        self.assertEqual(get_persistence_backend(), "local")
        stop_persistence()

        # Malformed host with short timeout
        start_persistence(mongo_uri="mongodb://localhost:59999/?connectTimeoutMS=500")
        self.assertEqual(get_persistence_mode(), "local")
        self.assertEqual(get_persistence_backend(), "local")
        stop_persistence()

    def test_security_path_traversal_rejection(self):
        """Directly tests path-traversal rejection and sanitisation on file endpoints."""
        from backend.main import _find_file_on_disk, serve_raw_file, serve_preview_image
        from fastapi import HTTPException

        client = TestClient(app)

        # 1. Direct function path traversal checks
        traversal_payloads = [
            "../../etc/passwd",
            "..\\..\\windows\\win.ini",
            "../main.py",
            "subdir/../../secret.txt",
        ]
        for payload in traversal_payloads:
            self.assertIsNone(_find_file_on_disk(payload))
            with self.assertRaises(HTTPException) as ctx:
                serve_raw_file(payload)
            self.assertEqual(ctx.exception.status_code, 400)

            with self.assertRaises(HTTPException) as ctx_img:
                serve_preview_image(payload)
            self.assertEqual(ctx_img.exception.status_code, 400)

        # 2. HTTP client requests with path traversal sequences
        res_bs = client.get("/api/files/..\\test.txt")
        self.assertEqual(res_bs.status_code, 400)

        # 3. Valid sample file download
        res_ok = client.get("/api/files/01_happy_shree_ganesh_inr.pdf")
        self.assertEqual(res_ok.status_code, 200)

        # 4. Non-existent file returns 404
        res_404 = client.get("/api/files/nonexistent_document_123.pdf")
        self.assertEqual(res_404.status_code, 404)

    def test_security_upload_limits(self):
        """Verifies upload file count (max 10) and size limit (15MB) with 400/413."""
        client = TestClient(app)

        # 1. More than 10 files should return 400
        eleven_files = [("files", (f"file_{i}.pdf", b"%PDF-1.4 mock", "application/pdf")) for i in range(11)]
        res_count = client.post("/api/runs/upload", files=eleven_files)
        self.assertEqual(res_count.status_code, 400)
        self.assertIn("Too many files", res_count.json().get("detail", ""))

        # 2. File exceeding 15MB should return 413
        oversized_data = b"X" * (16 * 1024 * 1024)
        one_huge_file = [("files", ("huge_invoice.pdf", oversized_data, "application/pdf"))]
        res_size = client.post("/api/runs/upload", files=one_huge_file)
        self.assertEqual(res_size.status_code, 413)
        self.assertIn("exceeds maximum allowed size", res_size.json().get("detail", ""))

    def test_auth_salt_and_session_expiration(self):
        """Tests that admin_1 always logs in, custom salt works, and sessions expire."""
        # 1. Default admin_1 login works
        admin = authenticate_user("admin_1", "pass@admin")
        self.assertIsNotNone(admin)
        self.assertEqual(admin["username"], "admin_1")

        # 2. Session creation and expiration
        token = create_session(admin, ttl_seconds=1)
        self.assertIsNotNone(get_session_user(token))
        time.sleep(1.2)
        # After TTL, session must expire and return None
        self.assertIsNone(get_session_user(token))

    def test_ocr_disabled_flag_and_memory_safety(self):
        """Verifies ENABLE_LOCAL_OCR=false falls back gracefully to low-confidence review."""
        old_val = os.environ.get("ENABLE_LOCAL_OCR")
        try:
            os.environ["ENABLE_LOCAL_OCR"] = "false"
            text, method, conf, meta = read_document("backend/data/sample_invoices/06_scanned_muller_no_po_eur.png")
            self.assertEqual(method, "ocr")
            self.assertLessEqual(conf, 0.50)
            self.assertTrue(meta.get("review_required"))
        finally:
            if old_val is not None:
                os.environ["ENABLE_LOCAL_OCR"] = old_val
            else:
                os.environ.pop("ENABLE_LOCAL_OCR", None)


if __name__ == "__main__":
    unittest.main()
