# Monthly Report Automation

Pulls data from Google Analytics 4 and pushes it into a Figma report — automatically. Replaces 2 hours of manual copy-paste with one button click.

## What It Does

- Fetches GA4 metrics (sessions, users, bounce rate, conversions, traffic by channel)
- Updates 73 text nodes in Figma via a local plugin
- Saves a running Excel backup of all monthly data

## Run It

```bash
# Install dependencies (one time)
pip install -r requirements.txt

# Launch dashboard
streamlit run dashboard.py

# Or run from terminal
py run_report.py
```

## Requirements

- Python 3.10+
- Google Analytics 4 access (OAuth2)
- Figma Desktop with the Report Updater plugin loaded
- `oauth_client.json` — download from Google Cloud Console
- `config.json` — client settings (not committed, keep private)

## Monthly Workflow

1. Open dashboard → verify month is correct
2. Click **Fetch GA4 Data**
3. Click **Push to Figma** → open plugin in Figma → click Fetch & Update All Nodes
4. Click **Export Excel** → download file

Or use **Run Full Pipeline** to do all steps in one click.

## New Client Setup

1. Update `config.json` with new GA4 property ID, Figma file key, and token
2. Run `py fetch_nodes.py` to map Figma text nodes
3. Run `py run_report.py`
