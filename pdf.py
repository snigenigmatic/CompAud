"""
CompAud — Compliance PDF Downloader
=======================================
Downloads all source PDFs for: CERT-In, DPDP, PCI-DSS, RBI (IT Governance + PA MD)

Run:
    pip install requests tqdm
    python download_compliance_pdfs.py

All PDFs land in ./compliance_pdfs/ ready to upload to Claude for rule extraction.
"""

import os
import sys
import time
import requests
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

OUTPUT_DIR = Path("compliance_pdfs")
TIMEOUT    = 30   # seconds per request
MAX_RETRY  = 3
DELAY      = 2    # seconds between retries

SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}

# ─────────────────────────────────────────────
# PDF MANIFEST
# Each entry: (framework, short_name, filename, pdf_url, referer_url_or_None)
# ─────────────────────────────────────────────

PDFS = [

    # ── CERT-In ──────────────────────────────────────────────────────────────
    (
        "CERT-In",
        "Primary Directions (70B) — April 2022",
        "certin_directions_70b_apr2022.pdf",
        "https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf",
        "https://www.cert-in.org.in/Directions70B.jsp",
    ),
    (
        "CERT-In",
        "Extension & MSME Clarification — June 2022",
        "certin_extension_msme_jun2022.pdf",
        "https://www.cert-in.org.in/PDF/CERT-In_directions_extension_MSMEs_and_validation_27.06.2022.pdf",
        "https://www.cert-in.org.in/Directions70B.jsp",
    ),

    # ── DPDP ─────────────────────────────────────────────────────────────────
    (
        "DPDP",
        "DPDP Rules 2025 — Official Gazette Text (English)",
        "dpdp_rules_2025_gazette.pdf",
        "https://www.dpdpa.com/DPDP_Rules_2025_English_only.pdf",
        "https://www.dpdpa.com",
    ),
    (
        "DPDP",
        "EY Practical Summary — DPDP Rules 2025",
        "dpdp_rules_2025_ey_summary.pdf",
        "https://www.ey.com/content/dam/ey-unified-site/ey-com/en-in/insights/cybersecurity/documents/2025/01/ey-india-dpdp-rules-2025-v1.pdf",
        "https://www.ey.com/en_in/insights/cybersecurity",
    ),
    (
        "DPDP",
        "Grant Thornton DPDP Brochure — Nov 2025",
        "dpdp_rules_2025_grant_thornton.pdf",
        "https://www.grantthornton.in/globalassets/1.-member-firms/india/assets/pdfs/flyers/dpdpa-rules-detailed-brochure_final-25th-november-2025-1.pdf",
        "https://www.grantthornton.in",
    ),

    # ── PCI-DSS ───────────────────────────────────────────────────────────────
    (
        "PCI-DSS",
        "PCI DSS v4.0.1 Full Standard",
        "pci_dss_v4_0_1_full.pdf",
        "https://www.middlebury.edu/sites/default/files/2025-01/PCI-DSS-v4_0_1.pdf",
        "https://www.middlebury.edu",
    ),
    (
        "PCI-DSS",
        "PCI DSS v3.2.1 → v4.0 Summary of Changes",
        "pci_dss_v3_to_v4_changes.pdf",
        "https://docs-prv.pcisecuritystandards.org/PCI%20DSS/Standard/PCI-DSS-v3-2-1-to-v4-0-Summary-of-Changes-r2.pdf",
        "https://www.pcisecuritystandards.org",
    ),

    # ── RBI ───────────────────────────────────────────────────────────────────
    (
        "RBI",
        "IT Governance, Risk, Controls & Assurance Practices MD — Nov 2023",
        "rbi_itgrc_master_direction_2023.pdf",
        "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/107MDITGOVERNANCE3303572008604C67AC25B84292D85567.PDF",
        "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12562",
    ),
    (
        "RBI",
        "Payment Aggregator Master Direction — Sep 2025 (Press Release PDF)",
        "rbi_payment_aggregator_md_2025.pdf",
        "https://rbidocs.rbi.org.in/rdocs/PressRelease/PDFs/PR1102D0FE3DE1880B4E26BE4CC5184F8F8D7C.PDF",
        "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12896",
    ),
    (
        "RBI",
        "Authentication Mechanisms for Digital Payments — Sep 2025 (KPMG Summary)",
        "rbi_2fa_directions_2025_kpmg.pdf",
        "https://assets.kpmg.com/content/dam/kpmgsites/in/pdf/2025/12/reserve-bank-of-india-rbi-authentication-mechanisms-for-digital-payment-transactions-directions-2025.pdf.coredownload.pdf",
        "https://kpmg.com/in",
    ),

]

