#!/usr/bin/env python3

import json
import os
import sys
import requests
from datetime import datetime, timedelta
import smtplib
import io
from contextlib import redirect_stdout
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Configuration ─────────────────────────────────────────

LOCATION_CODE = "US-NE"
API_URL = f"https://api.pota.app/location/parks/{LOCATION_CODE}"
DATA_DIR = "./pota_data"
LOG_FILE = os.path.join(DATA_DIR, "change_log.json")

SENDER_EMAIL = "clubfullofpinkponies@gmail.com"
APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECEIVER_EMAIL = "mattvancleave@gmail.com"

# ── Helpers ───────────────────────────────────────────────

def snapshot_filename(date: datetime) -> str:
    return os.path.join(DATA_DIR, f"parks_{date.strftime('%Y-%m-%d')}.json")


def fetch_parks() -> list[dict]:
    print(f"Fetching parks from: {API_URL}")
    try:
        response = requests.get(API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            parks = data
        elif isinstance(data, dict) and "parks" in data:
            parks = data["parks"]
        else:
            print("Unexpected API response format")
            sys.exit(1)

        print(f"✓ Retrieved {len(parks)} parks")
        return parks

    except requests.RequestException as e:
        print(f"API request failed: {e}")
        sys.exit(1)


def load_snapshot(filepath: str):
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r") as f:
        parks_list = json.load(f)
    return {park["reference"]: park for park in parks_list}


def save_snapshot(parks: list[dict], filepath: str):
    with open(filepath, "w") as f:
        json.dump(parks, f, indent=2)
    print(f"✓ Snapshot saved to: {filepath}")


def compare_snapshots(today, yesterday):

    today_refs = set(today.keys())
    yesterday_refs = set(yesterday.keys())

    new_parks = [today[r] for r in sorted(today_refs - yesterday_refs)]
    removed_parks = [yesterday[r] for r in sorted(yesterday_refs - today_refs)]

    return {
        "new_parks": new_parks,
        "removed_parks": removed_parks,
        "total_today": len(today_refs),
        "total_yesterday": len(yesterday_refs),
    }


def print_park(park: dict, label=""):
    ref = park.get("reference", "???")
    name = park.get("name", "Unknown")
    loc = park.get("locationDesc", park.get("locationName", ""))
    print(f"{label}{ref}  {name}  [{loc}]")


def append_to_log(entry):

    log = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            log = json.load(f)

    log.append(entry)

    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)

    print(f"✓ Change log updated: {LOG_FILE}")


# ── Email Sender ──────────────────────────────────────────

def send_email(subject, body):

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)

    print("Email sent successfully!")


# ── Main Script ───────────────────────────────────────────

def main():

    os.makedirs(DATA_DIR, exist_ok=True)

    today = datetime.now()
    yesterday = today - timedelta(days=1)

    today_file = snapshot_filename(today)
    yesterday_file = snapshot_filename(yesterday)

    print("="*60)
    print(f"POTA Nebraska Park Tracker — {today.strftime('%Y-%m-%d')}")
    print("="*60)

    parks_list = fetch_parks()
    save_snapshot(parks_list, today_file)

    today_map = {park["reference"]: park for park in parks_list}

    yesterday_map = load_snapshot(yesterday_file)

    if yesterday_map is None:

        older_files = sorted([
            f for f in os.listdir(DATA_DIR)
            if f.startswith("parks_") and f.endswith(".json") and f != os.path.basename(today_file)
        ])

        if older_files:
            last_file = os.path.join(DATA_DIR, older_files[-1])
            print(f"No snapshot yesterday. Using {older_files[-1]}")
            yesterday_map = load_snapshot(last_file)
        else:
            print("No previous snapshot found.")
            print(f"Nebraska currently has {len(parks_list)} parks.")
            return

    diff = compare_snapshots(today_map, yesterday_map)

    print()
    print(f"Park count: {diff['total_yesterday']} → {diff['total_today']}")
    print(f"Net change: {diff['total_today'] - diff['total_yesterday']:+d}")
    print()

    if diff["new_parks"]:
        print(f"NEW PARKS ADDED ({len(diff['new_parks'])})")
        for park in diff["new_parks"]:
            print_park(park, "+ ")
    else:
        print("No new parks added.")

    print()

    if diff["removed_parks"]:
        print(f"PARKS REMOVED ({len(diff['removed_parks'])})")
        for park in diff["removed_parks"]:
            print_park(park, "- ")
    else:
        print("No parks removed.")

    if diff["new_parks"] or diff["removed_parks"]:

        log_entry = {
            "date": today.strftime("%Y-%m-%d"),
            "total_today": diff["total_today"],
            "total_yesterday": diff["total_yesterday"],
            "new_parks": diff["new_parks"],
            "removed_parks": diff["removed_parks"],
        }

        append_to_log(log_entry)

    print("="*60)


# ── Run and Capture Output ─────────────────────────────────

if __name__ == "__main__":

    buffer = io.StringIO()

    with redirect_stdout(buffer):
        main()

    email_body = buffer.getvalue()

    subject = f"POTA Nebraska Park Tracker — {datetime.now().strftime('%Y-%m-%d')}"

    send_email(subject, email_body)


    print(email_body)
