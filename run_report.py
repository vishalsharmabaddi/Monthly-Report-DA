"""
Monthly runner — run this every month to update the Figma report and save Excel.
Usage: py run_report.py
"""
import json
import os
import sys
import urllib.request
import urllib.parse


NEW_TEMPLATE_MSG = """
  node_map.json is missing or your Figma template has changed significantly.

  Run this ONCE to map your new Figma nodes:
  ──────────────────────────────────────────────────
  1. Make sure your Figma file is open in the browser
  2. Open Claude Code in this project folder
  3. Run:  py fetch_nodes.py
  4. Then say to Claude:
       "Map my Figma nodes to report fields using nodes_output.txt"
  5. Claude will update node_map.json automatically
  6. Re-run:  py run_report.py
  ──────────────────────────────────────────────────
  NOTE: This step is only needed when the Figma template
  structure changes. For new months or new clients using
  the same template, this step is skipped automatically.
"""


def validate_node_map(config):
    """Returns (is_valid, message). Checks node_map.json exists and nodes are live in Figma."""

    if not os.path.exists("node_map.json"):
        return False, NEW_TEMPLATE_MSG

    with open("node_map.json") as f:
        node_map = json.load(f)

    if not node_map:
        return False, NEW_TEMPLATE_MSG

    # Collect node IDs — skip manual fields (semrush / google_ads)
    node_ids = [
        v["node_id"] for v in node_map.values()
        if v.get("source") not in ("semrush", "google_ads")
    ]

    if not node_ids:
        return False, NEW_TEMPLATE_MSG

    # Verify nodes exist in Figma
    ids_param = urllib.parse.quote(",".join(node_ids))
    req = urllib.request.Request(
        f'https://api.figma.com/v1/files/{config["figma_file_key"]}/nodes?ids={ids_param}',
        headers={"X-Figma-Token": config["figma_token"]}
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read())
    except Exception as e:
        print(f"      Warning: Could not reach Figma API ({e}). Skipping validation.")
        return True, ""

    found = set(data.get("nodes", {}).keys())
    missing = [nid for nid in node_ids if nid not in found]
    missing_pct = len(missing) / len(node_ids)

    if missing_pct > 0.5:
        return False, NEW_TEMPLATE_MSG
    elif missing:
        print(f"      Warning: {len(missing)} node(s) not found in Figma — they will be skipped.")

    return True, ""


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

    # ── Step 0: Validate node map ─────────────────
    print("[0/3] Checking Figma node map...")
    valid, msg = validate_node_map(config)
    if not valid:
        print()
        print("=" * 50)
        print("  NEW TEMPLATE DETECTED")
        print("=" * 50)
        print(msg)
        sys.exit(0)
    print("      node_map.json is valid. Ready to update Figma.")
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
    print()
    print("[2/3] Updating Figma...")
    from update_figma import update_figma
    update_figma(report_data, config)
    # TODO: Chunk 2 will rewrite update_figma.py with plugin/MCP/variables support

    # ── Step 3: Export to Excel ───────────────────
    print("[3/3] Exporting to Excel...")
    from export_excel import export_to_excel
    export_to_excel(report_data, config)

    print()
    print("Done! Open Figma and export your report as PDF.")
    print("=" * 50)


if __name__ == "__main__":
    main()
