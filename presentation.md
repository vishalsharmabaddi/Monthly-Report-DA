# Monthly Report Automation — Dashboard Guide

---

## What This System Does

Replaces **2 hours of manual copy-paste** every month with a **5-minute, 4-click process.**

Pulls live data from Google Analytics 4 → pushes it directly into Figma text nodes → exports to Excel backup.

---

## The Dashboard

Run once to open:
```
py -m streamlit run dashboard.py
```
Browser opens at `http://localhost:8501`

---

```
┌─────────────────────────────────────────────────────────────────────┐
│                     REPORT DASHBOARD                                │
├──────────────────┬──────────────────────────────────────────────────┤
│  SIDEBAR         │  1800 Buggies — May 2026                         │
│                  │  GA4: 414073971 | Figma: 0ZRlbR... | plugin      │
│  Client          │ ─────────────────────────────────────────────── │
│  [1800 Buggies▼] │                                                  │
│  [Load Client]   │  ┌──────────────┐ ┌──────────────┐              │
│                  │  │ Fetch GA4    │ │ Push to Figma│              │
│  Client Name     │  │    Data      │ │              │              │
│  [1800 Buggies]  │  └──────────────┘ └──────────────┘              │
│                  │  ┌──────────────┐ ┌──────────────┐              │
│  GA4 Property ID │  │ Export Excel │ │ Rebuild Node │              │
│  [414073971    ] │  │              │ │     Map      │              │
│                  │  └──────────────┘ └──────────────┘              │
│  Figma File Key  │                                                  │
│  [0ZRlbR......] │  ─────────────────────────────────────────────── │
│                  │                                                  │
│  Figma Token     │  Data — May 2026 (68 fields)                    │
│  [••••••••••••] │                                                  │
│                  │  Field                    Value                  │
│  Month  [May ▼]  │  ga4_sessions_heading     676 Session           │
│  Year   [2026 ]  │  report_month_year         May 2026             │
│                  │  ga4_current_block         Total Users 398 ...  │
│  Method [plugin▼]│  organic_sessions          Sessions    305      │
│                  │  ua_direct_total           328                   │
│  [Save Config]   │  conv_total_current        0                    │
│  [Save Client ]  │  ...                       ...                  │
└──────────────────┴──────────────────────────────────────────────────┘
```

---

## Monthly Workflow — Normal Month

> Same client, same Figma template. Fully automatic.

### Step 1 — Change the month in sidebar

```
Sidebar → Month: [June ▼]  Year: [2026]
→ Click "Save Config"
```

### Step 2 — Fetch GA4 Data

```
Click: [Fetch GA4 Data]
```

```
What happens:
  Connecting to Google Analytics 4...
  Running 5 queries (sessions, users, organic, conversions, social)...
  68 fields fetched and saved  ✓
  Table appears in dashboard below
```

> First time each month: browser opens for Google login → approve → auto-saved for next time.

### Step 3 — Push to Figma

```
Click: [Push to Figma]
```

```
Dashboard shows:
  "Server starting at localhost:5555 (120s window)"
  "Open Figma → Plugins → Development → Report Updater → Fetch & Update All Nodes"
```

```
While spinner is running → go to Figma:
  Right-click canvas → Plugins → Development → Report Updater
  Click: [Fetch & Update All Nodes]

  Plugin shows:
    ✓ 65 nodes updated
    3 fields skipped (semrush / google_ads — manual)
```

### Step 4 — Export to Excel (optional)

```
Click: [Export Excel]
→ Row added to data/monthly_reports.xlsx
```

### Step 5 — Done

```
Export PDF from Figma → send to client
```

---

## Multi-Client Workflow

### Switching to a different client

```
Sidebar → Client dropdown → Select client
→ Click "Load Client"
→ All fields auto-fill (GA4 ID, Figma key, token)
→ Click "Fetch GA4 Data" → new client's data pulls in
→ Click "Push to Figma" → updates their Figma file
```

### Adding a new client

```
Sidebar → Fill in all fields:
  Client Name:    New Client Ltd
  GA4 Property:   123456789
  Figma File Key: AbCdEfGhIjKlMn
  Figma Token:    figd_xxxxxxxxxxxx
  Method:         plugin

→ Click "Save Client"
→ Saved to clients/new_client_ltd.json
→ Appears in dropdown from now on
```

---

## When the Figma Template Changes

> Only needed when the designer rebuilds the template (new node IDs).

```
Click: [Rebuild Node Map]
→ Dashboard shows instructions
```

```
Terminal:
  py fetch_nodes.py

Output:
  Found 87 text nodes.
  Auto-matched: 65/68 fields  ✓
  Needs review: 3 fields
    - conv_paid_current
    - conv_paid_prev_year
    - ua_paid_total

  >> Tell Claude: "Map these unmatched fields using nodes_output.txt"
```

```
Claude maps the remaining 3 → node_map.json updated
→ py run_report.py  (fully automated from now on)
```

---

## Figma Update Methods

| Method | How it works | Best for |
|---|---|---|
| **plugin** *(default)* | Python starts a local server → Figma plugin fetches data | Free plan, fastest, no limits |
| **mcp** | Claude AI reads report_data.json and pushes via MCP | When plugin isn't available |
| **variables** | Figma REST API — direct push | Paid Figma plan only |

Change method anytime: Sidebar → Method dropdown → Save Config

---

## Fields Automated vs Manual

| Category | Count | Status |
|---|---|---|
| GA4 — Overall traffic | 15 | Automated |
| GA4 — Organic search | 4 | Automated |
| User Acquisition by channel | 24 | Automated |
| Conversions by channel | 21 | Automated |
| Social platform sessions | 8 | Automated |
| **Total automated** | **68** | **Automated** |
| Authority Score | 1 | Manual (SEMrush) |
| Top 5 Keywords | 5 rows | Manual (SEMrush) |
| Google Ads | varies | Manual (Google Ads) |

---

## One-Time Setup Checklist

```
[ ] pip install -r requirements.txt
[ ] Download oauth_client.json from Google Cloud Console
[ ] Add GA4 viewer access for the Google account
[ ] Install Report Updater plugin in Figma:
      Main Menu → Plugins → Development → Import plugin from manifest
      → Select: figma_plugin/manifest.json
[ ] Fill in sidebar + click Save Client
[ ] Run pipeline once → approve Google login in browser
[ ] Done — fully automated from next month
```
