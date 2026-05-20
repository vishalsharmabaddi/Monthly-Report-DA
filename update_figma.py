"""
Pushes report_data.json values into Figma text nodes.

Four methods — set "figma_update_method" in config.json:
  "plugin"     — local HTTP server + Figma dev plugin (default, free, no rate limits)
  "mcp"        — Claude AI Figma MCP (free tier, once/month is fine)
  "variables"  — Figma REST Variables API (paid Figma plan only)
  "claude_api" — Anthropic API + Figma Variables API (paid Figma + ANTHROPIC_API_KEY)
"""
import json
import os


def update_figma(report_data: dict, config: dict):
    method = config.get("figma_update_method", "plugin")
    if method == "variables":
        _update_via_variables(report_data, config)
    elif method == "claude_api":
        _update_via_claude_api(report_data, config)
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
            pass

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
        print("      Run: py setup_figma.py  (requires paid Figma plan)")
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


# ── Method 4: Claude API + Figma Variables ────────────────────────────────────

def _update_via_claude_api(report_data: dict, config: dict):
    """
    Uses Anthropic Claude API to validate + push data via Figma Variables API.
    Requires: ANTHROPIC_API_KEY in env + paid Figma plan + figma_vars.json.
    """
    try:
        import anthropic
    except ImportError:
        print("      ERROR: 'anthropic' not installed. Run: pip install anthropic")
        return

    try:
        import requests
    except ImportError:
        print("      ERROR: 'requests' not installed. Run: pip install requests")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("      ERROR: ANTHROPIC_API_KEY not found in environment.")
        print("      Add it to Streamlit Cloud secrets or your local .env file.")
        return

    if not os.path.exists("figma_vars.json"):
        print("      ERROR: figma_vars.json not found.")
        print("      Run: py setup_figma.py  (requires paid Figma plan)")
        return

    with open("figma_vars.json") as f:
        figma_vars = json.load(f)

    TOKEN    = config["figma_token"]
    FILE_KEY = config["figma_file_key"]
    mode_id  = figma_vars["mode_id"]
    var_ids  = figma_vars["variables"]
    HEADERS  = {"X-Figma-Token": TOKEN, "Content-Type": "application/json"}

    # Build field → variable ID mapping (only fields that have a variable)
    field_var_map = {
        field: var_ids[field]
        for field in report_data
        if field in var_ids
    }
    skipped = [f for f in report_data if f not in var_ids]

    # Ask Claude to validate and prepare the Figma update payload
    client = anthropic.Anthropic(api_key=api_key)

    tools = [{
        "name": "push_to_figma",
        "description": "Push validated report data values to Figma variables via REST API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode_values": {
                    "type": "array",
                    "description": "List of variable updates to send to Figma.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "variableId": {"type": "string"},
                            "modeId":     {"type": "string"},
                            "value":      {"type": "string"}
                        },
                        "required": ["variableId", "modeId", "value"]
                    }
                }
            },
            "required": ["mode_values"]
        }
    }]

    prompt = f"""You are updating a Figma design with monthly report data.

Report data (field → value):
{json.dumps(report_data, indent=2)}

Field to Figma Variable ID mapping:
{json.dumps(field_var_map, indent=2)}

Mode ID: {mode_id}

Build the mode_values array and call push_to_figma.
Each item: variableId from the mapping, modeId as given, value as string."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=tools,
        messages=[{"role": "user", "content": prompt}]
    )

    # Execute whatever tool call Claude makes
    pushed = False
    for block in response.content:
        if block.type == "tool_use" and block.name == "push_to_figma":
            mode_values = block.input.get("mode_values", [])
            resp = requests.post(
                f"https://api.figma.com/v1/files/{FILE_KEY}/variables",
                headers=HEADERS,
                json={"variableModeValues": mode_values}
            )
            if resp.status_code == 200:
                print(f"      ✓ Claude API pushed {len(mode_values)} fields to Figma.")
            else:
                print(f"      Figma update failed: {resp.status_code}")
                print(resp.text)
            pushed = True
            break

    if not pushed:
        print("      Claude did not generate a push. Check ANTHROPIC_API_KEY and figma_vars.json.")

    if skipped:
        print(f"      Skipped (no variable): {len(skipped)} fields")
