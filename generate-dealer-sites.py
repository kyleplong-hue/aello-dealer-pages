#!/usr/bin/env python3
"""
Generate personalized dealer landing pages and report pages from templates.

Reads dealer data from aello-dealer-data.json and creates per-dealer directories
under dealer-sites/ with customized index.html (landing) and report.html files.

Usage:
    python3 generate-dealer-sites.py
"""

import json
import math
import os
import re
import sys

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "aello-dealer-data.json")
LANDING_TEMPLATE = os.path.join(BASE_DIR, "aello-dealer-landing.html")
REPORT_TEMPLATE = os.path.join(BASE_DIR, "aello-dealer-report.html")
OUTPUT_DIR = os.path.join(BASE_DIR, "dealer-sites")

# ── Marketplace abbreviation mappings ──────────────────────────────────────────
ABBR_MAP = {
    "Autoline": "AL",
    "TrucksNL": "NL",
    "Truck1": "T1",
    "Via Mobilis": "VM",
    "Mascus": "MA",
    "TruckScout24": "TS",
    "Machineryline": "ML",
    "Mobile.de": "MD",
    "Europa-Vrachtwagens": "EV",
    "Machineryzone": "MZ",
    "Europa-Bouwmachines": "EB",
    "Forklift": "FL",
    "Machinerypark": "MP",
    "TruckNL": "TN",
    "AgriAffaires": "AA",
    "LeBonCoin": "LBC",
    "LeBonCoin Pro": "LBC",
    "Europe-Camions": "EC",
    "BasWorld": "BW",
    "MachineryTrader": "MT",
    "MachineryFinder": "MF",
}


