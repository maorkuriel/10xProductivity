#!/usr/bin/env python3
"""
Google AI Mode SSO — open or resume the dedicated Chrome profile.

Checks whether the existing profile has a valid signed-in Google session
before asking the user to sign in again.  Use --force to skip the check.

Standalone usage:
    python3 tool_connections/google-ai-mode/sso.py
    python3 tool_connections/google-ai-mode/sso.py --force
"""

import argparse
import sys
import time
from pathlib import Path

from google_ai_mode import (
    AI_MODE_URL, CDP_PORT, PROFILE_DIR,
    cdp_ready, ensure_chrome, launch_chrome,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from tool_connections.shared_utils.browser import sync_playwright


def check(port: int = CDP_PORT) -> bool:
    """Return True if the profile has a valid signed-in Google session."""
    if not cdp_ready(port):
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(AI_MODE_URL, wait_until="domcontentloaded", timeout=15_000)
            time.sleep(3)
            url = page.url.lower()
            signed_in = (
                "accounts.google.com" not in url
                and "sorry/index" not in url
            )
            browser.close()
            return signed_in
    except Exception:
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Open or resume the Google AI Mode Chrome profile.")
    parser.add_argument("--force", action="store_true",
                        help="Open Chrome for sign-in even if session is valid")
    args = parser.parse_args()

    if not args.force and PROFILE_DIR.exists():
        try:
            ensure_chrome()
            if check():
                print(f"Session valid — profile: {PROFILE_DIR}")
                print("No sign-in needed. Use --force to re-authenticate.")
                sys.exit(0)
        except Exception:
            pass

    launch_chrome()
    print(f"Opened Google AI Mode profile: {PROFILE_DIR}")
    print("Sign in to Google in the Chrome window.")
    print("The session persists in this dedicated profile.")
