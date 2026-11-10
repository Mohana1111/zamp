import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_all():
    print("Testing 1: GET /api/overview...")
    res = client.get("/api/overview")
    assert res.status_code == 200, res.text
    overview = res.json()
    assert "quotations" in overview, "quotations key missing from overview"
    print(f"Quotations in overview: {len(overview['quotations'])}")

    print("Testing 2: GET /api/quotations...")
    res = client.get("/api/quotations")
    assert res.status_code == 200, res.text
    data = res.json()
    quotations = data.get("quotations", [])
    assert isinstance(quotations, list)
    if quotations:
        q0 = quotations[0]
        print(f"Found quotation: {q0['quotation_number']} - {q0['vendor_name']}")


    print("Testing 3: POST /api/quotations (Manual creation)...")
    payload = {
        "quotation_number": "QT-TEST-2026",
        "vendor_name": "Test Apex Solutions",
        "vendor_country": "IN",
        "vendor_tax_id": "29AABCU9603R1ZM",
        "currency": "INR",
        "quotation_date": "2026-02-01",
        "validity_period": "60 Days",
        "subtotal": 100000.0,
        "tax_amount": 18000.0,
        "total_amount": 118000.0,
        "items_count": 1,
        "total_qty": 1,
        "line_items": [{
            "line_no": 1,
            "item_code": "TEST-01",
            "description": "Consulting Services",
            "qty": 1,
            "unit_price": 100000.0,
            "amount": 100000.0,
            "tax_rate": 18.0
        }]
    }
    res = client.post("/api/quotations", json=payload)
    assert res.status_code == 200, res.text
    created_q = res.json()["quotation"]
    test_qid = created_q["quotation_id"]
    print(f"Created quotation ID: {test_qid}")

    print("Testing 4: POST /api/sources/gmail/send-to-agent...")
    gmail_msgs = client.get("/api/sources/gmail/messages").json()
    if not gmail_msgs:
        from backend.connectors import _load_sandbox_sample_emails
        _load_sandbox_sample_emails()
        gmail_msgs = client.get("/api/sources/gmail/messages").json()

    if gmail_msgs:
        msg_id = gmail_msgs[0]["id"]
        res = client.post("/api/sources/gmail/send-to-agent", json={"message_id": msg_id})
        assert res.status_code == 200, res.text
        agent_run = res.json()["run"]
        print(f"Agent run generated: {agent_run['run_id']} with status: {agent_run.get('human_approval_status')}")
        assert agent_run.get("human_approval_status") in ["PENDING_FINAL_APPROVAL", "NEEDS_HUMAN_APPROVAL"]
        assert agent_run.get("email_thread_history") is not None
        print(f"Thread history length: {len(agent_run['email_thread_history'])}")

        print("Testing 5: POST /api/runs/{run_id}/link-quotation/{quotation_id}...")
        res = client.post(f"/api/runs/{agent_run['run_id']}/link-quotation/{test_qid}")
        assert res.status_code == 200, res.text
        linked_run = res.json()["run"]
        assert linked_run.get("expected_quotation") is not None
        print(f"Linked quotation status: {linked_run['expected_quotation']['match_status']}")

        print("Testing 6: POST /api/runs/{run_id}/approve...")
        res = client.post(
            f"/api/runs/{agent_run['run_id']}/approve",
            json={"reviewer": "AP Lead", "action": "APPROVE", "comment": "Verified by controller"}
        )
        assert res.status_code == 200, res.text
        approved_run = res.json()["run"]
        assert approved_run["human_approval_status"] == "APPROVED_BY_HUMAN"
        print(f"Approved run status: {approved_run['human_approval_status']}")


    print("Testing 7: POST /api/sources/gmail/sync-extension...")
    res = client.post("/api/sources/gmail/sync-extension")
    assert res.status_code == 200, res.text
    print("Extension sync result:", res.json().get("status"))

    print("Testing 8: DELETE /api/quotations/{test_qid}...")
    res = client.delete(f"/api/quotations/{test_qid}")
    assert res.status_code == 200, res.text
    print("Quotation deleted successfully!")

    print("\n==========================================")
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("==========================================")

if __name__ == "__main__":
    test_all()
