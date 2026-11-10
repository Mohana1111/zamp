# Upgrade Spec — Invoice-to-Decision (AP)

Goal: a sleek, professional, easy-to-use AP tool. Accurate deterministic workflow + a precise LLM
reasoning layer + robust OCR. UI shows business meaning only — never implementation details.

## Principles
- **Rules guard, LLM reasons.** Hard facts (tax ID, bank account, PO balance, currency, duplicates, arithmetic)
  are checked deterministically. The LLM handles *fuzzy judgement* and the *final safety review*.
- **LLM can only make a case safer, never riskier.** It may downgrade APPROVE → REVIEW/REJECT. It may approve only
  when every deterministic hard check is clean. If LLM is unavailable, a rule-based reviewer takes over
  (approve only if clean AND within vendor policy; otherwise REVIEW).
- **No secrets in source.** Keys come from env / `.env` (`GEMINI_API_KEY`, `GROQ_API_KEY`) or the settings endpoint.
  Remove the hardcoded Groq key in `backend/extractor.py` and `.env.example`.
- **UI never mentions**: stage numbers, model/provider names (Groq, Llama, Gemini), regex, hashes, "deterministic",
  "pipeline", "extraction engine", reason-code constants (map to plain English).

## Backend work (`backend/`)

### 1. `llm.py` — unified LLM client (new)
- `llm_available() -> bool`, `call_llm_json(system, user, images=None, schema_hint=None, temperature=0) -> dict|None`.
- Provider order: Gemini (`google-genai`, model `gemini-2.5-flash`, supports images) → Groq (existing OpenAI-compatible
  REST, text only) → None. Keys from env or runtime config (`set_ai_api_key`). Strict JSON out, 1 retry, 30s timeout.
- Existing `extractor.call_groq_llm` / `AI_CONFIG` should delegate to this module; keep `/api/config/ai` working.

### 2. `ocr.py` — document reading (new)
Layered, used by `extractor.ingest_raw_document`:
1. PDF text layer via PyMuPDF. If text < ~40 chars/page → treat as scanned.
2. Scanned PDF/image → render pages at 200–300 dpi → local OCR with `rapidocr-onnxruntime` (add to requirements;
   lazy import; if unavailable, skip).
3. If LLM has vision (Gemini) and OCR text is poor/empty or extraction is low-confidence → send page images to the LLM
   for structured extraction (vendor, tax id, invoice no, dates, PO ref, currency, line items, subtotal, tax, total, bank).
