# Handoff Notes — Aurae EMS (rebranded from OS2 Studio EMS)

This is the same Employee Management System application built and used by OS2 Studio,
rebranded for **Aurae Software Solutions**. No logic, workflow, or functionality has
been changed — only branding (logo, colors/text, contact details) and the items below.

## ✅ Already done
<<<<<<< HEAD
- Logo replaced everywhere (sidebar, login screen, invoice/payslip/receipt/project PDFs, favicon, app icons)
- All "OS2 Studio" text replaced with "Aurae Software Solutions" across the app UI, PDF generator, and standalone invoice tool (`aurae-invoice-generator.html`)
- Seed admin login changed from `admin@os2studio.com` → `admin@auraesoftwaresolutions.com`
- OS2's own live backend URL and CORS origin removed from the code (was pointing at OS2's Railway deployment)
- A small "Built by OS2 Studio" credit line added under the login footer (non-intrusive, as requested)
- App responsive across mobile / tablet / desktop
- **Full app color theme switched from OS2's amber to Aurae's crimson (#DB1F33)** — every button, badge, chart, active nav state, and highlight across the whole dashboard, not just the invoice tool
- **Invoice/Quotation template rebuilt to match your final revised PDF (`AUR-INV-260001_Revised.pdf`) exactly**: A4 page size, centered "INVOICE" title, top diagonal + bottom-left corner graphics (cropped pixel-exact from your PDF), italic red company branding block, real registered details auto-filled (name "Aurae Software Solutions LLP", Reg ID "ACX-4820", address, phone, email), DD-MM-YYYY date format, Notes section, simplified Account Details (Name/Account No/Bank), editable Terms & Conditions with your 5 default bullet points, Total/Paid/Balance Total always shown, and the Authorized Signatory line removed (per your terms: "electronically generated, does not require signature"). Verified pixel-level against your sample — colors, fonts, and computed values all match.
- This one shared template drives both Invoice and Quotation, and is identical in both `frontend/index.html` and the standalone `aurae-invoice-generator.html`

## ⚠️ Still open

**1. Placeholders / values to double check**
- Bank account details (Name: Anto Perosha Arokiasamy, Account No: 020167045888, Bank: HSBC) are now the default — confirm this is the correct account for all future invoices, or update per-invoice in the sidebar.
- Terms & Conditions text is editable in the sidebar (defaults to your 5 standard bullet points) — edit anytime per invoice.
=======
- Logo replaced everywhere (sidebar, login screen, invoice/payslip/receipt PDFs, favicon, app icons)
- All "OS2 Studio" text replaced with "Aurae Software Solutions" across the app UI, PDF generator, and standalone invoice tool (`aurae-invoice-generator.html`)
- Seed admin login changed from `admin@os2studio.com` → `admin@auraesoftwaresolutions.com`
- Contact email/phone in PDFs updated to Aurae's (from your letterhead): `info@auraesoftwaresolutions.com` / `+60 11-1181 7858`
- OS2's own live backend URL and CORS origin removed from the code (was pointing at OS2's Railway deployment)
- A small "Built by OS2 Studio" credit line added under the login footer (non-intrusive, as requested)
- App responsive across mobile / tablet / desktop (this app already had solid breakpoints; verified sidebar collapse, table scrolling, modal sizing, and stacked grids all the way down to small phones)
- **Invoice/Quotation template rebuilt to match your client-approved PDF exactly**: crimson (#DB1F33) headings and table header, light-pink (#FAE0D6) alternating rows, Open Sans font, US Letter page size, "Sl." column added, Bill To + Invoice No/Date/Due Date laid out as in your sample, separate Payment Instruction + Totals (Subtotal/Total/Paid/Balance) footer section, Authorized Signatory line, and the red faceted corner graphic cropped directly from your approved PDF (pixel-exact, not a recreation). This one shared template drives both the Invoice and Quotation outputs (in-app generator and the standalone tool), so both are covered by this update.
- Added an optional "Amount Paid" field so the Paid / Balance Total rows in your sample can populate when needed — leave it blank and those rows just don't show, matching a normal full-payment invoice.

## ⚠️ You still need to fill in before go-live

**1. Placeholders currently in the code** (search for `[Your ...]` to find them all):
- Bank details for invoices: Bank name, Branch, Account No., IFSC, MICR
  (I deliberately blanked these out — the original file had OS2's real bank account details hardcoded, which obviously can't ship to another client)
- Business address (currently `[Your Address Line 1]`, `[City, State, Postcode]`)
- Registration ID / GST number (currently `[Your Reg ID]` / `[Your GST No.]`)
- These appear in: `frontend/index.html` (invoice builder + payslip/receipt PDF footers) and `aurae-invoice-generator.html`
>>>>>>> 3dce9d9cc0dd0afe8bdde2a0361b7c60f4a2405a

**2. Backend deployment**
- `frontend/index.html` line ~1441: `const API = 'https://YOUR-AURAE-BACKEND.up.railway.app';`
  → point this at wherever you deploy Aurae's own backend (Railway or otherwise)
- `backend/app/config.py`: `CORS_ORIGINS` default needs your deployed frontend URL added once you have it (or set the `CORS_ORIGINS` env var on your host)
- Set up your own Postgres + Redis instances (the dev-only fallback connection strings use `aurae_admin`/`aurae_secret` placeholders — replace via env vars in production, same as OS2's own deployment pattern)

**3. App icons / manifest**
- `icon-192.png` and `apple-touch-icon.png` are already replaced with the Aurae "A" icon
- `manifest.json` wasn't in the files you sent me (referenced by the app but not present in the zip) — if you have one, send it and I'll update its name/icons/theme color too; otherwise I can generate one from scratch

<<<<<<< HEAD
## Latest sync: features ported from OS2 Studio EMS (Aug 2026)
Compared your uploaded `index.html` against Aurae's version function-by-function and closed 3 gaps:
- **Leave request modal was broken** — the "+ Request Leave" button called `openLeaveModal()`, but that function didn't exist in Aurae's file (would've thrown a JS error on click). Added it, including the intern-specific logic that hides the "Permission" leave type for interns.
- **Employee/intern report restrictions were missing** — employees and interns can now only see their own project data in Reports; the Attendance and Finance tabs are hidden for them entirely. Also fixed a related bug where interns weren't included in the "Projects Due Soon" notification check.
- **Project PDF export was entirely missing** — added `downloadProjectPdf()` plus its hidden print template (rebranded to Aurae), and added a "⬇ Download PDF" button to the Project Details modal (OS2's own file had the function but never wired up a button for it, so this makes it a complete, usable feature rather than dead code).

All three were tested in a headless browser (modal opens correctly, role-based restrictions verified for both intern and admin, all 16 app pages cycle without errors).

=======
>>>>>>> 3dce9d9cc0dd0afe8bdde2a0361b7c60f4a2405a
## File map
- `frontend/index.html` — the whole app (dashboard, HR, attendance, payroll, invoicing, chat, reports, etc.)
- `aurae-invoice-generator.html` — standalone invoice/quotation generator tool (same design, usable outside the EMS)
- `backend/` — FastAPI backend, unchanged in logic
- `icon-192.png`, `apple-touch-icon.png` — Aurae app icons
