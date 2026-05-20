"""
Monthly report dashboard.
Run: streamlit run dashboard.py
"""
import contextlib
import io
import json
import os
import sys
from datetime import date
from dateutil.relativedelta import relativedelta
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

IS_CLOUD = bool(
    os.environ.get("STREAMLIT_SHARING_MODE") or
    os.environ.get("IS_CLOUD") or
    os.environ.get("GOOGLE_REFRESH_TOKEN")
)


# ── Login gate ────────────────────────────────────────────────────────────────

def _get_app_password() -> str | None:
    """Return configured password, or None if auth is disabled (local dev)."""
    try:
        return st.secrets.get("APP_PASSWORD") or os.environ.get("APP_PASSWORD")
    except Exception:
        return os.environ.get("APP_PASSWORD")


def require_login():
    app_password = _get_app_password()
    if not app_password:
        return  # No password configured — local dev, skip auth

    if st.session_state.get("authenticated"):
        return

    st.markdown("## Report Dashboard — Login")
    pwd = st.text_input("Password", type="password", key="login_input")
    if st.button("Login", type="primary"):
        if pwd == app_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


require_login()


# ── Secrets overlay ───────────────────────────────────────────────────────────

def _secret(key: str, fallback: str = "") -> str:
    """Read from st.secrets, then env var, then fallback."""
    try:
        val = st.secrets.get(key)
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, fallback)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_clients() -> dict:
    CLIENTS_DIR.mkdir(exist_ok=True)
    clients = {}
    for f in sorted(CLIENTS_DIR.glob("*.json")):
        if "_node_map" in f.name:
            continue
        try:
            data = json.loads(f.read_text())
            clients[data.get("client_name", f.stem)] = f
        except Exception:
            pass
    return clients


def _default_config() -> dict:
    """Fallback config for cloud where config.json doesn't exist."""
    today = date.today()
    last_month = today.replace(day=1) - relativedelta(months=1)
    prev = last_month.replace(day=1) - relativedelta(months=1)
    return {
        "ga4_property_id": _secret("GA4_PROPERTY_ID", ""),
        "figma_token":     _secret("FIGMA_TOKEN", ""),
        "figma_file_key":  _secret("FIGMA_FILE_KEY", ""),
        "report_month":    MONTHS[last_month.month - 1],
        "report_year":     str(last_month.year),
        "prev_month_label": f"{MONTH_ABBR[MONTHS[prev.month - 1]]} {prev.year}",
        "client_name":     _secret("CLIENT_NAME", "My Client"),
        "figma_update_method": "variables",
    }


def load_config() -> dict:
    if os.path.exists("config.json"):
        with open("config.json") as f:
            cfg = json.load(f)
    else:
        cfg = _default_config()
    # Overlay secrets from env / st.secrets
    figma_token = _secret("FIGMA_TOKEN")
    if figma_token:
        cfg["figma_token"] = figma_token
    return cfg


def save_config(cfg: dict):
    with open("config.json", "w") as f:
        json.dump(cfg, f, indent=2)


def _client_slug(cfg: dict) -> str:
    return cfg["client_name"].lower().replace(" ", "_").replace("/", "_")


def save_client(cfg: dict) -> Path:
    CLIENTS_DIR.mkdir(exist_ok=True)
    slug = _client_slug(cfg)
    path = CLIENTS_DIR / f"{slug}.json"
    path.write_text(json.dumps(cfg, indent=2))
    # Also snapshot current node_map.json with this client
    if Path("node_map.json").exists():
        nm_path = CLIENTS_DIR / f"{slug}_node_map.json"
        nm_path.write_text(Path("node_map.json").read_text())
    return path


def load_client(cfg_path: Path):
    loaded = json.loads(cfg_path.read_text())
    save_config(loaded)
    # Restore this client's node_map if it was saved
    slug = _client_slug(loaded)
    nm_path = CLIENTS_DIR / f"{slug}_node_map.json"
    if nm_path.exists():
        Path("node_map.json").write_text(nm_path.read_text())


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