def slugify(name):
    """Convert dealer name to URL-friendly slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug


def parse_response_hrs(response_hrs):
    """
    Parse the response_hrs field.

    Returns (hours_float, response_time_str, response_minutes, is_pending, is_no_response)
    """
    if not response_hrs or response_hrs.strip() == "":
        # Not mystery shopped yet
        return (None, "En attente d'audit", -1, True, False)

    if response_hrs.strip().lower() == "no response":
        return (None, "Pas de réponse", 9999, False, True)

    # Parse patterns like "11.7h (email)", "15.6h (truck1)", "0.5h (email)"
    match = re.match(r"([\d.]+)h", response_hrs.strip())
    if match:
        hours = float(match.group(1))
        total_minutes = round(hours * 60)
        h = int(total_minutes // 60)
        m = int(total_minutes % 60)
        if h > 0 and m > 0:
            time_str = f"{h}h {m:02d}min"
        elif h > 0:
            time_str = f"{h}h 00min"
        else:
            time_str = f"{m}min"
        return (hours, time_str, total_minutes, False, False)

    # Fallback
    return (None, "En attente d'audit", -1, True, False)


def parse_platform_from_response(response_hrs):
    """Extract platform name from response_hrs parenthetical, if present."""
    match = re.search(r"\(([^)]+)\)", response_hrs or "")
    if match:
        platform_hint = match.group(1).strip().lower()
        # Map common hints back to platform names
        hint_map = {
            "email": None,  # generic, not a platform name
            "truck1": "Truck1",
            "autoline": "Autoline",
            "trucksnl": "TrucksNL",
            "truckscout24": "TruckScout24",
            "mascus": "Mascus",
            "leboncoin": "LeBonCoin",
            "europe-camions": "Europe-Camions",
        }
        return hint_map.get(platform_hint)
    return None


def parse_european_currency(value_str):
    """Parse European currency format like '€12.000,00' to float."""
    if not value_str or not value_str.strip():
        return None
    cleaned = value_str.strip()
    cleaned = re.sub(r"[€\s]", "", cleaned)
    # European format: dots as thousands separator, comma as decimal
    cleaned = cleaned.replace(".", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def calculate_score(response_minutes):
    """
    Calculate overall score based on response time.
    - If has response time: score = max(5, 100 - (minutes/60)*5)
    - If no response (9999): score = 5
    - If pending (-1): score = -1
    """
    if response_minutes == -1:
        return -1
    if response_minutes == 9999:
        return 5
    hours = response_minutes / 60
    score = 100 - hours * 5
    return max(5, round(score))


def build_marketplace_list(marketplaces_spoken, listings_count):
    """Build the marketplace_list array from comma-separated marketplace string."""
    if not marketplaces_spoken or not marketplaces_spoken.strip():
        return []

    names = [m.strip() for m in marketplaces_spoken.split(",") if m.strip()]
    platform_count = len(names)
    listings_per = round(listings_count / platform_count) if platform_count > 0 else 0

    marketplace_list = []
    for name in names:
        abbr = ABBR_MAP.get(name, name[:2].upper())
        marketplace_list.append({
            "name": name,
            "abbr": abbr,
            "listings": listings_per,
            "active": True,
        })
    return marketplace_list


def build_dealer_data_landing(dealer):
    """Build the dealerData JS object for the landing page template."""
    listings_count = dealer.get("listings_count", 0) or 0
    marketplaces_spoken = dealer.get("marketplaces_spoken", "")
    marketplace_list = build_marketplace_list(marketplaces_spoken, listings_count)
    platform_count = len(marketplace_list)

    est_leads = dealer.get("est_leads_mo")
    if not est_leads:
        est_leads = round(listings_count * 0.8)

    response_hrs = dealer.get("response_hrs", "")
    hours, time_str, minutes, is_pending, is_no_response = parse_response_hrs(response_hrs)

    # Shop platform
    shop_platform = dealer.get("shop_platform", "")
    response_platform = parse_platform_from_response(response_hrs)
    mystery_platform = response_platform or shop_platform or (marketplace_list[0]["name"] if marketplace_list else "")

    # Revenue
    rev_str = dealer.get("lost_revenue_mo", "")
    revenue = parse_european_currency(rev_str)
    if revenue is None:
        revenue = round(est_leads * 75)

    # Deals lost per month (estimate)
    margin_per_sale = 1800
    deals_lost = max(1, round(revenue / margin_per_sale)) if margin_per_sale > 0 else 1

    # Build JS object as a dict, then serialize
    data = {
        "dealer_name": dealer["dealer_name"],
        "dealer_city": dealer.get("city", ""),
        "dealer_website": dealer.get("domain", ""),
        "total_listings": listings_count,
        "total_platforms": platform_count,
        "estimated_leads_per_month": est_leads,
        "marketplace_list": marketplace_list,
        "mystery_shop_response_time": time_str,
        "mystery_shop_response_minutes": minutes,
        "mystery_shop_platform": mystery_platform,
        "mystery_shop_pending": is_pending,
        "mystery_shop_no_response": is_no_response,
        "revenue_leak_monthly": round(revenue),
        "cost_per_lead": 18,
        "deals_lost_per_month": deals_lost,
        "margin_per_sale": margin_per_sale,
        "generated_date": "March 2026",
        "overall_score": calculate_score(minutes),
    }
    return data


def build_dealer_data_report(dealer):
    """Build the dealer data for the report page template (the 'dealer' const)."""
    response_hrs = dealer.get("response_hrs", "")
    hours, time_str, minutes, is_pending, is_no_response = parse_response_hrs(response_hrs)
    score = calculate_score(minutes)

    shop_platform = dealer.get("shop_platform", "")
    response_platform = parse_platform_from_response(response_hrs)
    marketplaces_spoken = dealer.get("marketplaces_spoken", "")
    marketplace_names = [m.strip() for m in marketplaces_spoken.split(",") if m.strip()]
    mystery_platform = response_platform or shop_platform or (marketplace_names[0] if marketplace_names else "")

    data = {
        "name": dealer["dealer_name"],
        "city": dealer.get("city", ""),
        "platform": mystery_platform,
        "vehicle": "DAF XF 480 FT",  # Keep template default
        "buyer": "Max Schreiber",     # Keep template default
        "date": "March 2026",
        "overall_score": score,
        "mystery_shop_response_time": time_str,
        "mystery_shop_response_minutes": minutes,
        "mystery_shop_pending": is_pending,
        "mystery_shop_no_response": is_no_response,
    }
    return data


def format_js_value(value):
    """Format a Python value as a JavaScript literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, str):
        # Escape for JS string
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'").replace("\n", "\\n")
        return f'"{escaped}"'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, dict):
                pairs = []
                for k, v in item.items():
                    pairs.append(f"{k}: {format_js_value(v)}")
                items.append("{ " + ", ".join(pairs) + " }")
            else:
                items.append(format_js_value(item))
        return "[\n    " + ",\n    ".join(items) + ",\n  ]"
    elif value is None:
        return "null"
    else:
        return str(value)


