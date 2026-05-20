"""
Pushes report_data.json values into Figma text nodes.

Three methods — set "figma_update_method" in config.json:
  "plugin"    — local HTTP server + Figma dev plugin (default, free, no rate limits)
  "mcp"       — Claude AI Figma MCP (free tier, once/month is fine)
  "variables" — Figma REST Variables API (paid Figma plan only)
"""
import json
import os


def update_figma(report_data: dict, config: dict):
    method = config.get("figma_update_method", "plugin")
    if method == "variables":
        _update_via_variables(report_data, config)
    elif method == "mcp":
        _update_via_mcp()
    else:
        _update_via_plugin(report_data)


# ── Method 1: Local plugin (default) ─────────────────────────────────────────

def _update_via_plugin(report_data: dict):
    """Starts a local HTTP server. User opens the Figma dev plugin to pull and apply data."""
    import threading
    import time
    from http.server import HTTPServer, BaseHTTPRequestHandler

    with open("node_map.json") as f:
        node_map = json.load(f)

    payload = json.dumps({"report_data": report_data, "node_map": node_map}).encode()
    done_event = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.end_headers()

        def do_GET(self):
            if self.path == "/data":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(payload)
                done_event.set()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # suppress request logs

    server = HTTPServer(("localhost", 5555), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("      Server running at http://localhost:5555")
    print()
    print("      >> Open Figma -> Plugins -> Report Updater -> 'Fetch & Update All Nodes'")
    print("      Waiting up to 120 seconds for plugin...")

    if done_event.wait(timeout=120):
        time.sleep(1)
        print("      OK - Data delivered to Figma plugin.")
    else:
        print("      Timeout - plugin was not opened within 120s.")
        print("      Tip: open the plugin in Figma and re-run the script.")

    server.shutdown()


# ── Method 2: Claude MCP ──────────────────────────────────────────────────────

def _update_via_mcp():
    """Instructs user to trigger the Figma MCP push via Claude."""
    print("      report_data.json is ready.")
    print()
    print("      >> Tell Claude: 'push to figma'")
    print("         Claude will read report_data.json + node_map.json")
    print("         and push all values via the Figma MCP.")


# ── Method 3: Figma Variables API (paid plan) ─────────────────────────────────

def _update_via_variables(report_data: dict, config: dict):
    """Uses Figma REST Variables API. Requires paid Figma plan + figma_vars.json."""
    try:
        import requests
    except ImportError:
        print("      ERROR: 'requests' not installed. Run: pip install requests")
        return

    if not os.path.exists("figma_vars.json"):
        print("      ERROR: figma_vars.json not found.")
        print("      This method requires a paid Figma plan.")
        print("      Switch to 'plugin' method in config.json to use the free option.")
        return

    with open("figma_vars.json") as f:
        figma_vars = json.load(f)

    TOKEN    = config["figma_token"]
    FILE_KEY = config["figma_file_key"]
    mode_id  = figma_vars["mode_id"]
    var_ids  = figma_vars["variables"]
    HEADERS  = {"X-Figma-Token": TOKEN, "Content-Type": "application/json"}

    mode_values, skipped = [], []
    for field, value in report_data.items():
        var_id = var_ids.get(field)
        if not var_id:
            skipped.append(field)
            continue
        mode_values.append({"variableId": var_id, "modeId": mode_id, "value": str(value)})

    resp = requests.post(
        f"https://api.figma.com/v1/files/{FILE_KEY}/variables",
        headers=HEADERS,
        json={"variableModeValues": mode_values}
    )

    if resp.status_code == 200:
        print(f"      ✓ Figma updated — {len(mode_values)} fields pushed.")
    else:
        print(f"      Figma update failed: {resp.status_code}")
        print(resp.text)

    if skipped:
        print(f"      Skipped (no variable ID): {len(skipped)} fields")