def expected_report_month() -> tuple[str, str]:
    """Last completed month — what we should be reporting on today."""
    last = date.today().replace(day=1) - relativedelta(months=1)
    return MONTHS[last.month - 1], str(last.year)


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
            load_client(clients[selected])
            st.success(f"Loaded {selected}")
            st.rerun()
    else:
        st.info("No clients saved yet. Fill in the fields and click 'Save Client'.")

    st.divider()

    client_name = st.text_input("Client Name", cfg.get("client_name", ""))
    ga4_id      = st.text_input("GA4 Property ID", cfg.get("ga4_property_id", ""))
    figma_key   = st.text_input("Figma File Key", cfg.get("figma_file_key", ""))

    # On cloud, figma_token comes from secrets — show as read-only hint
    if IS_CLOUD and _secret("FIGMA_TOKEN"):
        st.text_input("Figma Token", value="(from environment)", disabled=True)
        figma_token = cfg.get("figma_token", "")
    else:
        figma_token = st.text_input("Figma Token", cfg.get("figma_token", ""), type="password")

    month_val = cfg.get("report_month", "January")
    month = st.selectbox(
        "Month", MONTHS,
        index=MONTHS.index(month_val) if month_val in MONTHS else 0,
    )
    year = st.text_input("Year", cfg.get("report_year", "2026"))

    method_opts = ["plugin", "mcp", "variables", "claude_api"]
    cur_method = cfg.get("figma_update_method", "plugin")
    if cur_method not in method_opts:
        cur_method = method_opts[0]
    method = st.selectbox(
        "Figma Update Method", method_opts,
        index=method_opts.index(cur_method),
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

    if st.session_state.get("authenticated"):
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.pop("authenticated", None)
            st.rerun()


# ── Main header ───────────────────────────────────────────────────────────────

cfg = load_config()
st.title(f"{cfg['client_name']} — {cfg['report_month']} {cfg['report_year']}")
st.caption(
    f"GA4: `{cfg['ga4_property_id']}` | "
    f"Figma: `{cfg['figma_file_key']}` | "
    f"Method: `{cfg.get('figma_update_method', 'plugin')}`"
)

# Auto-month banner: warn if config month doesn't match expected reporting month
exp_month, exp_year = expected_report_month()
if cfg.get("report_month") != exp_month or cfg.get("report_year") != exp_year:
    col_warn, col_btn = st.columns([3, 1])
    with col_warn:
        st.warning(
            f"Config says **{cfg['report_month']} {cfg['report_year']}** "
            f"— expected reporting month is **{exp_month} {exp_year}**."
        )
    with col_btn:
        if st.button(f"Switch to {exp_month} {exp_year}", use_container_width=True):
            new_cfg = build_config(
                cfg, cfg["client_name"], cfg["ga4_property_id"],
                cfg["figma_file_key"], cfg["figma_token"],
                exp_month, exp_year, cfg.get("figma_update_method", "plugin"),
            )
            save_config(new_cfg)
            st.rerun()

st.divider()


# ── Shared pipeline steps (used by both individual buttons and Run All) ────────

def step_fetch_ga4(cfg: dict) -> dict | None:
    has_cloud_auth = bool(os.environ.get("GOOGLE_REFRESH_TOKEN") or _secret("GOOGLE_REFRESH_TOKEN"))
    if not has_cloud_auth and not os.path.exists("oauth_client.json"):
        st.error("oauth_client.json not found. Download from Google Cloud Console.")
        return None
    try:
        # Inject cloud Google secrets into env so fetch_ga4.get_credentials() picks them up
        for key in ("GOOGLE_REFRESH_TOKEN", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
            val = _secret(key)
            if val:
                os.environ[key] = val
        sys.path.insert(0, str(Path(__file__).parent))
        from fetch_ga4 import fetch_ga4_data
        report_data = fetch_ga4_data(cfg)
        with open("report_data.json", "w") as f:
            json.dump(report_data, f, indent=2)
        st.session_state["report_data"] = report_data
        return report_data
    except Exception as e:
        st.error(f"GA4 error: {e}")
        return None


def step_push_figma(cfg: dict, report_data: dict) -> bool:
    push_method = cfg.get("figma_update_method", "plugin")

    if push_method == "mcp":
        st.info(
            "**report_data.json is ready.**\n\n"
            "Tell Claude: **'push to figma'**\n\n"
            "Claude will read report_data.json + node_map.json and push all values."
        )
        return True

    if push_method == "variables" and not os.path.exists("figma_vars.json"):
        st.error(
            "figma_vars.json not found. "
            "Run `py setup_figma.py` once to create Figma variables (requires paid Figma plan)."
        )
        return False

    if push_method == "plugin":
        st.info(
            "Server starting at **localhost:5555** (120s window).\n\n"
            ">> Open Figma → Plugins → Report Updater → **Fetch & Update All Nodes**"
        )

    buf = io.StringIO()
    try:
        from update_figma import update_figma
        with contextlib.redirect_stdout(buf):
            update_figma(report_data, cfg)
    except Exception as e:
        st.error(f"Figma error: {e}")
        return False

    output = buf.getvalue().strip()

    if "Timeout" in output or "was not opened within 120s" in output:
        st.error(
            "Plugin timed out — not opened within 120s.\n\n"
            "Open Figma → Plugins → Report Updater → Fetch & Update All Nodes, then try again."
        )
        if output:
            st.code(output)
        return False
    elif "ERROR" in output or "failed" in output.lower():
        st.error("Figma update failed.")
        if output:
            st.code(output)
        return False
    else:
        st.success("Figma updated.")
        return True


def step_export_excel(cfg: dict, report_data: dict) -> bool:
    try:
        from export_excel import export_to_excel
        export_to_excel(report_data, cfg)
        st.success("Saved to data/monthly_reports.xlsx")
        # Offer browser download
        with open("data/monthly_reports.xlsx", "rb") as f:
            st.download_button(
                label="Download Excel",
                data=f.read(),
                file_name=f"monthly_reports_{cfg['report_month']}_{cfg['report_year']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return True
    except Exception as e:
        st.error(f"Excel error: {e}")
        return False


# ── Action buttons ────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

# ── Fetch GA4 ────────────────────
with col1:
    if st.button("Fetch GA4 Data", use_container_width=True, type="primary"):
        with st.spinner("Fetching GA4 data..."):
            step_fetch_ga4(cfg)

# ── Push to Figma ────────────────
with col2:
    if st.button("Push to Figma", use_container_width=True, type="primary"):
        if not os.path.exists("report_data.json"):
            st.warning("Run **Fetch GA4 Data** first.")
        else:
            with open("report_data.json") as f:
                report_data = json.load(f)
            label = "Waiting for Figma plugin..." if cfg.get("figma_update_method") == "plugin" else "Pushing to Figma..."
            with st.spinner(label):
                step_push_figma(cfg, report_data)

# ── Export Excel ─────────────────
with col3:
    if st.button("Export Excel", use_container_width=True):
        if not os.path.exists("report_data.json"):
            st.warning("Run **Fetch GA4 Data** first.")
        else:
            with open("report_data.json") as f:
                report_data = json.load(f)
            step_export_excel(cfg, report_data)

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

st.divider()

# ── Run Full Pipeline ─────────────────────────────────────────────────────────

with st.expander("Run Full Pipeline — Fetch GA4 + Push Figma + Export Excel", expanded=False):
    st.caption("Runs all 3 steps in sequence. Stops if any step fails.")
    if st.button("Run Full Pipeline", use_container_width=True, type="primary", key="run_all"):
        st.markdown("---")

        st.markdown("**Step 1 / 3 — Fetch GA4 Data**")
        with st.spinner("Fetching GA4 data..."):
            report_data = step_fetch_ga4(cfg)
        if report_data is None:
            st.stop()

        st.markdown("**Step 2 / 3 — Push to Figma**")
        method = cfg.get("figma_update_method", "plugin")
        label = "Waiting for Figma plugin..." if method == "plugin" else "Pushing to Figma..."
        with st.spinner(label):
            ok = step_push_figma(cfg, report_data)
        if not ok and method != "mcp":
            st.stop()

        st.markdown("**Step 3 / 3 — Export Excel**")
        step_export_excel(cfg, report_data)

        st.success("Pipeline complete.")


# ── Data table ────────────────────────────────────────────────────────────────

st.divider()

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
