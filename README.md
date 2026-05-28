# Monthly Report Automation

Pulls metrics from Google Analytics 4 and pushes them into a Figma report — automatically. Replaces ~2 hours of manual copy-paste per month with one click.

---

## What It Does

- Fetches 47+ GA4 metrics (sessions, users, bounce rate, conversions, channel breakdown, social platforms)
- Pushes formatted values into 73 Figma text nodes via a local plugin
- Saves a running Excel backup of all monthly data
- Supports multiple clients — switch between them from the dashboard

---

## Requirements

- Python 3.10+
- [Figma Desktop](https://www.figma.com/downloads/) with the **Report Updater** plugin loaded locally
- Google Analytics 4 access on the client account
- Two credential files per client (not committed — keep private):
  - `oauth_client.json` — download from Google Cloud Console
  - `config.json` — client settings (GA4 property ID, Figma token, file key)

---

## Installation

```bash
# Clone the repo
git clone <repo-url>
cd "Report monthly dy"

# Install dependencies
pip install -r requirements.txt
```

---

## Monthly Workflow

### Option A — Dashboard (Recommended)

```bash
streamlit run dashboard.py
```

1. Select your client from the sidebar dropdown → click **Load Client**
2. Verify the month/year is correct (auto-warns if it looks wrong)
3. Click **Fetch GA4 Data** — browser login on first run, automatic after that
4. Open Figma Desktop → Plugins → Report Updater → **Fetch & Update All Nodes**
5. Back on the dashboard, click **Push to Figma**
6. Click **Export Excel** → download the file

Or use **Run Full Pipeline** (expander at the bottom) to do steps 3–6 in one click.

### Option B — Terminal

```bash
# Run for a specific client
py run_report.py 1800_buggies

# Interactive client selector (no argument)
py run_report.py
```

---

## New Client Setup

### Step 1 — Google Cloud (OAuth2)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **Google Analytics Data API**
3. Create credentials → **OAuth 2.0 Client ID** (Desktop app) → Download JSON
4. Rename it to `oauth_client.json`
5. On the OAuth consent screen → **Test users** → add the client's Google account email

### Step 2 — GA4 Access

1. Go to GA4 → Admin → Account Access Management
2. Add your service account or Google account as **Viewer**
3. Copy the **Property ID** (found in GA4 → Admin → Property Settings)

### Step 3 — Figma

1. Get a Figma **Personal Access Token**: figma.com → Account Settings → Personal Access Tokens
2. Open the Figma report file → copy the **File Key** from the URL:
   ```
   figma.com/design/<FILE_KEY>/...
   ```

### Step 4 — Config File

Create `clients/<client_slug>/config.json`:

```json
{
  "client_name": "Client Name",
  "ga4_property_id": "414073971",
  "figma_token": "figd_...",
  "figma_file_key": "0ZRlbRlTVTpKpzFdwMiy0P",
  "report_month": "May",
  "report_year": "2026",
  "prev_month_label": "Apr 2026",
  "figma_update_method": "plugin"
}
```

Place `oauth_client.json` in the same folder: `clients/<client_slug>/oauth_client.json`

### Step 5 — Map Figma Nodes (one-time)

```bash
py fetch_nodes.py <client_slug>
```

This dumps all Figma text nodes to `clients/<client_slug>/nodes_output.txt`.

Then in Claude Code, run:
> "Please complete our Figma node mapping:
> 1. Identify the unmatched fields from the top section of `nodes_output.txt`
> 2. Match them to correct Figma node IDs by comparing values in `report_data.json` and analyzing parent frame paths
> 3. Update ONLY newly resolved fields in `node_map.json`, leaving already mapped fields intact"

### Step 6 — First Run

```bash
py run_report.py <client_slug>
```

A browser window opens for Google login → approves → saves `token.json` → fully automated from here.

---

## Architecture

```
run_report.py  (orchestrator)
    │
    ├── fetch_ga4.py       → GA4 API → report_data.json   (47 formatted fields)
    ├── update_figma.py    → report_data.json + node_map.json → Figma text nodes
    └── export_excel.py    → report_data.json → data/monthly_reports.xlsx
```

| File | Purpose |
|---|---|
| `config.json` | Client settings — edit monthly (`report_month`, `report_year`, `prev_month_label`) |
| `node_map.json` | Maps 73 field names → Figma text node IDs |
| `token.json` | Auto-saved Google OAuth token — delete to force re-login |
| `oauth_client.json` | Google Cloud OAuth2 key |
| `report_data.json` | Intermediate output from GA4 fetch — 47 pre-formatted string fields |
| `data/monthly_reports.xlsx` | Running Excel backup — one row per month |

---

## Deploying to Streamlit Cloud

Add these secrets in your Streamlit Cloud app settings (⋮ → Settings → Secrets):

```toml
APP_PASSWORD        = "your_dashboard_password"
FIGMA_TOKEN         = "figd_your_token"
GA4_PROPERTY_ID     = "414073971"
FIGMA_FILE_KEY      = "0ZRlbRlTVTpKpzFdwMiy0P"
GOOGLE_REFRESH_TOKEN   = "..."
GOOGLE_CLIENT_ID       = "..."
GOOGLE_CLIENT_SECRET   = "..."
```

The dashboard auto-detects cloud mode and reads credentials from secrets instead of local files.

---

## Troubleshooting

**GA4 auth broken / token expired**
```bash
del token.json       # Windows
py run_report.py     # re-triggers browser login
```

**Figma plugin times out**
- Make sure Figma Desktop is open with the report file
- Go to Plugins → Report Updater → Fetch & Update All Nodes
- The server waits 120 seconds — open the plugin within that window

**Node map is stale (Figma template changed)**
```bash
py fetch_nodes.py <client_slug>
# Then ask Claude to update node_map.json (see New Client Setup → Step 5)
```

**Fields marked as manual (skipped automatically)**
- `source: "semrush"` — Authority Score, top keywords (update in Figma manually)
- `source: "google_ads"` — Google Ads metrics (update in Figma manually)

---

## What's Private (Never Committed)

```
config.json               ← Figma token + GA4 property ID
token.json                ← Google OAuth refresh token
oauth_client.json         ← Google Cloud OAuth2 key
clients/*/config.json
clients/*/token.json
clients/*/oauth_client.json
clients/*/report_data.json
data/                     ← Excel backup
.streamlit/secrets.toml   ← Cloud secrets
```