def dealer_data_to_js(data, var_name="dealerData", declaration="const"):
    """Convert a dealer data dict to a JavaScript const declaration string."""
    lines = [f"{declaration} {var_name} = {{"]
    items = list(data.items())
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ","
        formatted = format_js_value(value)
        if isinstance(value, list):
            lines.append(f"  {key}: {formatted}{comma}")
        else:
            lines.append(f"  {key}: {formatted}{comma}")
    lines.append("};")
    return "\n".join(lines)


def replace_dealer_data_block(html, new_js_block, var_name="dealerData"):
    """
    Replace the `const dealerData = { ... };` block in the HTML.

    Uses regex to match from `const dealerData = {` through the closing `};`
    handling nested braces properly.
    """
    # Pattern to find the start of the declaration
    pattern_start = re.escape(f"const {var_name} = {{")

    match = re.search(pattern_start, html)
    if not match:
        return html, False

    start_idx = match.start()

    # Now find the matching closing `};` by counting braces
    brace_depth = 0
    i = match.end() - 1  # Position of the opening `{`
    in_string = False
    string_char = None
    escape_next = False

    while i < len(html):
        ch = html[i]

        if escape_next:
            escape_next = False
            i += 1
            continue

        if ch == "\\":
            escape_next = True
            i += 1
            continue

        if in_string:
            if ch == string_char:
                in_string = False
        else:
            if ch in ('"', "'", "`"):
                in_string = True
                string_char = ch
            elif ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    # Found the closing brace. Include the semicolon if present.
                    end_idx = i + 1
                    if end_idx < len(html) and html[end_idx] == ";":
                        end_idx += 1
                    return html[:start_idx] + new_js_block + html[end_idx:], True
        i += 1

    return html, False


def replace_report_dealer_const(html, new_js_block):
    """
    Replace the `const dealer = { name: "...", ... };` block in the report HTML.
    """
    return replace_dealer_data_block(html, new_js_block, var_name="dealer")


def replace_hardcoded_dealer_name_in_report(html, dealer_name):
    """
    Replace hardcoded '1FOTEAM' references in the report HTML with the dealer name.
    This covers the <title> tag, translation strings, and static HTML text.
    """
    # Replace in title tag
    html = re.sub(
        r"(<title>.*?)1FOTEAM(.*?</title>)",
        lambda m: m.group(1) + dealer_name + m.group(2),
        html,
    )

    # Replace 1FOTEAM in the T translation object strings and HTML attributes
    # We need to be careful to replace ALL occurrences since it appears in many places
    html = html.replace("1FOTEAM", dealer_name)

    return html


def replace_hardcoded_dealer_name_in_landing(html, dealer_name):
    """Replace hardcoded '1FOTEAM' references in the landing page."""
    html = html.replace("1FOTEAM", dealer_name)
    return html


def replace_report_score_circle(html, score):
    """
    Update the score circle SVG and displayed score number in the report.
    The circle has radius 54, circumference = 2*pi*54 = 339.29.
    stroke-dashoffset = circumference * (1 - score/100)
    """
    circumference = 339.29

    if score < 0:
        # Pending: show "?" instead of a number, empty circle
        dash_offset = circumference  # empty circle
        score_display = "?"
        score_color = "var(--gray-400)"
    elif score <= 20:
        dash_offset = round(circumference * (1 - score / 100), 2)
        score_display = str(score)
        score_color = "var(--danger)"
    elif score <= 50:
        dash_offset = round(circumference * (1 - score / 100), 2)
        score_display = str(score)
        score_color = "var(--warning)"
    else:
        dash_offset = round(circumference * (1 - score / 100), 2)
        score_display = str(score)
        score_color = "var(--success)"

    # Replace the stroke-dashoffset value
    html = re.sub(
        r'stroke-dasharray="339\.29"\s+stroke-dashoffset="[^"]*"',
        f'stroke-dasharray="339.29" stroke-dashoffset="{dash_offset}"',
        html,
    )

    # Replace the stroke color on the progress circle
    html = re.sub(
        r'(stroke-dasharray="339\.29".*?stroke=")var\(--[a-z]+\)(")',
        lambda m: m.group(1) + score_color + m.group(2),
        html,
        flags=re.DOTALL,
    )

    # Replace the score number display
    html = re.sub(
        r'(<span class="score-circle__number"[^>]*>)\d+(<)',
        lambda m: m.group(1) + score_display + m.group(2),
        html,
    )

    # Replace the score number color
    html = re.sub(
        r'(<span class="score-circle__number" style="color:)var\(--[a-z]+\);',
        lambda m: m.group(1) + score_color + ";",
        html,
    )

    return html


