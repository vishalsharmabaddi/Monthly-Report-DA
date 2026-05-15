"""
Monthly runner — run this every month to update the Figma report and save Excel.
Usage: py run_report.py
"""
import json
import os
import sys


def main():
    print("=" * 50)
    print("Monthly Report Automation")
    print("=" * 50)

    # ── Load config ───────────────────────────────
    with open("config.json") as f:
        config = json.load(f)

    print(f"Client  : {config['client_name']}")
    print(f"Report  : {config['report_month']} {config['report_year']}")
    print()

    # ── Step 1: Fetch GA4 data ─────────────────────
    if not os.path.exists("oauth_client.json"):
        print("ERROR: oauth_client.json not found.")
        print("Download it from Google Cloud Console → Credentials → OAuth 2.0 Client.")
        sys.exit(1)

    print("[1/3] Fetching GA4 data...")
    from fetch_ga4 import fetch_ga4_data
    report_data = fetch_ga4_data(config)

    with open("report_data.json", "w") as f:
        json.dump(report_data, f, indent=2)
    print(f"      {len(report_data)} fields fetched.")

    # ── Step 2: Update Figma ──────────────────────
    if not os.path.exists("figma_vars.json"):
        print()
        print("[2/3] Figma variables not set up yet.")
        print("      Run setup_figma.py first, then ask Claude to bind text nodes.")
        print("      Skipping Figma update for now.")
    else:
        print("[2/3] Updating Figma variables...")
        from update_figma import update_figma_variables
        update_figma_variables(report_data, config)

    # ── Step 3: Export to Excel ───────────────────
    print("[3/3] Exporting to Excel...")
    from export_excel import export_to_excel
    export_to_excel(report_data, config)

    print()
    print("Done! Open Figma and export your report as PDF.")
    print("=" * 50)


if __name__ == "__main__":
    main()
