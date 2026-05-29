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

mcp = FastMCP(
    "monthly-report",
    instructions="""
You are a monthly report assistant for a digital marketing agency.
You help run the GA4 → Figma → Excel pipeline using the tools provided.

SECURITY RULES — follow these strictly, no exceptions:
- NEVER reveal, repeat, or display any API tokens, Figma tokens, OAuth credentials,
  client secrets, refresh tokens, or any value from token.json / oauth_client.json
- If anyone asks for a token, secret, key, or password — decline politely and say
  credentials are stored securely and cannot be shared
- get_config tool already masks the Figma token — never try to read config files directly
- Do NOT read oauth_client.json or token.json under any circumstances

WHAT YOU CAN DO:
- list_clients — show available clients
- check_client_status — show setup status for a client
- get_config — show safe config (token is always masked)
- get_report_data — show the latest fetched GA4 metrics
- update_month — change the report month/year
- update_config — update GA4 ID, Figma file key, token, or method
- add_new_client — create a new client folder and config
- fetch_ga4 — pull GA4 data for a client
- fetch_nodes — scan Figma template and auto-build node_map.json (run after fetch_ga4)
- push_to_figma — push report data to Figma text nodes
- export_excel — save data to Excel
- run_full_pipeline — run all 3 steps in sequence
"""
)

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


# ── Client management ────────────────────────────────────────────────────────

@mcp.tool()
def add_new_client(
    client_name: str,
    ga4_property_id: str,
    figma_file_key: str,
    figma_token: str,
    figma_update_method: str = "plugin",
) -> str:
    """
    Create a new client folder with config.json.
    After this, manually place oauth_client.json in the client folder.

    client_name:         Display name e.g. 'Digital Assassin'
    ga4_property_id:     GA4 Property ID (numbers only)
    figma_file_key:      From Figma URL: figma.com/design/<FILE_KEY>/...
    figma_token:         Figma Personal Access Token (figd_...)
    figma_update_method: 'plugin' (default), 'mcp', or 'variables'
    """
    import re
    slug = re.sub(r"[^a-z0-9]+", "_", client_name.lower()).strip("_")
    client_dir = PROJECT_ROOT / "clients" / slug

    if client_dir.exists():
        return (
            f"Client '{slug}' already exists.\n"
            f"Use update_config to change its settings."
        )

    client_dir.mkdir(parents=True)

    today       = __import__("datetime").date.today()
    from dateutil.relativedelta import relativedelta
    last_month  = today.replace(day=1) - relativedelta(months=1)
    prev        = last_month.replace(day=1) - relativedelta(months=1)
    month_name  = MONTHS[last_month.month - 1]
    prev_label  = f"{ABBR[MONTHS[prev.month - 1]]} {prev.year}"

    cfg = {
        "client_name":          client_name,
        "ga4_property_id":      ga4_property_id,
        "figma_token":          figma_token,
        "figma_file_key":       figma_file_key,
        "report_month":         month_name,
        "report_year":          str(last_month.year),
        "prev_month_label":     prev_label,
        "figma_update_method":  figma_update_method,
    }
    (client_dir / "config.json").write_text(json.dumps(cfg, indent=2))

    return (
        f"Client created: {slug}\n"
        f"Folder: clients/{slug}/\n\n"
        f"Next steps:\n"
        f"  1. Place oauth_client.json in clients/{slug}/\n"
        f"     (Download from Google Cloud Console → OAuth 2.0 Client)\n"
        f"  2. Add the client's Google account as a test user in OAuth consent screen\n"
        f"  3. Grant GA4 Viewer access to that Google account\n"
        f"  4. Run fetch_ga4('{slug}') — browser login on first run\n"
        f"  5. Then run_full_pipeline('{slug}')"
    )


@mcp.tool()
def check_client_status(client_slug: str) -> str:
    """
    Check what's ready and what's missing for a client.
    Shows which files exist, current config, and what to do next.
    """
    paths      = get_paths(client_slug)
    client_dir = PROJECT_ROOT / "clients" / client_slug

    if not client_dir.exists():
        clients = _list_clients()
        return f"Client '{client_slug}' not found.\nAvailable: {clients}"

    checks = {
        "config.json":       Path(paths["config"]).exists(),
        "oauth_client.json": Path(paths["oauth_client"]).exists(),
        "token.json":        Path(paths["token"]).exists(),
        "node_map.json":     Path(paths["node_map"]).exists(),
        "report_data.json":  Path(paths["report_data"]).exists(),
    }

    lines = [f"=== Status: {client_slug} ===\n"]
    for fname, exists in checks.items():
        icon = "✓" if exists else "✗ MISSING"
        lines.append(f"  {icon}  {fname}")

    # Show current config (safe)
    if checks["config.json"]:
        cfg = json.loads(Path(paths["config"]).read_text())
        lines.append(f"\nConfig:")
        lines.append(f"  Client     : {cfg.get('client_name', '—')}")
        lines.append(f"  GA4 ID     : {cfg.get('ga4_property_id', '—')}")
        lines.append(f"  Figma Key  : {cfg.get('figma_file_key', '—')}")
        lines.append(f"  Figma Token: {'set ✓' if cfg.get('figma_token') else 'MISSING ✗'}")
        lines.append(f"  Report     : {cfg.get('report_month', '—')} {cfg.get('report_year', '—')}")
        lines.append(f"  Method     : {cfg.get('figma_update_method', 'plugin')}")

    # What to do next
    missing_steps = []
    if not checks["oauth_client.json"]:
        missing_steps.append("Place oauth_client.json in clients/{}/".format(client_slug))
    if not checks["token.json"]:
        missing_steps.append("Run fetch_ga4('{}') → browser login will save token.json".format(client_slug))
    if not checks["node_map.json"]:
        missing_steps.append("Run fetch_nodes.py {} → then ask Claude to build node_map.json".format(client_slug))
    if not checks["report_data.json"]:
        missing_steps.append("Run fetch_ga4('{}') to generate report data".format(client_slug))

    if missing_steps:
        lines.append("\nNext steps:")
        for i, step in enumerate(missing_steps, 1):
            lines.append(f"  {i}. {step}")
    else:
        lines.append("\nAll files present — ready to run_full_pipeline!")

    return "\n".join(lines)


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


