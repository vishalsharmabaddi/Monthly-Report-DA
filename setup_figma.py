"""
Run ONCE per client to create Figma string variables for every report field.
Saves variable IDs to clients/{client}/figma_vars.json — needed by run_report.py each month.
After this, open Figma desktop and bind text nodes to variables (one-time step).

Usage:
  py setup_figma.py               — shows client selector menu
  py setup_figma.py makesure      — runs for a specific client
"""
import json
import sys
import requests
from client_utils import resolve_client, get_paths, load_config, load_node_map

client   = resolve_client(sys.argv[1] if len(sys.argv) > 1 else None)
paths    = get_paths(client)
config   = load_config(client)
node_map = load_node_map(client)

TOKEN    = config["figma_token"]
FILE_KEY = config["figma_file_key"]
HEADERS  = {"X-Figma-Token": TOKEN, "Content-Type": "application/json"}

# ── Build variable create payload ─────────────────────────────────────────────
COLLECTION_TEMP_ID = "temp_collection_1"
MODE_TEMP_ID       = "temp_mode_1"

variables_payload = []
for field_name in node_map:
    variables_payload.append({
        "action": "CREATE",
        "id": f"temp_{field_name}",
        "name": field_name,
        "variableCollectionId": COLLECTION_TEMP_ID,
        "resolvedType": "STRING",
    })

payload = {
    "variableCollections": [{
        "action": "CREATE",
        "id": COLLECTION_TEMP_ID,
        "name": "Monthly Report Data",
        "initialModeId": MODE_TEMP_ID,
    }],
    "variables": variables_payload,
    "variableModeValues": [],
}

resp = requests.post(
    f"https://api.figma.com/v1/files/{FILE_KEY}/variables",
    headers=HEADERS,
    json=payload
)

if resp.status_code != 200:
    print(f"Error: {resp.status_code}")
    print(resp.text)
    exit(1)

result = resp.json()
meta   = result.get("meta", {})

# Map temp IDs → real Figma IDs
collection_id = None
mode_id       = None
var_id_map    = {}

for temp_id, coll_data in meta.get("variableCollections", {}).items():
    collection_id = coll_data["id"]
    mode_id       = list(coll_data["modes"].values())[0]["modeId"] if isinstance(list(coll_data["modes"].values())[0], dict) else coll_data["modes"][list(coll_data["modes"].keys())[0]]
    # Handle different response structures
    if isinstance(coll_data.get("modes"), dict):
        first_mode = list(coll_data["modes"].values())[0]
        mode_id = first_mode.get("modeId") or first_mode

for temp_id, var_data in meta.get("variables", {}).items():
    field_name = temp_id.replace("temp_", "", 1)
    var_id_map[field_name] = var_data["id"]

# Save everything needed for monthly updates
output = {
    "collection_id": collection_id,
    "mode_id":       mode_id,
    "variables":     var_id_map,
}

figma_vars_path = paths["config"].replace("config.json", "figma_vars.json")
with open(figma_vars_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"Done! Created {len(var_id_map)} Figma variables.")
print(f"Collection ID : {collection_id}")
print(f"Mode ID       : {mode_id}")
print(f"Saved to      : {figma_vars_path}")
print()
print("Next steps:")
print("  1. Open Figma → each text node → bind to its variable (one-time)")
print("  2. Set figma_update_method = 'variables' in config.json")
print(f"  3. Run: py run_report.py {client}")
