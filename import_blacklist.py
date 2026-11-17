#!/usr/bin/env python3
"""Import a UID list into another Bilibili account's blacklist.

This is a WRITE operation. By default the script runs a dry-run and changes
nothing. You must pass --apply to actually block users.

Python 3.8+ | standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

MODIFY_API = "https://api.bilibili.com/x/relation/modify"
BLACKS_API = "https://api.bilibili.com/x/relation/blacks"
NAV_API = "https://api.bilibili.com/x/web-interface/nav"

ACT_BLOCK = 5            # confirmed: 5 = block, 6 = unblock
ATTRIBUTE_BLOCKED = 128  # bit flag meaning "blocked"
PAGE_SIZE = 50

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# Codes where retrying the same request will not help.
FATAL_CODES = {
    -101: "Not logged in / cookie expired.",
    -403: "Access denied (CSRF rejected).",
    -352: "Risk control triggered. Stop and retry later with a larger --delay.",
    412: "Request blocked by anti-crawl layer. Stop and retry later.",
    22001: "Cannot block yourself.",
}


def load_cookie(args: argparse.Namespace) -> str:
    if args.cookie:
        return args.cookie.strip()
    env = os.environ.get("BILI_COOKIE")
    if env:
        return env.strip()
    path = args.cookie_file
    if not os.path.isabs(path) and not os.path.exists(path):
        beside_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        if os.path.exists(beside_script):
            path = beside_script
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            return f.read().strip()
    return ""


def csrf_from_cookie(cookie: str) -> str | None:
    match = re.search(r"(?:^|;\s*)bili_jct=([^;]+)", cookie)
    return match.group(1).strip() if match else None


def api_get(url: str, cookie: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers=dict(HEADERS, Cookie=cookie))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post_form(url: str, fields: dict, cookie: str, timeout: float) -> dict:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    headers = dict(HEADERS)
    headers["Cookie"] = cookie
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_account(cookie: str, timeout: float) -> tuple[str, str]:
    payload = api_get(NAV_API, cookie, timeout)
    if payload.get("code") != 0:
        raise RuntimeError("Cannot read account info: code=%s %s"
                           % (payload.get("code"), payload.get("message")))
    data = payload.get("data") or {}
    if not data.get("isLogin"):
        raise RuntimeError("Cookie is not logged in. Log in to bilibili.com and copy a fresh Cookie.")
    self_uid = str(data.get("mid") or "")
    self_name = data.get("uname") or "(unknown)"
    return self_uid, self_name


def current_blacklist(cookie: str, timeout: float) -> set[str]:
    blocked: set[str] = set()
    for pn in range(1, 201):
        url = "%s?re_src=32&pn=%d&ps=%d" % (BLACKS_API, pn, PAGE_SIZE)
        payload = api_get(url, cookie, timeout)
        if payload.get("code") != 0:
            raise RuntimeError("Cannot read blacklist on page %d: %s"
                               % (pn, payload.get("message")))
        data = payload.get("data") or {}
        batch = data.get("list") or []
        blocked.update(str(u["mid"]) for u in batch)
        if not batch or len(blocked) >= (data.get("total") or 0):
            break
    return blocked


def load_uids(path: str) -> list[str]:
    """Accept .txt (one UID per line), .csv (uid column), or .json (export format)."""
    if not os.path.exists(path):
        raise RuntimeError("Input file not found: %s" % path)
    ext = os.path.splitext(path)[1].lower()
    uids: list[str] = []

    if ext == ".csv":
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or "uid" not in reader.fieldnames:
                raise RuntimeError("CSV must have a 'uid' column (see examples/sample_output.csv)")
            uids = [row["uid"].strip() for row in reader if row.get("uid")]
    elif ext == ".json":
        raw = json.load(open(path, encoding="utf-8-sig"))
        if isinstance(raw, list):
            uids = [str(row.get("uid") or row.get("mid") or "").strip() for row in raw]
        elif isinstance(raw, dict) and isinstance(raw.get("data"), dict):
            uids = [str(u["mid"]).strip() for u in raw["data"].get("list") or []]
        else:
            raise RuntimeError("Unrecognized JSON structure.")
    else:
        with open(path, encoding="utf-8-sig") as f:
            uids = [line.strip() for line in f]

    # Validate and de-duplicate while preserving order.
    seen: set[str] = set()
    clean: list[str] = []
    for uid in uids:
        uid = uid.strip().strip('"\'')
        if not uid or not re.fullmatch(r"\d+", uid):
            continue
        if uid not in seen:
            seen.add(uid)
            clean.append(uid)
    return clean


def confirm(uids: list[str], self_uid: str, self_name: str, apply: bool, assume_yes: bool) -> bool:
    print("\n=== WRITE OPERATION SUMMARY ===")
    print("  Target account : %s (UID %s)" % (self_name, self_uid))
    print("  UIDs to block  : %d" % len(uids))
    print("  Preview (first 10): %s" % ", ".join(uids[:10]))
    print("  Mode           : %s" % ("APPLY - changes WILL be made" if apply else "DRY-RUN - no changes"))
    if not apply:
        print("\nDry-run only. Re-run with --apply to actually block users.")
        return False
    if not assume_yes:
        answer = input('\nType "yes" to confirm, anything else to abort: ').strip().lower()
        if answer != "yes":
            print("Aborted by user.")
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import UIDs into a Bilibili blacklist. Dry-run by default."
    )
    parser.add_argument("input", help="TXT (one UID/line), CSV with uid column, or exported JSON")
    parser.add_argument("--cookie", help="Cookie string (prefer cookie.txt)")
    parser.add_argument("--cookie-file", default="cookie.txt", help="Cookie file (default: cookie.txt)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually perform blocking. Without this flag nothing is written.")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds between block requests (default: 1.5, conservative)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process the first N UIDs (0 = all). Useful for a small trial batch.")
    parser.add_argument("--log", default="import_log.jsonl", help="Per-UID result log (JSON Lines)")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout")
    args = parser.parse_args()

    cookie = load_cookie(args)
    if not cookie:
        print("No login credential found. Create cookie.txt or pass --cookie / BILI_COOKIE.",
              file=sys.stderr)
        return 2
    csrf = csrf_from_cookie(cookie)
    if not csrf:
        print("Cookie is missing bili_jct (CSRF token). Log in again and copy the full Cookie.",
              file=sys.stderr)
        return 2

    try:
        self_uid, self_name = get_account(cookie, args.timeout)
        all_uids = load_uids(args.input)
    except RuntimeError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1

    if args.limit > 0:
        all_uids = all_uids[:args.limit]

    # Never block yourself, and skip people already blocked.
    pending = [uid for uid in all_uids if uid != self_uid]
    skipped_self = len(all_uids) - len(pending)
    try:
        already = current_blacklist(cookie, args.timeout)
    except RuntimeError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    todo = [uid for uid in pending if uid not in already]
    skipped_existing = len(pending) - len(todo)

    print("Loaded %d UIDs; %d already blocked, %d are the account itself."
          % (len(all_uids), skipped_existing, skipped_self))
    if skipped_self:
        print("Note: excluded your own UID from the import list.")

    if not confirm(todo, self_uid, self_name, args.apply, args.yes):
        return 0

    if not todo:
        print("Nothing to do.")
        return 0

    log_path = os.path.abspath(args.log)
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    results = {"ok": 0, "failed": 0}
    started = datetime.now().strftime("%Y%m%d_%H%M%S")

    with open(log_path, "a", encoding="utf-8") as log:
        for i, uid in enumerate(todo, 1):
            record = {"time": datetime.now().isoformat(timespec="seconds"),
                      "batch": started, "uid": uid, "action": "block"}
            if not args.apply:
                record["status"] = "dry_run"
                results["ok"] += 1
            else:
                try:
                    payload = api_post_form(
                        MODIFY_API,
                        {"fid": uid, "act": ACT_BLOCK, "re_src": 11, "csrf": csrf},
                        cookie, args.timeout,
                    )
                    code = payload.get("code")
                    record["code"] = code
                    record["message"] = payload.get("message")
                    if code == 0:
                        record["status"] = "ok"
                        results["ok"] += 1
                    elif code in FATAL_CODES:
                        record["status"] = "fatal"
                        results["failed"] += 1
                        print("\nFatal code %d: %s\nStopping. %d UIDs were processed before the stop."
                              % (code, FATAL_CODES[code], i - 1), file=sys.stderr)
                        log.write(json.dumps(record, ensure_ascii=False) + "\n")
                        break
                    else:
                        record["status"] = "failed"
                        results["failed"] += 1
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                    record["status"] = "error"
                    record["error"] = str(exc)
                    results["failed"] += 1
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            log.flush()
            print("[%d/%d] uid=%s -> %s" % (i, len(todo), uid, record["status"]))

            if i < len(todo) and args.delay > 0:
                time.sleep(args.delay)

    print("\nDone. ok=%d failed=%d" % (results["ok"], results["failed"]))
    print("Log: %s" % log_path)
    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
