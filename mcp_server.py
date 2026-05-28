"""
MCP server for Monthly Report Automation.

Non-developers: Connect Claude Desktop to this server once,
then just chat in plain language — Claude runs the pipeline for you.

Setup instructions at bottom of this file.
"""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from mcp.server.fastmcp import FastMCP
from client_utils import list_clients as _list_clients, get_paths, load_config, load_node_map

mcp = FastMCP("monthly-report")

MONTHS = ["January","February","March","April","May","June",
          "July","August","September","October","November","December"]
ABBR   = {"January":"Jan","February":"Feb","March":"Mar","April":"Apr",
          "May":"May","June":"Jun","July":"Jul","August":"Aug",
          "September":"Sep","October":"Oct","November":"Nov","December":"Dec"}


# ── Client info ───────────────────────────────────────────────────────────────

@mcp.tool()
def list_clients() -> list[str]:
    """List all available client slugs (folder names under clients/)."""
    clients = _list_clients()
    if not clients:
        return ["No clients found. Add a client folder under clients/."]
    return clients


@mcp.tool()
def get_config(client_slug: str) -> dict:
    """
    Get the current report config for a client.
    Shows: client name, report month/year, GA4 property ID, Figma file key.
    Figma token is hidden for security.
    """
    try:
        cfg  = load_config(client_slug)
        safe = {k: v for k, v in cfg.items() if "token" not in k}
        safe["figma_token"] = "***hidden***"
        return safe
    except FileNotFoundError:
        return {"error": f"Client '{client_slug}' not found. Available: {_list_clients()}"}


@mcp.tool()
def get_report_data(client_slug: str) -> dict:
    """
    Show the most recently fetched GA4 report data for a client.
    Returns all 47 metrics (sessions, users, bounce rate, conversions, etc.).
    Run fetch_ga4 first if you get an error.
    """
    paths       = get_paths(client_slug)
    report_path = Path(paths["report_data"])
    if not report_path.exists():
        return {"error": "No data yet. Run fetch_ga4 first."}
    return json.loads(report_path.read_text())


# ── Config management ─────────────────────────────────────────────────────────

@mcp.tool()
def update_month(client_slug: str, month: str, year: str) -> str:
    """
    Update the report month and year for a client.
    month: full English month name e.g. 'May', 'January'
    year:  4-digit string e.g. '2026'
    """
    if month not in MONTHS:
        return f"Invalid month '{month}'. Use full English name e.g. 'May'."

    paths       = get_paths(client_slug)
    config_path = Path(paths["config"])
    if not config_path.exists():
        return f"Client '{client_slug}' not found."

    cfg        = json.loads(config_path.read_text())
    idx        = MONTHS.index(month)
    prev_month = MONTHS[(idx - 1) % 12]
    prev_year  = int(year) if idx > 0 else int(year) - 1

    cfg["report_month"]     = month
    cfg["report_year"]      = str(year)
    cfg["prev_month_label"] = f"{ABBR[prev_month]} {prev_year}"
    config_path.write_text(json.dumps(cfg, indent=2))

    return f"Updated: {month} {year}  |  prev label: {ABBR[prev_month]} {prev_year}"


# ── Pipeline steps ────────────────────────────────────────────────────────────

@mcp.tool()
def fetch_ga4(client_slug: str) -> str:
    """
    Fetch Google Analytics 4 data for the client's current report month.
    Saves 47 formatted metrics to clients/{client_slug}/report_data.json.
    First run ever: opens a browser for Google login (saved after that).
    """
    try:
        cfg   = load_config(client_slug)
        paths = get_paths(client_slug)

        if not Path(paths["oauth_client"]).exists():
            return (
                f"ERROR: oauth_client.json not found at {paths['oauth_client']}\n"
                "Fix: Download from Google Cloud Console → Credentials → "
                "OAuth 2.0 Client (Desktop) and place it there."
            )

        from fetch_ga4 import fetch_ga4_data
        report_data = fetch_ga4_data(cfg, paths["token"], paths["oauth_client"])
        Path(paths["report_data"]).write_text(json.dumps(report_data, indent=2))

        return (
            f"Done. {len(report_data)} fields fetched.\n"
            f"Client: {cfg['client_name']}  |  {cfg['report_month']} {cfg['report_year']}"
        )
    except Exception as e:
        return f"GA4 fetch failed: {e}"