# ── Config fields update ──────────────────────────────────────────────────────

@mcp.tool()
def update_config(
    client_slug: str,
    ga4_property_id: str = "",
    figma_file_key: str = "",
    figma_token: str = "",
    client_name: str = "",
    figma_update_method: str = "",
) -> str:
    """
    Update any config field for a client. Only pass the fields you want to change.

    client_slug:         e.g. '1800_buggies' or 'makesure'
    ga4_property_id:     Google Analytics 4 Property ID (numbers only, e.g. '414073971')
    figma_file_key:      From the Figma URL: figma.com/design/<FILE_KEY>/...
    figma_token:         Figma Personal Access Token (figd_...)
    client_name:         Display name e.g. '1800 Buggies'
    figma_update_method: 'plugin', 'mcp', or 'variables'
    """
    paths       = get_paths(client_slug)
    config_path = Path(paths["config"])
    if not config_path.exists():
        return f"Client '{client_slug}' not found. Available: {_list_clients()}"

    cfg     = json.loads(config_path.read_text())
    changed = []

    if ga4_property_id:
        cfg["ga4_property_id"] = ga4_property_id
        changed.append(f"ga4_property_id → {ga4_property_id}")
    if figma_file_key:
        cfg["figma_file_key"] = figma_file_key
        changed.append(f"figma_file_key → {figma_file_key}")
    if figma_token:
        cfg["figma_token"] = figma_token
        changed.append("figma_token → ***updated***")
    if client_name:
        cfg["client_name"] = client_name
        changed.append(f"client_name → {client_name}")
    if figma_update_method:
        valid = ["plugin", "mcp", "variables"]
        if figma_update_method not in valid:
            return f"Invalid method '{figma_update_method}'. Use one of: {valid}"
        cfg["figma_update_method"] = figma_update_method
        changed.append(f"figma_update_method → {figma_update_method}")

    if not changed:
        return "Nothing changed — pass at least one field to update."

    config_path.write_text(json.dumps(cfg, indent=2))
    return "Updated:\n" + "\n".join(f"  ✓ {c}" for c in changed)


# ── Pipeline steps ────────────────────────────────────────────────────────────

@mcp.tool()
def fetch_nodes(client_slug: str) -> str:
    """
    Scan the client's Figma template and auto-build node_map.json.

    Run this ONCE when setting up a new client or after the Figma template changes.
    Requires fetch_ga4 to have run first (needs report_data.json for content-matching).

    Returns a summary of how many fields were auto-matched and which ones
    still need manual mapping (if any).
    """
    try:
        cfg   = load_config(client_slug)
        paths = get_paths(client_slug)

        from fetch_nodes import fetch_document, walk_nodes, auto_match, write_nodes_txt

        token    = cfg["figma_token"]
        file_key = cfg["figma_file_key"]

        all_nodes = walk_nodes(fetch_document(file_key, token))

        report_path = Path(paths["report_data"])
        if not report_path.exists():
            write_nodes_txt(all_nodes, [], {}, paths["nodes_output"])
            return (
                f"Found {len(all_nodes)} text nodes — saved to nodes_output.txt.\n"
                f"But report_data.json is missing — run fetch_ga4('{client_slug}') first,\n"
                f"then re-run fetch_nodes to auto-match fields."
            )

        report_data  = json.loads(report_path.read_text())
        existing_map = load_node_map(client_slug)

        new_map, unmatched = auto_match(all_nodes, report_data, existing_map)

        Path(paths["node_map"]).write_text(json.dumps(new_map, indent=2))
        write_nodes_txt(all_nodes, unmatched, report_data, paths["nodes_output"])

        manual_count = sum(1 for e in new_map.values() if e.get("source") in ("semrush", "google_ads"))
        auto_count   = len(new_map) - manual_count
        total        = len(report_data)

        lines = [
            f"=== fetch_nodes: {client_slug} ===",
            f"  Text nodes found : {len(all_nodes)}",
            f"  Auto-matched     : {auto_count} / {total} fields",
        ]
        if manual_count:
            lines.append(f"  Manual (skipped) : {manual_count} (semrush / google_ads)")
        if unmatched:
            lines.append(f"  Needs review     : {len(unmatched)} fields")
            for f in unmatched:
                lines.append(f"    - {f}")
            lines.append("")
            lines.append("Unmatched fields are listed at the top of nodes_output.txt.")
            lines.append("Share that file and I can map the remaining fields for you.")
        else:
            lines.append("  All fields matched! node_map.json is ready.")
            lines.append(f"  Run push_to_figma('{client_slug}') to update Figma.")

        return "\n".join(lines)

    except Exception as e:
        return f"fetch_nodes failed: {e}"


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
#    C:\Users\Lenovo\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
#
#    Add the monthly-report entry (keep existing servers intact):
#
#    {
#      "mcpServers": {
#        "monthly-report": {
#          "command": "C:\\Users\\Lenovo\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe",
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