def replace_report_dashboard_stats(html, dealer_data_landing):
    """Update the hardcoded dashboard stats (revenue, response time) in report."""
    revenue = dealer_data_landing["revenue_leak_monthly"]
    time_str = dealer_data_landing["mystery_shop_response_time"]

    # Format revenue for display
    if revenue >= 1000:
        rev_display = f"&euro;{revenue:,}".replace(",", ".")
    else:
        rev_display = f"&euro;{revenue}"

    # Replace the revenue stat
    html = re.sub(
        r'(<div class="stat-card__number" style="color:var\(--danger\);">)&euro;709(</div>\s*<div class="stat-card__label" data-t="dashStat0">)',
        lambda m: m.group(1) + rev_display + m.group(2),
        html,
    )

    # Replace the response time stat (extract just hours portion for display)
    minutes = dealer_data_landing["mystery_shop_response_minutes"]
    if minutes == -1:
        time_display = "—"
    elif minutes == 9999:
        time_display = "∞"
    else:
        h = minutes // 60
        time_display = f"{h}h" if h > 0 else f"{minutes}min"

    html = re.sub(
        r'(<div class="stat-card__number" style="color:var\(--danger\);">)18h(</div>\s*<div class="stat-card__label" data-t="dashStat1">)',
        lambda m: m.group(1) + time_display + m.group(2),
        html,
    )

    return html


def replace_report_dimension_scores(html, score, minutes):
    """
    Update dimension scores in the report based on the dealer's actual performance.
    The response_time dimension score is derived from minutes.
    Other dimensions get default scores for mystery-shopped dealers.
    """
    # Calculate response_time score (out of 5)
    if minutes == -1:
        rt_score = 0  # pending
    elif minutes == 9999:
        rt_score = 1  # no response
    elif minutes <= 15:
        rt_score = 5
    elif minutes <= 30:
        rt_score = 4
    elif minutes <= 120:
        rt_score = 3
    elif minutes <= 720:
        rt_score = 2
    else:
        rt_score = 1

    # Replace the response_time score in all language arrays of dimensionsT.
    # Pattern: { key: "response_time", name: "...", score: X,
    html = re.sub(
        r'(\{\s*key:\s*"response_time"[^}]*?score:\s*)\d+',
        lambda m: m.group(1) + str(rt_score),
        html,
    )

    return html


def update_landing_links(html):
    """Replace links to aello-dealer-report.html with report.html in landing page."""
    html = html.replace("aello-dealer-report.html", "report.html")
    return html


def update_report_links(html):
    """Replace links to aello-dealer-landing.html with index.html in report page."""
    html = html.replace("aello-dealer-landing.html", "index.html")
    return html