@mcp.tool()
def push_to_figma(client_slug: str) -> str:
    """
    Push report data into Figma text nodes via the local plugin.

    BEFORE running this tool:
    1. Open Figma Desktop
    2. Open the client's report file
    3. Go to Plugins → Report Updater → click 'Fetch & Update All Nodes'
    The plugin must be open — this tool waits up to 120 seconds for it.
    """
    try:
        paths       = get_paths(client_slug)
        report_path = Path(paths["report_data"])

        if not report_path.exists():
            return "ERROR: No report data found. Run fetch_ga4 first."

        cfg         = load_config(client_slug)
        node_map    = load_node_map(client_slug)
        report_data = json.loads(report_path.read_text())

        import io
        import contextlib
        from update_figma import update_figma

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            update_figma(report_data, cfg, node_map)

        return buf.getvalue().strip() or "Figma update complete."
    except Exception as e:
        return f"Figma push failed: {e}"


@mcp.tool()
def export_excel(client_slug: str) -> str:
    """
    Append this month's report data to data/monthly_reports.xlsx.
    Creates the file on first run. Run fetch_ga4 first.
    """
    try:
        paths       = get_paths(client_slug)
        report_path = Path(paths["report_data"])

        if not report_path.exists():
            return "ERROR: No report data found. Run fetch_ga4 first."

        cfg         = load_config(client_slug)
        report_data = json.loads(report_path.read_text())

        import io
        import contextlib
        from export_excel import export_to_excel

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            export_to_excel(report_data, cfg)

        return buf.getvalue().strip() or "Saved to data/monthly_reports.xlsx"
    except Exception as e:
        return f"Excel export failed: {e}"


@mcp.tool()
def run_full_pipeline(client_slug: str) -> str:
    """
    Run the complete monthly report pipeline in one go:
    Step 1 → Fetch GA4 data
    Step 2 → Push to Figma  (have the plugin open BEFORE running this)
    Step 3 → Export to Excel

    Stops and reports the error if any step fails.
    """
    lines = []

    lines.append(f"=== Pipeline: {client_slug} ===\n")

    lines.append("[ 1/3 ] Fetching GA4 data...")
    r1 = fetch_ga4(client_slug)
    lines.append(r1)
    if "failed" in r1.lower() or "error" in r1.lower():
        lines.append("\nStopped — fix the GA4 error above and retry.")
        return "\n".join(lines)

    lines.append("\n[ 2/3 ] Pushing to Figma...")
    lines.append("(Make sure Figma plugin is open and waiting)")
    r2 = push_to_figma(client_slug)
    lines.append(r2)

    lines.append("\n[ 3/3 ] Exporting Excel...")
    r3 = export_excel(client_slug)
    lines.append(r3)

    lines.append("\nAll done. Open Figma and export PDF.")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SETUP — Run once to connect Claude Desktop to this server
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 1. Install the MCP package:
#    pip install mcp
#
# 2. Open this file in your editor:
#    C:\Users\Lenovo\AppData\Roaming\Claude\claude_desktop_config.json
#
#    If it doesn't exist, create it. Add:
#
#    {
#      "mcpServers": {
#        "monthly-report": {
#          "command": "py",
#          "args": ["C:\\Users\\Lenovo\\Desktop\\Report monthly dy\\mcp_server.py"],
#          "cwd": "C:\\Users\\Lenovo\\Desktop\\Report monthly dy"
#        }
#      }
#    }
#
# 3. Restart Claude Desktop completely.
#
# 4. Open a new chat in Claude Desktop.
#    You should see a hammer icon (🔨) — that means MCP is connected.
#
# 5. Try typing:
#    "List my clients"
#    "Fetch GA4 data for 1800_buggies"
#    "Run full pipeline for makesure"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
