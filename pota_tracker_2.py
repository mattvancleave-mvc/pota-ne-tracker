#!/usr/bin/env python3
"""
POTA Nebraska Park Tracker — improved

- Saves daily snapshots only if there are new/removed parks
- Maintains history in pota_data/
- Sends email with summary of changes
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Configuration ──────────────────────────────────────────────

LOCATION_CODE = "US-NE"
API_URL = f"https://api.pota.app/location/parks/{LOCATION_CODE}"
DATA_DIR = "./pota_data"

SENDER_EMAIL = "clubfullofpinkponies@gmail.com"
APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")  # GitHub secret
RECEIVER_EMAIL = "mattvancleave@gmail.com"

# ── Helpers ───────────────────────────────────────────────────

def snapshot_filename(date: datetime) -> str:
    return os.path.join(DATA_DIR, f"parks_{date.strftime('%Y-%m-%d')}.json")

def fetch_parks() -> list[dict]:
    try:
        resp = requests.get(API_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "parks" in data:
            return data["parks"]
        else:
            print("Unexpected API response format")
            sys.exit(1)
    except requests.RequestException as e:
        print("API request failed:", e)
        sys.exit(1)

def load_snapshot(filepath: str) -> dict[str, dict] | None:
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r") as f:
        parks_list = json.load(f)
    return {park["reference"]: park for park in parks_list}

def save_snapshot(parks: list[dict], filepath: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(parks, f, indent=2)

def compare_snapshots(today: dict[str, dict], yesterday: dict[str, dict]) -> dict:
    today_refs = set(today.keys())
    yesterday_refs = set(yesterday.keys())
    new_parks = [today[r] for r in sorted(today_refs - yesterday_refs)]
    removed_parks = [yesterday[r] for r in sorted(yesterday_refs - today_refs)]
    return {"new_parks": new_parks, "removed_parks": removed_parks,
            "total_today": len(today_refs), "total_yesterday": len(yesterday_refs)}

def format_email(diff: dict) -> str:
    lines = [
        f"Park count: {diff['total_yesterday']} → {diff['total_today']}",
        f"Net change: {diff['total_today'] - diff['total_yesterday']:+d}\n"
    ]
    if diff["new_parks"]:
        lines.append(f"🆕 NEW PARKS ({len(diff['new_parks'])}):")
        for p in diff["new_parks"]:
            lines.append(f"  + {p.get('reference', '???')}  {p.get('name', 'Unknown')}")
    if diff["removed_parks"]:
        lines.append(f"❌ REMOVED PARKS ({len(diff['removed_parks'])}):")
        for p in diff["removed_parks"]:
            lines.append(f"  - {p.get('reference', '???')}  {p.get('name', 'Unknown')}")
    if not diff["new_parks"] and not diff["removed_parks"]:
        lines.append("✅ No changes since last snapshot.")
    return "\n".join(lines)

def send_email(subject: str, body: str):
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)

# ── Main ──────────────────────────────────────────────────────

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    today = datetime.now()
    yesterday = today - timedelta(days=1)

    today_file = snapshot_filename(today)
    yesterday_file = snapshot_filename(yesterday)

    parks_list = fetch_parks()
    today_map = {p["reference"]: p for p in parks_list}

    yesterday_map = load_snapshot(yesterday_file)

    # fallback to latest snapshot if yesterday missing
    if yesterday_map is None:
        files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".json")])
        if files:
            yesterday_map = load_snapshot(os.path.join(DATA_DIR, files[-1]))
        else:
            yesterday_map = {}

    diff = compare_snapshots(today_map, yesterday_map)

    # only save snapshot if there are changes
    if diff["new_parks"] or diff["removed_parks"]:
        save_snapshot(parks_list, today_file)

    # send email
    subject = f"POTA Nebraska Park Tracker — {today.strftime('%Y-%m-%d')}"
    body = format_email(diff)
    send_email(subject, body)
    print(body)

if __name__ == "__main__":
    main()
