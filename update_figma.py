"""
Called by run_report.py — pushes all formatted field values into Figma variables.
Figma text nodes auto-update because they are bound to these variables.
"""
import json
import requests


def update_figma_variables(report_data: dict, config: dict):
    with open("figma_vars.json") as f:
        figma_vars = json.load(f)

    TOKEN    = config["figma_token"]
    FILE_KEY = config["figma_file_key"]
    mode_id  = figma_vars["mode_id"]
    var_ids  = figma_vars["variables"]
    HEADERS  = {"X-Figma-Token": TOKEN, "Content-Type": "application/json"}

    mode_values = []
    skipped     = []

    for field_name, value in report_data.items():
        var_id = var_ids.get(field_name)
        if not var_id:
            skipped.append(field_name)
            continue
        mode_values.append({
            "variableId": var_id,
            "modeId":     mode_id,
            "value":      str(value),
        })

    payload = {"variableModeValues": mode_values}

    resp = requests.post(
        f"https://api.figma.com/v1/files/{FILE_KEY}/variables",
        headers=HEADERS,
        json=payload
    )

    if resp.status_code == 200:
        print(f"Figma updated — {len(mode_values)} fields pushed.")
    else:
        print(f"Figma update failed: {resp.status_code}")
        print(resp.text)

    if skipped:
        print(f"Skipped (no variable ID): {skipped}")
