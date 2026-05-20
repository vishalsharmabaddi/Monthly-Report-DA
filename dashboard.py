"""
Monthly report dashboard.
Run: streamlit run dashboard.py
"""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Report Dashboard", page_icon="📊", layout="wide")

CLIENTS_DIR = Path("clients")
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_ABBR = {
    "January": "Jan", "February": "Feb", "March": "Mar", "April": "Apr",
    "May": "May", "June": "Jun", "July": "Jul", "August": "Aug",
    "September": "Sep", "October": "Oct", "November": "Nov", "December": "Dec",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_clients() -> dict:
    CLIENTS_DIR.mkdir(exist_ok=True)
    clients = {}
    for f in sorted(CLIENTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            clients[data.get("client_name", f.stem)] = f
        except Exception:
            pass
    return clients


def load_config() -> dict:
    with open("config.json") as f:
        return json.load(f)


def save_config(cfg: dict):
    with open("config.json", "w") as f:
        json.dump(cfg, f, indent=2)


def save_client(cfg: dict) -> Path:
    CLIENTS_DIR.mkdir(exist_ok=True)
    slug = cfg["client_name"].lower().replace(" ", "_").replace("/", "_")
    path = CLIENTS_DIR / f"{slug}.json"
    path.write_text(json.dumps(cfg, indent=2))
    return path


def build_config(cfg_base, client_name, ga4_id, figma_key, figma_token,
                 month, year, method) -> dict:
    month_idx = MONTHS.index(month)
    prev_month = MONTHS[(month_idx - 1) % 12]
    prev_year = int(year) if month_idx > 0 else int(year) - 1
    return {
        "ga4_property_id": ga4_id,
        "figma_token": figma_token,
        "figma_file_key": figma_key,
        "credentials_path": cfg_base.get("credentials_path", "credentials.json"),
        "report_month": month,
        "report_year": str(year),
        "prev_month_label": f"{MONTH_ABBR[prev_month]} {prev_year}",
        "client_name": client_name,
        "figma_update_method": method,
    }


# ── Sidebar ───────────────────────────────────────────────────────────────────

clients = load_clients()
client_names = list(clients.keys())
cfg = load_config()

with st.sidebar:
    st.title("Config")

    if client_names:
        current_name = cfg.get("client_name", client_names[0])
        default_idx = client_names.index(current_name) if current_name in client_names else 0
        selected = st.selectbox("Client", client_names, index=default_idx)
        if st.button("Load Client", use_container_width=True):
            loaded = json.loads(clients[selected].read_text())
            save_config(loaded)
            st.success(f"Loaded {selected}")
            st.rerun()
    else:
        st.info("No clients saved yet. Fill in the fields and click 'Save Client'.")

    st.divider()

    client_name = st.text_input("Client Name", cfg.get("client_name", ""))
    ga4_id      = st.text_input("GA4 Property ID", cfg.get("ga4_property_id", ""))
    figma_key   = st.text_input("Figma File Key", cfg.get("figma_file_key", ""))
    figma_token = st.text_input("Figma Token", cfg.get("figma_token", ""), type="password")

    month_val = cfg.get("report_month", "January")
    month = st.selectbox(
        "Month", MONTHS,
        index=MONTHS.index(month_val) if month_val in MONTHS else 0,
    )
    year = st.text_input("Year", cfg.get("report_year", "2026"))

    method_opts = ["plugin", "mcp", "variables"]
    method = st.selectbox(
        "Figma Update Method", method_opts,
        index=method_opts.index(cfg.get("figma_update_method", "plugin")),
    )

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Save Config", use_container_width=True):
            new_cfg = build_config(cfg, client_name, ga4_id, figma_key,
                                   figma_token, month, year, method)
            save_config(new_cfg)
            st.success("Saved!")
            st.rerun()
    with col_b:
        if st.button("Save Client", use_container_width=True):
            new_cfg = build_config(cfg, client_name, ga4_id, figma_key,
                                   figma_token, month, year, method)
            save_config(new_cfg)
            path = save_client(new_cfg)
            st.success(f"Saved {path.name}")
            st.rerun()


# ── Main header ───────────────────────────────────────────────────────────────

cfg = load_config()
st.title(f"{cfg['client_name']} — {cfg['report_month']} {cfg['report_year']}")
st.caption(
    f"GA4: `{cfg['ga4_property_id']}` | "
    f"Figma: `{cfg['figma_file_key']}` | "
    f"Method: `{cfg.get('figma_update_method', 'plugin')}`"
)
st.divider()


# ── Action buttons ────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

# ── Fetch GA4 ────────────────────
with col1:
    if st.button("Fetch GA4 Data", use_container_width=True, type="primary"):
        if not os.path.exists("oauth_client.json"):
            st.error("oauth_client.json not found.\nDownload from Google Cloud Console.")
        else:
            with st.spinner("Fetching GA4 data..."):
                try:
                    sys.path.insert(0, str(Path(__file__).parent))
                    from fetch_ga4 import fetch_ga4_data
                    report_data = fetch_ga4_data(cfg)
                    with open("report_data.json", "w") as f:
                        json.dump(report_data, f, indent=2)
                    st.session_state["report_data"] = report_data
                    st.success(f"{len(report_data)} fields fetched and saved.")
                except Exception as e:
                    st.error(f"GA4 error: {e}")

# ── Push to Figma ────────────────
with col2:
    if st.button("Push to Figma", use_container_width=True, type="primary"):
        push_method = cfg.get("figma_update_method", "plugin")

        if push_method == "mcp":
            st.info(
                "**report_data.json is ready.**\n\n"
                "Tell Claude: **'push to figma'**\n\n"
                "Claude will read report_data.json + node_map.json and push all values."
            )
        elif not os.path.exists("report_data.json"):
            st.warning("Run **Fetch GA4 Data** first.")
        else:
            with open("report_data.json") as f:
                report_data = json.load(f)

            if push_method == "plugin":
                st.info(
                    "Server starting at **localhost:5555** (120s window).\n\n"
                    ">> Open Figma → Plugins → Report Updater → **Fetch & Update All Nodes**"
                )

            buf = io.StringIO()
            with st.spinner("Pushing to Figma..." if push_method != "plugin" else "Waiting for Figma plugin..."):
                try:
                    from update_figma import update_figma
                    with contextlib.redirect_stdout(buf):
                        update_figma(report_data, cfg)
                except Exception as e:
                    st.error(f"Figma error: {e}")

            output = buf.getvalue().strip()

            # Check actual outcome from the captured output
            if "Timeout" in output or "was not opened within 120s" in output:
                st.error(
                    "Plugin timed out — the plugin was not opened within 120 seconds.\n\n"
                    "**Fix:** Open Figma → Plugins → Report Updater → Fetch & Update All Nodes "
                    "WHILE the server is running, then click Push to Figma again."
                )
            elif "ERROR" in output or "failed" in output.lower():
                st.error("Figma update failed. See details below.")
            elif not output or "Figma error" not in output:
                st.success("Figma update complete.")

            if output:
                st.code(output)

# ── Export Excel ─────────────────
with col3:
    if st.button("Export Excel", use_container_width=True):
        if not os.path.exists("report_data.json"):
            st.warning("Run **Fetch GA4 Data** first.")
        else:
            with open("report_data.json") as f:
                report_data = json.load(f)
            try:
                from export_excel import export_to_excel
                export_to_excel(report_data, cfg)
                st.success("Saved to data/monthly_reports.xlsx")
            except Exception as e:
                st.error(f"Excel error: {e}")

# ── Rebuild Node Map ─────────────
with col4:
    if st.button("Rebuild Node Map", use_container_width=True):
        st.session_state["show_node_map_help"] = True

if st.session_state.get("show_node_map_help"):
    st.info(
        "**Only needed when the Figma template structure changes.**\n\n"
        "1. Run in terminal: `py fetch_nodes.py`\n"
        "2. Tell Claude: *'Map my Figma nodes to report fields using nodes_output.txt'*\n"
        "3. Claude updates node_map.json automatically\n"
        "4. Re-run the pipeline\n\n"
        "For new months or new clients using the same template, this is skipped automatically."
    )


# ── Data table ────────────────────────────────────────────────────────────────

st.divider()

# Load from session or from file
if "report_data" not in st.session_state and os.path.exists("report_data.json"):
    with open("report_data.json") as f:
        st.session_state["report_data"] = json.load(f)

if "report_data" in st.session_state:
    data = st.session_state["report_data"]
    st.subheader(f"Data — {cfg['report_month']} {cfg['report_year']} ({len(data)} fields)")
    rows = [{"Field": k, "Value": v} for k, v in data.items()]
    st.dataframe(rows, use_container_width=True, height=480)
else:
    st.caption("No data loaded. Click **Fetch GA4 Data** to pull the current month.")