# ─────────────────────────────────────────────
# FALLBACK URLS
# If the primary URL fails, try these in order.
# Only defined for the most likely to 403.
# ─────────────────────────────────────────────

FALLBACKS = {
    "pci_dss_v4_0_1_full.pdf": [
        # PCI SSC official (requires free account — may redirect to login)
        "https://docs-prv.pcisecuritystandards.org/PCI%20DSS/Standard/PCI-DSS-v4_0_1.pdf",
    ],
    "certin_directions_70b_apr2022.pdf": [
        # AZB Partners cached version
        "https://www.azbpartners.com/wp-content/uploads/2022/05/CERT-In-Directions-28042022.pdf",
    ],
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def sizeof_fmt(num):
    for unit in ("B", "KB", "MB"):
        if abs(num) < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"


def download(session, url, dest_path, referer=None, attempt=1):
    headers = {}
    if referer:
        headers["Referer"] = referer

    try:
        r = session.get(url, headers=headers, timeout=TIMEOUT,
                        stream=True, allow_redirects=True)
        r.raise_for_status()

        # Verify it's actually a PDF
        content = b""
        for chunk in r.iter_content(chunk_size=8192):
            content += chunk

        if not content.startswith(b"%PDF"):
            return False, f"Response is not a PDF (got: {content[:20]!r})"

        dest_path.write_bytes(content)
        return True, sizeof_fmt(len(content))

    except requests.HTTPError as e:
        return False, f"HTTP {e.response.status_code}"
    except requests.ConnectionError as e:
        return False, f"Connection error: {str(e)[:60]}"
    except requests.Timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)[:80]


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    session = requests.Session()
    session.headers.update(SESSION_HEADERS)

    results = []
    print(f"\n{'='*65}")
    print(f"  CompAud — Compliance PDF Downloader")
    print(f"  Output: {OUTPUT_DIR.resolve()}")
    print(f"{'='*65}\n")

    for framework, desc, filename, url, referer in PDFS:
        dest = OUTPUT_DIR / filename

        # Skip if already downloaded
        if dest.exists() and dest.stat().st_size > 1000:
            size = sizeof_fmt(dest.stat().st_size)
            print(f"  [SKIP] {framework} — {desc}")
            print(f"         Already exists ({size})\n")
            results.append((framework, filename, "skipped", size))
            continue

        print(f"  [....] {framework} — {desc}")
        print(f"         {url}")

        success, info = False, ""
        for attempt in range(1, MAX_RETRY + 1):
            success, info = download(session, url, dest, referer, attempt)
            if success:
                break
            print(f"         Attempt {attempt}/{MAX_RETRY} failed: {info}")
            if attempt < MAX_RETRY:
                time.sleep(DELAY)

        # Try fallbacks if primary failed
        if not success and filename in FALLBACKS:
            print(f"         Trying fallback URLs...")
            for fb_url in FALLBACKS[filename]:
                success, info = download(session, fb_url, dest, referer=None)
                if success:
                    print(f"         Fallback succeeded: {fb_url}")
                    break

        status = "OK  " if success else "FAIL"
        icon   = "✓" if success else "✗"
        print(f"         {icon} {status} — {info}\n")
        results.append((framework, filename, "ok" if success else "failed", info))

    # ── Summary ──────────────────────────────
    print(f"{'='*65}")
    print(f"  DOWNLOAD SUMMARY")
    print(f"{'='*65}")

    ok      = [r for r in results if r[2] == "ok"]
    skipped = [r for r in results if r[2] == "skipped"]
    failed  = [r for r in results if r[2] == "failed"]

    print(f"  Downloaded : {len(ok)}")
    print(f"  Skipped    : {len(skipped)}  (already on disk)")
    print(f"  Failed     : {len(failed)}")

    if failed:
        print(f"\n  FAILED — download these manually:")
        for fw, fn, _, reason in failed:
            print(f"    [{fw}] {fn}")
            print(f"           Reason: {reason}")

    if ok or skipped:
        print(f"\n  Files ready in: {OUTPUT_DIR.resolve()}/")
        for fw, fn, status, info in results:
            marker = "✓" if status in ("ok", "skipped") else "✗"
            tag = "(already existed)" if status == "skipped" else info
            print(f"    {marker} {fn}  [{tag}]")

    print(f"\n  Next step: upload the PDFs in compliance_pdfs/ to Claude")
    print(f"  and run the extraction prompt from the playbook.\n")


if __name__ == "__main__":
    main()