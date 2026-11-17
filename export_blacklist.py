#!/usr/bin/env python3
"""Export your Bilibili blacklist (blocked users) to CSV / TXT / JSON.

Python 3.8+ | standard library only | no third-party dependencies.

Get your login cookie from the browser: F12 -> Network -> any request to
bilibili.com -> Request Headers -> Cookie. Keep it in `cookie.txt` (git-ignored)
or pass it with --cookie / the BILI_COOKIE environment variable.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

API = "https://api.bilibili.com/x/relation/blacks"
PAGE_SIZE = 50          # the server caps ps at 50 even if you ask for more
MAX_PAGES = 200         # hard stop to avoid an infinite loop
FIELDS = ["uid", "uname", "blocked_at", "space_url", "sign"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://account.bilibili.com/account/blacklist",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

ERROR_HINTS = {
    -101: "Cookie is missing or expired. Log in to bilibili.com and copy a fresh one.",
    -352: "Risk control triggered. Increase --delay (e.g. 1.0) and retry later.",
    412: "Request rejected by the anti-crawl layer. Increase --delay and retry.",
    -403: "Access denied. Check that the Cookie belongs to the logged-in account.",
}


def load_cookie(args: argparse.Namespace) -> str:
    if args.cookie:
        return args.cookie.strip()
    env = os.environ.get("BILI_COOKIE")
    if env:
        return env.strip()
    path = args.cookie_file
    if not os.path.isabs(path) and not os.path.exists(path):
        # Also look next to the script, so running from another cwd still works.
        beside_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        if os.path.exists(beside_script):
            path = beside_script
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return ""


def fetch_page(pn: int, cookie: str, timeout: float) -> dict:
    url = "%s?re_src=32&pn=%d&ps=%d" % (API, pn, PAGE_SIZE)
    headers = dict(HEADERS, Cookie=cookie)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect(cookie: str, delay: float, timeout: float):
    """Return (rows_by_uid, declared_total)."""
    rows: dict[str, dict] = {}
    total = None
    for pn in range(1, MAX_PAGES + 1):
        try:
            payload = fetch_page(pn, cookie, timeout)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("page %d request failed: %s" % (pn, exc)) from exc

        code = payload.get("code")
        if code != 0:
            hint = ERROR_HINTS.get(code, payload.get("message", ""))
            raise RuntimeError("API returned code=%s (%s)" % (code, hint))

        data = payload.get("data") or {}
        if total is None:
            total = data.get("total")
        batch = data.get("list") or []
        for user in batch:
            rows[str(user["mid"])] = user
        print("page %02d: +%-2d  accumulated %d / %s"
              % (pn, len(batch), len(rows), total if total is not None else "?"))

        if not batch:
            break
        if total is not None and len(rows) >= total:
            break
        time.sleep(delay)
    return rows, total


def normalize(rows: dict[str, dict]) -> list[dict]:
    out = []
    for uid, user in rows.items():
        try:
            dt = datetime.fromtimestamp(user.get("mtime") or 0).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError, OverflowError):
            dt = ""
        out.append({
            "uid": uid,
            "uname": user.get("uname") or "",
            "blocked_at": dt,
            "space_url": "https://space.bilibili.com/" + uid,
            "sign": (user.get("sign") or "").replace("\r", " ").replace("\n", " "),
        })
    out.sort(key=lambda r: int(r["uid"]))
    return out


def write_outputs(out: list[dict], directory: str, formats: list[str], name: str):
    os.makedirs(directory, exist_ok=True)
    written = []

    if "csv" in formats:
        path = os.path.join(directory, name + ".csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(out)
        written.append(path)

    if "txt" in formats:
        path = os.path.join(directory, name + "_uids.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(r["uid"] for r in out) + "\n")
        written.append(path)

    if "json" in formats:
        path = os.path.join(directory, name + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        written.append(path)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Bilibili blacklist UIDs. Cookie never leaves your machine."
    )
    parser.add_argument("--cookie", help="Cookie header value (prefer cookie.txt instead)")
    parser.add_argument("--cookie-file", default="cookie.txt", help="File containing the Cookie (default: cookie.txt)")
    parser.add_argument("--out", default="output", help="Output directory (default: output)")
    parser.add_argument("--name", default="bilibili_blacklist", help="Output filename prefix")
    parser.add_argument("--formats", default="csv,txt", help="Comma-separated: csv,txt,json (default: csv,txt)")
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between pages (default: 0.25)")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout (default: 20)")
    args = parser.parse_args()

    cookie = load_cookie(args)
    if not cookie:
        print("No login credential found.\n"
              "Create a file named 'cookie.txt' next to this script, or pass "
              "--cookie / set BILI_COOKIE.\n"
              "F12 -> Network -> any bilibili.com request -> Request Headers -> Cookie.",
              file=sys.stderr)
        return 2

    formats = [s.strip().lower() for s in args.formats.split(",") if s.strip()]
    unknown = set(formats) - {"csv", "txt", "json"}
    if unknown:
        print("Unsupported format(s): %s" % ", ".join(sorted(unknown)), file=sys.stderr)
        return 2

    try:
        rows, total = collect(cookie, args.delay, args.timeout)
    except RuntimeError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1

    out = normalize(rows)
    paths = write_outputs(out, args.out, formats, args.name)
    print("\nExported %d unique UIDs (API declared total: %s)"
          % (len(out), total if total is not None else "unknown"))
    for path in paths:
        print("  " + os.path.abspath(path))
    if total is not None and len(out) != total:
        print("Warning: unique count differs from API total; some pages may have "
              "contained duplicate entries.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
