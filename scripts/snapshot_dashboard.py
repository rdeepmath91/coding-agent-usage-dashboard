#!/usr/bin/env python3
"""Capture a local dashboard screenshot and lightweight DOM health summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot the local coding-agent usage dashboard.")
    parser.add_argument("--url", default="http://localhost:8321", help="Dashboard URL to inspect")
    parser.add_argument("--out", default="dashboard-snapshots", help="Output directory")
    parser.add_argument("--wait", default="#model-table-body td", help="Selector that confirms data rendered")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    screenshot_path = out_dir / f"dashboard-{stamp}.png"
    summary_path = out_dir / f"dashboard-{stamp}.json"

    console_messages: list[dict[str, str]] = []
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        page.on("console", lambda msg: console_messages.append({"type": msg.type, "text": msg.text}))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        response = page.goto(args.url, wait_until="networkidle")
        page.wait_for_selector(args.wait, timeout=10_000)
        page.screenshot(path=screenshot_path, full_page=True)

        summary = {
            "url": page.url,
            "status": response.status if response else None,
            "title": page.title(),
            "logo": page.locator(".logo").inner_text(timeout=5_000).strip(),
            "overview_cards": page.locator(".stat-card").count(),
            "legend_items": page.locator("#chart-legend .legend-item").count(),
            "model_rows": page.locator("#model-table-body tr").count(),
            "usage_rows": page.locator("#usage-table-body tr").count(),
            "first_model": page.locator("#model-table-body td").first.inner_text(timeout=5_000).strip(),
            "console_messages": console_messages,
            "page_errors": page_errors,
            "screenshot": str(screenshot_path),
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        browser.close()

    print(json.dumps({"screenshot": str(screenshot_path), "summary": str(summary_path), "title": summary["title"], "errors": len(page_errors)}, indent=2))


if __name__ == "__main__":
    main()
