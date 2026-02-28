#!/usr/bin/env python3
"""
SSE → OpenClaw Webhook Bridge

Listens to the Pikud HaOref SSE alert stream and forwards matching alerts
to OpenClaw's /hooks/agent endpoint, which delivers via WhatsApp (or any channel).

Usage:
    # Watch for alerts in אשקלון, send to WhatsApp
    python scripts/sse_to_openclaw.py \
        --cities "אשקלון" \
        --to "+972545899945" \
        --channel whatsapp

    # Watch multiple cities
    python scripts/sse_to_openclaw.py \
        --cities "אשקלון,תל אביב,באר שבע" \
        --to "+972545899945"

    # Use environment variables instead of flags
    OPENCLAW_HOOK_TOKEN=my-secret \
    OPENCLAW_HOOK_URL=http://127.0.0.1:18789/hooks/agent \
    SSE_URL=http://localhost:8002/api/alerts-stream \
    WATCH_CITIES="אשקלון" \
    DELIVER_TO="+972545899945" \
    python scripts/sse_to_openclaw.py

Environment Variables:
    SSE_URL              - SSE stream URL (default: local Docker)
    OPENCLAW_HOOK_URL    - OpenClaw webhook URL (default: http://127.0.0.1:18789/hooks/agent)
    OPENCLAW_HOOK_TOKEN  - OpenClaw webhook token (required)
    WATCH_CITIES         - Comma-separated city names in Hebrew
    DELIVER_TO           - WhatsApp number or group JID
    DELIVER_CHANNEL      - Channel: whatsapp, telegram, etc. (default: whatsapp)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("sse-bridge")

DEFAULT_SSE_URL = "http://localhost:8002/api/alerts-stream"
DEFAULT_HOOK_URL = "http://127.0.0.1:18789/hooks/agent"


def parse_args():
    p = argparse.ArgumentParser(description="SSE → OpenClaw webhook bridge for Pikud HaOref alerts")
    p.add_argument("--sse-url", default=os.getenv("SSE_URL", DEFAULT_SSE_URL))
    p.add_argument("--hook-url", default=os.getenv("OPENCLAW_HOOK_URL", DEFAULT_HOOK_URL))
    p.add_argument("--hook-token", default=os.getenv("OPENCLAW_HOOK_TOKEN"))
    p.add_argument("--cities", default=os.getenv("WATCH_CITIES", "אשקלון"),
                    help="Comma-separated city names to watch (Hebrew)")
    p.add_argument("--to", default=os.getenv("DELIVER_TO"),
                    help="Recipient: phone number (+972...) or group JID")
    p.add_argument("--channel", default=os.getenv("DELIVER_CHANNEL", "whatsapp"),
                    help="Delivery channel (default: whatsapp)")
    return p.parse_args()


def city_matches(alert_cities: list[str], watch_cities: set[str]) -> list[str]:
    """Return the subset of alert cities that match our watch list."""
    return [c for c in alert_cities if any(w in c for w in watch_cities)]


def build_message(alert: dict, matched_cities: list[str]) -> str:
    """Build the WhatsApp message from an alert."""
    cities_str = ", ".join(matched_cities)
    alert_type = alert.get("type", alert.get("cat", "unknown"))
    instructions = alert.get("instructions", "")
    title = alert.get("title", "")

    msg = (
        f"🚨 *התרעה — {title or alert_type}*\n"
        f"📍 ערים: {cities_str}\n"
    )
    if instructions:
        msg += f"📋 הנחיות: {instructions}\n"
    return msg


def forward_to_openclaw(hook_url: str, token: str, message: str, channel: str, to: str | None):
    """POST to OpenClaw /hooks/agent."""
    payload: dict = {
        "message": (
            f"Send the following message VERBATIM to the recipient, "
            f"exactly as written, no changes, no summary, no confirmation "
            f"— just the text itself:\n\n{message}"
        ),
        "name": "PikudHaoref",
        "wakeMode": "now",
        "deliver": True,
        "channel": channel,
    }
    if to:
        payload["to"] = to

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    resp = httpx.post(hook_url, json=payload, headers=headers, timeout=15)
    if resp.status_code in (200, 202):
        log.info("✅ Alert forwarded to OpenClaw → %s", channel)
    else:
        log.error("❌ OpenClaw webhook returned %s: %s", resp.status_code, resp.text)


def listen(args):
    """Connect to SSE stream and process events."""
    watch_cities = {c.strip() for c in args.cities.split(",") if c.strip()}
    log.info("👀 Watching cities: %s", watch_cities)
    log.info("📡 SSE: %s", args.sse_url)
    log.info("🔗 Hook: %s", args.hook_url)
    log.info("📱 Deliver: %s → %s", args.channel, args.to or "(last)")

    backoff = 2
    while True:
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream("GET", args.sse_url) as resp:
                    if resp.status_code != 200:
                        log.error("SSE returned %s", resp.status_code)
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 60)
                        continue

                    backoff = 2
                    log.info("✅ Connected to SSE stream")

                    for line in resp.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "keep-alive":
                            continue

                        try:
                            alert = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        cities = alert.get("cities", alert.get("data", []))
                        matched = city_matches(cities, watch_cities)
                        if not matched:
                            continue

                        log.warning("🚨 ALERT matches %s: %s", matched, alert.get("type"))
                        message = build_message(alert, matched)
                        forward_to_openclaw(args.hook_url, args.hook_token, message, args.channel, args.to)

        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            log.warning("SSE disconnected (%s), reconnecting in %ds...", e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except KeyboardInterrupt:
            log.info("Stopped.")
            sys.exit(0)


def main():
    args = parse_args()
    if not args.hook_token:
        log.error("OPENCLAW_HOOK_TOKEN is required (--hook-token or env var)")
        sys.exit(1)
    listen(args)


if __name__ == "__main__":
    main()