4. Return text + `ocr_method` ("text-layer" | "ocr" | "vision") + `ocr_confidence`. Keep `SCANNED_DOCUMENT` reason code only
   when confidence is genuinely low (don't force review for every clean scan).
Handles: PDF, PNG/JPG/JPEG/WEBP/TIFF, XLSX, DOCX, TXT. Test with `backend/data/sample_invoices/06_scanned_muller_no_po_eur.png` and `.pdf`.

### 3. Vendor policy / pre-approved vendors (`policy.py`, new; stored in `data/vendor_policy.json`)
Per vendor_id:
```
trust: "PREAPPROVED" | "STANDARD" | "WATCHLIST" | "BLOCKED"
auto_approve_limit: float|null     # in vendor currency; max invoice total that may auto-approve
price_tolerance_pct: float|null    # overrides global (line price variance)
total_tolerance_pct: float|null    # overrides global (invoice vs PO total)
allow_without_po: bool             # recurring services (rent, SaaS, utilities) — no PO needed under limit
notes: str
```
Global settings (`data/settings.json`): `default_price_tolerance_pct` (2), `default_total_tolerance_pct` (1),
`default_auto_approve_limit_inr` (null), `duplicate_window_days` (365), `require_po_above_inr` (50000),
`ai_review_enabled` (true), `ai_min_confidence` (0.85).

Behaviour:
- BLOCKED → REJECT (`BLOCKED_VENDOR`).
- WATCHLIST → never auto-approve; NEEDS_REVIEW (`WATCHLIST_VENDOR`).
- PREAPPROVED: tolerance = vendor/global; no-PO invoice with `allow_without_po` and total ≤ limit → eligible
  (`PREAPPROVED_NO_PO`, not ON_HOLD). Total above limit → NEEDS_REVIEW (`OVER_VENDOR_LIMIT`).
  PREAPPROVED never bypasses: bank mismatch, tax-ID mismatch, duplicate, currency mismatch, arithmetic error, PO overbilling.
- STANDARD: current behaviour, with configurable tolerances (replace hardcoded variance constants).
- Within-tolerance variances pass with an informational note (not review).

Endpoints:
- `GET /api/vendors` → vendors merged with policy + stats `{invoice_count, approved_total_inr, last_invoice_date}`
- `POST /api/vendors` (create), `PUT /api/vendors/{id}` (edit master: name, aliases, tax_id, country, currency, bank, status, terms),
  `PUT /api/vendors/{id}/policy`, `DELETE /api/vendors/{id}` (soft: status INACTIVE)
- `GET/PUT /api/settings` (global settings above)
- `GET /api/ai/status` → `{ "enabled": bool, "mode": "ai"|"rules" }` (no provider names)
- `POST /api/vendors/{id}/preapprove` convenience: sets trust PREAPPROVED (used by "Pre-approve vendor" button after a human approves)

Writes to `vendors.csv` must preserve the column order and encoding (UTF-8; `Müller` currently mojibake in CSV — fix to proper UTF-8 and make alias matching accent-insensitive).

### 4. LLM reasoning tasks (in `llm_review.py`, new)
**a) `judge_vendor_identity(inv_vendor_name, inv_tax_id, inv_bank, master_vendor) -> {same_entity, confidence, reason}`**
Used when tax ID matches (or is absent) but name differs from legal name/aliases beyond a close fuzzy score.
Rules: legal-suffix variants (Pvt Ltd / Private Limited, Inc / Incorporated, GmbH), abbreviations, punctuation,
accents, word order, minor typos ⇒ same entity. **Tax ID (GSTIN/VAT/EIN/UEN) and bank account must match exactly** — a
name-only match with a different/missing tax ID when the master has one is NOT accepted. Different tax ID ⇒ different
entity ⇒ `UNKNOWN_VENDOR`/`TAX_ID_MISMATCH` (hard). Output reason shown in UI: e.g. “Name differs slightly
(‘Shree Ganesh Packaging Private Limited’ vs ‘…Pvt Ltd’); GST number and bank account match exactly.”
Rule-based fallback: normalise (casefold, strip accents/punctuation, expand suffix synonyms) + `difflib` ratio ≥ 0.88.
Add reason codes `VENDOR_NAME_VARIATION` (info, passes) and `TAX_ID_MISMATCH` (hard → REJECT/ON_HOLD).

**b) `final_review(case) -> {verdict: "APPROVE"|"REVIEW"|"REJECT", confidence, summary, checks:[{label, ok, note}], concerns:[str]}`**
`case` = compact JSON: extracted invoice (with per-field confidence), vendor master + policy, vendor-identity result,
matched PO + remaining balance + prior invoices, line diffs, FX, duplicate findings, deterministic reason codes, deterministic decision.
System prompt: senior AP controller; be precise and conservative; cite concrete numbers; never invent data; look for
anything odd (suspicious wording, payment-instruction changes, round-number padding, weekend/future dates, due date before
invoice date, tax rate inconsistent with country, unusually large vs history, vendor/email sender domain mismatch).
Final decision logic (in engine, last step):
```
if deterministic hard-fail -> keep (LLM only adds explanation)
elif deterministic clean (AUTO_APPROVE-eligible):
    verdict APPROVE and confidence >= ai_min_confidence -> AUTO_APPROVE
    else -> NEEDS_REVIEW with the LLM's concerns
elif deterministic is review-level -> LLM may *explain*; never upgrade to approve, except
    within-tolerance variance already cleared by policy.
```
Store as `ai_review` on the run (see contract) and keep `ai_summary`/`ai_flaws` filled from it.

**c) `explain_decision(run) -> str`**: 2–3 plain sentences for the top of the UI; rule-based template fallback.

### 5. Engine integration
- `process_invoice_file` currently is a ~1100-line monolith with scenario hacks (`is_scenario_11`, filename-based
  logic). Remove filename/scenario-specific hacks: decisions must follow from data + policy only. Keep existing sample outputs
  correct (see samples list in ARCHITECTURE.md) and re-verify each.
- Add a visible “AI review” step to `stages` (key `ai_review`) and a “Vendor policy” step. Keep step list otherwise.
- Extra useful checks (cheap, deterministic): due date < invoice date; invoice date in future or > 1 yr old (stale);
  tax rate vs PO line tax rate; duplicate by (vendor, normalized number) and by (vendor, total, date) fuzzy.
- Human override stays; “Approve & pre-approve vendor” optional flag on override → sets policy PREAPPROVED.

