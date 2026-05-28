#!/usr/bin/env python3
"""
Google AI Mode through a dedicated real-Chrome CDP profile.

This is browser automation, not a stable Google API. It mirrors the Google Drive
CDP pattern: launch real Chrome with a dedicated profile, attach with Playwright,
submit the query, and extract the rendered AI Mode answer text.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tool_connections.shared_utils.browser import sync_playwright

CHROME_APP = "Google Chrome"
CDP_PORT = 9236
PROFILE_DIR = Path.home() / ".browser_automation" / "google_ai_mode_cdp_profile"
AI_MODE_URL = "https://www.google.com/aimode"


def cdp_ready(port: int = CDP_PORT) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


def launch_chrome(port: int = CDP_PORT, profile_dir: Path = PROFILE_DIR, url: str = AI_MODE_URL) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)
    # Only remove locks for this dedicated automation profile.
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            (profile_dir / name).unlink()
        except FileNotFoundError:
            pass

    subprocess.Popen(
        [
            "open",
            "-na",
            CHROME_APP,
            "--args",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            "--window-size=1400,900",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(60):
        time.sleep(0.25)
        if cdp_ready(port):
            return
    raise RuntimeError(f"Chrome CDP did not start on port {port}")


def ensure_chrome(port: int = CDP_PORT, profile_dir: Path = PROFILE_DIR) -> None:
    if not cdp_ready(port):
        launch_chrome(port=port, profile_dir=profile_dir)


def extract_answer_lines(page) -> list[str]:
    text = page.locator("body").inner_text(timeout=10_000)
    lines: list[str] = []
    skip_fragments = (
        "google apps",
        "settings",
        "privacy",
        "terms",
        "skip to main content",
        "accessibility help",
        "ai can make mistakes",
    )
    for line in text.splitlines():
        value = line.strip()
        if not value or len(value) < 18:
            continue
        lower = value.lower()
        if any(fragment in lower for fragment in skip_fragments):
            continue
        if value not in lines:
            lines.append(value)
    return lines


def wait_for_ai_mode(page, timeout_ms: int = 25_000) -> None:
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        try:
            text = page.locator("body").inner_text(timeout=2_000)
            if "AI Mode response is ready" in text:
                return
        except Exception:
            pass
        time.sleep(1)


def ask_google_ai_mode(query: str, followups: list[str] | None = None, port: int = CDP_PORT) -> dict:
    ensure_chrome(port)
    followups = followups or []
    url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query, "udm": "50"})

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        wait_for_ai_mode(page)

        turns = [{"query": query, "lines": extract_answer_lines(page), "url": page.url}]

        for followup in followups:
            textbox = page.locator("textarea").last
            textbox.click(timeout=5_000)
            page.keyboard.press("Meta+A")
            page.keyboard.type(followup, delay=10)
            page.keyboard.press("Enter")
            wait_for_ai_mode(page)
            turns.append({"query": followup, "lines": extract_answer_lines(page), "url": page.url})

        browser.close()
        return {"turns": turns}


def main() -> None:
    parser = argparse.ArgumentParser(description="Query Google AI Mode through a signed-in Chrome CDP profile.")
    parser.add_argument("query", nargs="?", help="Initial AI Mode query")
    parser.add_argument("--followup", action="append", default=[], help="Follow-up query; repeat for multi-turn")
    parser.add_argument("--setup", action="store_true", help="Open Google AI Mode for manual Google sign-in")
    parser.add_argument("--port", type=int, default=CDP_PORT)
    args = parser.parse_args()

    if args.setup:
        launch_chrome(port=args.port)
        print(f"Opened Google AI Mode in {PROFILE_DIR}")
        print("Sign in manually, then rerun this script without --setup.")
        return

    if not args.query:
        parser.error("query is required unless --setup is used")

    print(json.dumps(ask_google_ai_mode(args.query, args.followup, port=args.port), indent=2))


if __name__ == "__main__":
    main()
