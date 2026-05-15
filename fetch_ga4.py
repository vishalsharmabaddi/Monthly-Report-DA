import json
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Metric, Dimension,
    FilterExpression, Filter
)
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def get_credentials():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("oauth_client.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return creds


def fmt_num(value):
    try:
        n = int(round(float(value)))
        return f"{n:,}"
    except:
        return "-"


def fmt_pct(value):
    try:
        return f"{float(value) * 100:.2f}"
    except:
        return "-"


def fmt_duration(seconds):
    try:
        s = int(float(seconds))
        return f"{s // 60}m {s % 60:02d}s"
    except:
        return "-"


def zero_or_dash(value):
    try:
        n = int(round(float(value)))
        return str(n) if n > 0 else "-"
    except:
        return "-"


def build_dates(config):
    year  = int(config["report_year"])
    month = datetime.strptime(config["report_month"], "%B").month

    cur_start = datetime(year, month, 1)
    if month == 12:
        cur_end = datetime(year, 12, 31)
    else:
        cur_end = datetime(year, month + 1, 1) - timedelta(days=1)

    prev_start = datetime(year - 1, month, 1)
    if month == 12:
        prev_end = datetime(year - 1, 12, 31)
    else:
        prev_end = datetime(year - 1, month + 1, 1) - timedelta(days=1)

    twelve_end   = cur_start - timedelta(days=1)
    twelve_start = cur_start - relativedelta(months=12)

    prev_month_end   = cur_start - timedelta(days=1)
    prev_month_start = cur_start - relativedelta(months=1)

    return {
        "cur_start":         cur_start.strftime("%Y-%m-%d"),
        "cur_end":           cur_end.strftime("%Y-%m-%d"),
        "prev_start":        prev_start.strftime("%Y-%m-%d"),
        "prev_end":          prev_end.strftime("%Y-%m-%d"),
        "twelve_start":      twelve_start.strftime("%Y-%m-%d"),
        "twelve_end":        twelve_end.strftime("%Y-%m-%d"),
        "prev_month_start":  prev_month_start.strftime("%Y-%m-%d"),
        "prev_month_end":    prev_month_end.strftime("%Y-%m-%d"),
    }


def fetch_ga4_data(config):
    prop    = f"properties/{config['ga4_property_id']}"
    client  = BetaAnalyticsDataClient(credentials=get_credentials())
    dates   = build_dates(config)
    data    = {}

    # ── 1. Overall metrics: current / prev year / 12-month total ──────────────
    r = client.run_report(RunReportRequest(
        property=prop,
        date_ranges=[
            DateRange(start_date=dates["cur_start"],    end_date=dates["cur_end"],    name="cur"),
            DateRange(start_date=dates["prev_start"],   end_date=dates["prev_end"],   name="prev"),
            DateRange(start_date=dates["twelve_start"], end_date=dates["twelve_end"], name="twelve"),
        ],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="newUsers"),
            Metric(name="bounceRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="conversions"),
        ],
    ))

    raw = {}
    for row in r.rows:
        dr = row.dimension_values[0].value
        raw[dr] = {
            "sessions":    row.metric_values[0].value,
            "users":       row.metric_values[1].value,
            "new_users":   row.metric_values[2].value,
            "bounce":      row.metric_values[3].value,
            "duration":    row.metric_values[4].value,
            "conversions": row.metric_values[5].value,
        }

    cur    = raw.get("cur",    {})
    prev   = raw.get("prev",   {})
    twelve = raw.get("twelve", {})

    # Current month
    data["ga4_sessions_heading"]     = f"{fmt_num(cur.get('sessions','0'))} Session"
    data["report_month_year"]        = f"{config['report_month']} {config['report_year']}"
    data["ga4_current_block"]        = (
        f"Total Users        {fmt_num(cur.get('users','0'))} "
        f"Bounce Rate      {fmt_pct(cur.get('bounce','0'))}% "
        f"Conversion         {fmt_num(cur.get('conversions','0'))}"
    )

    # Prev year same month
    data["ga4_prev_year_sessions"]   = f"Total Sessions    {fmt_num(prev.get('sessions','0'))}"
    data["ga4_prev_year_users"]      = f"Total Users          {fmt_num(prev.get('users','0'))}"
    data["ga4_prev_year_bounce"]     = f"Bounce Rate        {fmt_pct(prev.get('bounce','0'))}%"
    data["ga4_prev_year_conversion"] = f"Conversion          {fmt_num(prev.get('conversions','0'))}"

    # 12-month average (total / 12)
    def avg12(val):
        try: return str(round(float(val) / 12))
        except: return "-"

    data["ga4_12mo_sessions"]        = f"Total Sessions     {fmt_num(avg12(twelve.get('sessions','0')))}"
    data["ga4_12mo_users"]           = f"Total Users           {fmt_num(avg12(twelve.get('users','0')))}"
    data["ga4_12mo_bounce"]          = f"Bounce Rate        {fmt_pct(twelve.get('bounce','0'))}%"
    data["ga4_12mo_conversion"]      = f"Conversion           {fmt_num(avg12(twelve.get('conversions','0')))}"

    # ── 2. Organic Search Traffic section ────────────────────────────────────
    r2 = client.run_report(RunReportRequest(
        property=prop,
        date_ranges=[DateRange(start_date=dates["cur_start"], end_date=dates["cur_end"])],
        metrics=[
            Metric(name="sessions"),
            Metric(name="newUsers"),
            Metric(name="bounceRate"),
            Metric(name="averageSessionDuration"),
        ],
        dimension_filter=FilterExpression(filter=Filter(
            field_name="sessionDefaultChannelGroup",
            string_filter=Filter.StringFilter(
                value="Organic Search",
                match_type=Filter.StringFilter.MatchType.EXACT
            )
        ))
    ))

    if r2.rows:
        o = r2.rows[0]
        data["organic_sessions"]    = f"Sessions         {fmt_num(o.metric_values[0].value)}"
        data["organic_new_users"]   = f"New User         {fmt_num(o.metric_values[1].value)}"
        data["organic_bounce_rate"] = f"Bounce Rate    {fmt_pct(o.metric_values[2].value)}%"
        data["organic_avg_duration"]= f"Avg Session Duration           {fmt_duration(o.metric_values[3].value)}"

    # ── 3. User Acquisition by channel ───────────────────────────────────────
    channel_key = {
        "Organic Search": "organic",
        "Direct":         "direct",
        "Referral":       "referral",
        "Paid Search":    "paid",
        "Organic Social": "organic_social",
        "Unassigned":     "unassigned",
    }

    r3 = client.run_report(RunReportRequest(
        property=prop,
        date_ranges=[DateRange(start_date=dates["cur_start"], end_date=dates["cur_end"])],
        dimensions=[Dimension(name="sessionDefaultChannelGroup")],
        metrics=[
            Metric(name="totalUsers"),
            Metric(name="newUsers"),
            Metric(name="conversions"),
        ],
    ))

    totals = {"users": 0, "new": 0, "conv": 0}
    for row in r3.rows:
        ch  = row.dimension_values[0].value
        key = channel_key.get(ch)
        if not key:
            continue
        u   = row.metric_values[0].value
        n   = row.metric_values[1].value
        c   = row.metric_values[2].value
        ret = str(max(0, int(round(float(u))) - int(round(float(n)))))

        data[f"ua_{key}_total"]      = fmt_num(u)
        data[f"ua_{key}_new"]        = fmt_num(n)
        data[f"ua_{key}_returning"]  = fmt_num(ret)
        data[f"ua_{key}_key_events"] = zero_or_dash(c)

        totals["users"] += int(round(float(u)))
        totals["new"]   += int(round(float(n)))
        totals["conv"]  += int(round(float(c)))

    data["ua_total_users"]          = fmt_num(str(totals["users"]))
    data["ua_total_new_users"]      = fmt_num(str(totals["new"]))
    data["ua_total_returning_users"]= fmt_num(str(totals["users"] - totals["new"]))
    data["ua_total_key_events"]     = fmt_num(str(totals["conv"]))

    # ── 4. Conversions by channel – 3 date ranges ────────────────────────────
    r4 = client.run_report(RunReportRequest(
        property=prop,
        date_ranges=[
            DateRange(start_date=dates["cur_start"],    end_date=dates["cur_end"],    name="cur"),
            DateRange(start_date=dates["prev_start"],   end_date=dates["prev_end"],   name="prev"),
            DateRange(start_date=dates["twelve_start"], end_date=dates["twelve_end"], name="twelve"),
        ],
        dimensions=[
            Dimension(name="sessionDefaultChannelGroup"),
        ],
        metrics=[Metric(name="conversions")],
    ))

    conv_raw = {}
    for row in r4.rows:
        dr  = row.dimension_values[0].value
        ch  = row.dimension_values[1].value
        key = channel_key.get(ch)
        if key:
            conv_raw.setdefault(key, {})[dr] = row.metric_values[0].value

    conv_field_map = {
        "organic":        ("conv_organic_current",  "conv_organic_prev_year",  "conv_organic_12mo"),
        "unassigned":     ("conv_unassigned_current","conv_unassigned_prev_year","conv_unassigned_12mo"),
        "referral":       ("conv_referral_current",  "conv_referral_prev_year", "conv_referral_avg12mo"),
        "paid":           ("conv_paid_current",      "conv_paid_prev_year",     "conv_paid_12mo"),
        "direct":         ("conv_direct_current",    "conv_direct_prev_year",   "conv_direct_12mo"),
        "organic_social": ("conv_social_current",    "conv_social_prev_year",   "conv_social_12mo"),
    }

    conv_totals = {"cur": 0, "prev": 0, "twelve": 0}
    for key, (f_cur, f_prev, f_12) in conv_field_map.items():
        vals = conv_raw.get(key, {})
        c_val = vals.get("cur",    "0")
        p_val = vals.get("prev",   "0")
        t_val = vals.get("twelve", "0")
        data[f_cur]  = zero_or_dash(c_val)
        data[f_prev] = zero_or_dash(p_val)
        data[f_12]   = zero_or_dash(str(round(float(t_val) / 12))) if t_val != "0" else "-"
        try:
            conv_totals["cur"]    += int(round(float(c_val)))
            conv_totals["prev"]   += int(round(float(p_val)))
            conv_totals["twelve"] += int(round(float(t_val)))
        except:
            pass

    data["conv_total_current"]  = fmt_num(str(conv_totals["cur"]))
    data["conv_total_prev_year"]= fmt_num(str(conv_totals["prev"]))
    data["conv_total_12mo"]     = zero_or_dash(str(round(conv_totals["twelve"] / 12))) if conv_totals["twelve"] else "-"

    # ── 5. Social platform traffic (Traffic Overview) ─────────────────────────
    def social_sessions(start, end):
        resp = client.run_report(RunReportRequest(
            property=prop,
            date_ranges=[DateRange(start_date=start, end_date=end)],
            dimensions=[Dimension(name="sessionSource")],
            metrics=[Metric(name="sessions")],
            dimension_filter=FilterExpression(filter=Filter(
                field_name="sessionDefaultChannelGroup",
                string_filter=Filter.StringFilter(
                    value="Organic Social",
                    match_type=Filter.StringFilter.MatchType.EXACT
                )
            ))
        ))
        result = {"facebook": "-", "instagram": "-", "pinterest": "-", "linkedin": "-"}
        for row in resp.rows:
            src = row.dimension_values[0].value.lower()
            val = zero_or_dash(row.metric_values[0].value)
            for platform in result:
                if platform in src:
                    result[platform] = val
        return result

    cur_social  = social_sessions(dates["cur_start"],         dates["cur_end"])
    prev_social = social_sessions(dates["prev_month_start"],  dates["prev_month_end"])

    for platform in ["facebook", "instagram", "pinterest", "linkedin"]:
        data[f"social_{platform}_current"] = cur_social[platform]
        data[f"social_{platform}_prev"]    = prev_social[platform]

    return data


if __name__ == "__main__":
    with open("config.json") as f:
        config = json.load(f)
    result = fetch_ga4_data(config)
    with open("report_data.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"GA4 data fetched successfully — {len(result)} fields saved to report_data.json")