### Contract additions (InvoiceRunResult)
```
ai_review: {verdict, confidence, summary, checks:[{label, ok, note}], concerns:[str], mode:"ai"|"rules"}
vendor_identity: {same_entity: bool, confidence: float, reason: str, name_on_invoice: str, name_on_record: str}|null
policy_applied: {trust, limit, price_tolerance_pct, total_tolerance_pct, notes:[str]}|null
read_method: "text"|"ocr"|"vision"
```
`decision` enum unchanged (AUTO_APPROVE | NEEDS_REVIEW | ON_HOLD | REJECT). UI labels: Approved / Needs review / On hold / Rejected.

### Tests
`backend/test_features.py` (extend) or `backend/test_policy.py`: run every file in `data/sample_invoices` and assert expected decisions;
add cases: preapproved vendor w/o PO under limit → approved; preapproved over limit → review; blocked → reject;
name variation + same tax ID → approved w/ `VENDOR_NAME_VARIATION`; same name + different tax ID → rejected/hold;
scanned PNG read via OCR with no LLM key; all must pass with LLM disabled (rules mode) as well.

## Frontend work (`frontend/src/`) — React 18 + Tailwind 4 + lucide-react (already installed)

### Design language
Modern fintech: calm, light theme, generous whitespace, 1 accent colour (indigo/emerald for approve), Inter font,
subtle borders/shadows, rounded-xl, smooth transitions, skeleton loaders, keyboard-friendly, responsive.
Status colours: Approved = emerald, Needs review = amber, On hold = slate/blue, Rejected = rose.
Dark mode is optional; skip unless trivial.

### Information architecture (remove everything else)
Left sidebar (collapsible on mobile) with 4 items + small AI status dot (“AI review on/off” only):
1. **Invoices** (home)
2. **Vendors**
3. **Purchase orders**
4. **Settings** (tolerances, limits, AI on/off + API key field with “Connected” state)

Delete/stop rendering: Demo guide, extension popup, Slack/Teams tutorials, ConnectApps, platform bars, Gmail drawer
complexity, Footer, “execution trace” jargon, admin financial dashboard, batch-compare modal, scenario pickers.
Keep a simple **Email inbox import** only if it is one compact button (“Import from email”) reusing existing endpoints;
otherwise drop. Keep login only if the app already requires it — restyle it minimal.

### Invoices page
- Top: 4 compact stat tiles (Awaiting review · Approved · On hold · Rejected) that double as filters; search box.
- Big, friendly **drop zone** (“Drop invoices here — PDF, image, Excel or Word”) supports multi-file; shows per-file progress
  chips while processing, then rows slide in.
- Table: Vendor · Invoice # · PO · Amount (invoice currency) · Status pill · Date. Row click opens a **right-side detail panel**
  (wide drawer), not a new page.
- Empty state with one clear call to action.

### Invoice detail panel
1. **Header**: vendor, invoice #, amount, status pill.
2. **Decision card**: one-sentence outcome + 2–3 sentence plain-English reasoning (`ai_review.summary` / `decision_summary`).
   Concerns as short bullets. Buttons: **Approve**, **Reject**, (if needs review) “Approve & pre-approve vendor”; comment box in a
   small popover. Confirmed state shows who/when.
3. **Checks** (compact checklist with ✓ / ! / ✕ icons, one line each, expandable for the note): Vendor verified (incl. name variation
   note), Bank details, Purchase order match, Amount within tolerance, Duplicate check, Math & fields, Policy. Derive from `stages`
   + `ai_review.checks` + `vendor_identity` — wording in business language.
4. **Compare** tab: invoice vs PO (headers + line items) with variance highlighted; PO usage bar (used / this invoice / remaining).
5. **Document** tab: preview image of the original (`/api/files/{filename}/preview-image`) beside the extracted fields.
Tabs: Overview · Compare · Document. No raw JSON, hashes, engine names.

### Vendors page
Cards/table: name, country, tax ID, trust badge, auto-approve limit, last invoice. Click → side panel to edit master + policy
(trust segmented control: Pre-approved / Standard / Watchlist / Blocked; limit; tolerances; allow without PO; notes).
“Add vendor” button. Inline hints under each control (one short line).

### Purchase orders page
Clean table: PO · Vendor · Total · Billed · Remaining (progress bar) · Status. Row expand → lines + linked invoices. Keep existing data
sources; trim `PoLedgerView.tsx` (84 KB) drastically or replace.

### Settings page
Global tolerances / limits / AI toggle & key. Save toast.

### Quality bar
- `npm run build` passes with zero TS errors. No console errors. No dead components left imported.
- Update `types/index.ts` and `services/api.ts` for new fields/endpoints; remove unused API functions.
- Copy: short, plain, no jargon; no lorem/demo text; no emojis in UI.
- Prefer deleting unused files over leaving them.