def generate_index_page(dealers_info):
    """Generate the root index.html listing all dealers."""
    rows = []
    for info in sorted(dealers_info, key=lambda x: x["name"]):
        rows.append(
            f'      <tr>'
            f'<td><a href="{info["slug"]}/index.html">{info["name"]}</a></td>'
            f'<td>{info["city"]}</td>'
            f'<td>{info["listings"]}</td>'
            f'<td>{info["response"]}</td>'
            f'<td><a href="{info["slug"]}/index.html">Landing</a> · '
            f'<a href="{info["slug"]}/report.html">Report</a></td>'
            f'</tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Aello Dealer Sites — Directory</title>
<style>
  body {{ font-family: 'Inter', -apple-system, sans-serif; margin: 40px auto; max-width: 1100px; padding: 0 24px; color: #1a1a1a; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 8px; }}
  p {{ color: #6b7280; margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ text-align: left; padding: 10px 14px; border-bottom: 1px solid #e5e7eb; }}
  th {{ font-weight: 700; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; color: #6b7280; background: #f8fafb; }}
  tr:hover td {{ background: #f8fafb; }}
  a {{ color: #007C89; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .count {{ font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<h1>Aello Dealer Sites</h1>
<p>Generated {len(dealers_info)} personalized dealer pages.</p>
<table>
  <thead>
    <tr><th>Dealer</th><th>City</th><th>Listings</th><th>Response</th><th>Pages</th></tr>
  </thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table>
</body>
</html>"""


def main():
    # ── Load data ──────────────────────────────────────────────────────────────
    print(f"Loading dealer data from {DATA_FILE}")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        dealers = json.load(f)
    print(f"  Found {len(dealers)} dealers")

    print(f"Loading landing template from {LANDING_TEMPLATE}")
    with open(LANDING_TEMPLATE, "r", encoding="utf-8") as f:
        landing_html = f.read()

    print(f"Loading report template from {REPORT_TEMPLATE}")
    with open(REPORT_TEMPLATE, "r", encoding="utf-8") as f:
        report_html = f.read()

    # ── Create output directory ────────────────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Process each dealer ────────────────────────────────────────────────────
    dealers_info = []
    errors = []
    processed = 0

    for dealer in dealers:
        dealer_name = dealer.get("dealer_name", "").strip()
        if not dealer_name:
            errors.append("Skipped dealer with empty name")
            continue

        slug = slugify(dealer_name)
        if not slug:
            errors.append(f"Skipped dealer '{dealer_name}' — could not generate slug")
            continue

        try:
            # Build dealer data objects
            landing_data = build_dealer_data_landing(dealer)
            report_data = build_dealer_data_report(dealer)
            score = report_data["overall_score"]
            minutes = report_data["mystery_shop_response_minutes"]

            # ── Landing page ───────────────────────────────────────────────────
            landing = landing_html  # start from fresh template each time

            # Replace dealerData JS block
            landing_js = dealer_data_to_js(landing_data, "dealerData", "const")
            landing, replaced = replace_dealer_data_block(landing, landing_js, "dealerData")
            if not replaced:
                errors.append(f"[{dealer_name}] Could not find dealerData block in landing template")

            # Replace hardcoded dealer name
            landing = replace_hardcoded_dealer_name_in_landing(landing, dealer_name)

            # Update links
            landing = update_landing_links(landing)

            # ── Report page ────────────────────────────────────────────────────
            report = report_html  # start from fresh template each time

            # Replace the `const dealer = { ... };` block
            report_js = dealer_data_to_js(report_data, "dealer", "const")
            report, replaced = replace_report_dealer_const(report, report_js)
            if not replaced:
                errors.append(f"[{dealer_name}] Could not find dealer const block in report template")

            # Replace hardcoded dealer name
            report = replace_hardcoded_dealer_name_in_report(report, dealer_name)

            # Update score circle
            report = replace_report_score_circle(report, score)

            # Update dashboard stats
            report = replace_report_dashboard_stats(report, landing_data)

            # Update dimension scores based on response time
            report = replace_report_dimension_scores(report, score, minutes)

            # Replace hardcoded score "27" in chart title and translations
            score_str = str(score) if score >= 0 else "?"
            report = report.replace("De 27 ", f"De {score_str} ")
            report = report.replace("From 27 ", f"From {score_str} ")
            report = report.replace("Van 27 ", f"Van {score_str} ")

            # Update links
            report = update_report_links(report)

            # ── Write files ────────────────────────────────────────────────────
            dealer_dir = os.path.join(OUTPUT_DIR, slug)
            os.makedirs(dealer_dir, exist_ok=True)

            landing_path = os.path.join(dealer_dir, "index.html")
            with open(landing_path, "w", encoding="utf-8") as f:
                f.write(landing)

            report_path = os.path.join(dealer_dir, "report.html")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)

            # Track info for index page
            dealers_info.append({
                "name": dealer_name,
                "slug": slug,
                "city": dealer.get("city", ""),
                "listings": dealer.get("listings_count", 0),
                "response": landing_data["mystery_shop_response_time"],
            })

            processed += 1

        except Exception as e:
            errors.append(f"[{dealer_name}] Error: {e}")

    # ── Generate root index page ───────────────────────────────────────────────
    index_html = generate_index_page(dealers_info)
    index_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\nDone!")
    print(f"  Dealers processed: {processed}/{len(dealers)}")
    print(f"  Output directory:  {OUTPUT_DIR}")
    print(f"  Index page:        {index_path}")

    if errors:
        print(f"\n  Warnings/Errors ({len(errors)}):")
        for err in errors:
            print(f"    - {err}")
    else:
        print(f"  No errors.")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
