#!/usr/bin/env python3
"""
Fetch Jira issue context for AI pre-analysis.

Outputs a compact summary: description, comments, attachment inventory,
and extracted occurrence time — enough for the AI to decide next steps
without downloading any files.

Usage:
    python fetch_issue_context.py BAIC-12345
    python fetch_issue_context.py BAIC-12345 --json
"""

import os
import sys
import re
import json
import base64
import argparse
from datetime import datetime
from typing import Optional
from urllib.parse import quote

import requests


JIRA_URL  = os.environ.get("JIRA_URL", "")
JIRA_USER = os.environ.get("JIRA_USER", "")
JIRA_PASS = os.environ.get("JIRA_PASS", "")

SEVERITY_FIELD = "customfield_11002"
PROJECT_FIELD  = "customfield_12810"
FAULT_TIME     = "customfield_12812"
CAUSE_STATUS   = "customfield_12902"
FIX_STATUS     = "customfield_12903"
VERIFY_STATUS  = "customfield_12904"

FIELDS = ",".join([
    "summary", "status", "description", "created", "updated",
    "assignee", "reporter", "priority", "resolution",
    "attachment", "comment",
    SEVERITY_FIELD, PROJECT_FIELD, FAULT_TIME,
    CAUSE_STATUS, FIX_STATUS, VERIFY_STATUS,
])

ANDROID_LOG_RE = re.compile(
    r"^android[_\-]?(\d{8})[_\-]?(\d{6})?.*\.(?:zip|gz|tar|7z|rar)(?:\.\d+)?$",
    re.IGNORECASE,
)

ANALYSIS_KEYWORDS = re.compile(
    r"(?i)(?:exception|anr|crash|fatal|watchdog|sigsegv|oom|"
    r"caused\s+by|root\s*cause|gerrit|原因|导致|已修复|已合入|"
    r"BAIC-\d{4,})"
)


def _auth_header() -> dict:
    if not all([JIRA_URL, JIRA_USER, JIRA_PASS]):
        sys.exit("ERROR: set JIRA_URL / JIRA_USER / JIRA_PASS")
    token = base64.b64encode(f"{JIRA_USER}:{JIRA_PASS}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def _safe_value(obj, fallback="N/A"):
    if isinstance(obj, dict):
        return obj.get("value", obj.get("name", obj.get("displayName", str(obj))))
    return str(obj) if obj else fallback


def _classify_attachment(att):
    fn = att.get("filename", "")
    size = att.get("size", 0)
    size_mb = size / 1048576
    if fn.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
        return "image"
    if fn.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        return "video"
    if ANDROID_LOG_RE.match(fn) or ANDROID_LOG_RE.match(re.sub(r'\.\d+$', '', fn)):
        return "android_log"
    if fn.lower().endswith((".log", ".txt")) and size_mb < 50:
        return "small_log"
    if size_mb > 100:
        return "large_archive"
    return "other"


def fetch_and_summarize(key: str) -> dict:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url = f"{JIRA_URL}/rest/api/2/issue/{quote(key)}"
    r = requests.get(url, headers=_auth_header(),
                     params={"fields": FIELDS}, timeout=30, verify=False)
    r.raise_for_status()
    issue = r.json()
    f = issue.get("fields", {})

    severity = _safe_value(f.get(SEVERITY_FIELD))
    project = _safe_value(f.get(PROJECT_FIELD))
    fault_time = f.get(FAULT_TIME, "")
    if fault_time:
        fault_time = str(fault_time)[:19].replace("T", " ")

    desc = (f.get("description") or "")[:2000]
    comments_raw = f.get("comment", {}).get("comments", [])
    attachments = f.get("attachment", [])

    # Classify attachments
    att_groups = {}
    for att in attachments:
        cat = _classify_attachment(att)
        att_groups.setdefault(cat, []).append({
            "filename": att["filename"],
            "size_mb": round(att.get("size", 0) / 1048576, 2),
            "content_url": att.get("content", ""),
        })

    # Summarize comments
    comments_summary = []
    has_analysis_chain = False
    has_gerrit = False
    has_cause = False
    has_fix = False
    for c in comments_raw:
        author = c.get("author", {}).get("displayName", "?")
        created = c.get("created", "")[:16]
        body = c.get("body", "") or ""

        if "gerrit" in body.lower():
            has_gerrit = True
        if re.search(r"【原因分析】|原因[:：]|root\s*cause|caused\s+by", body, re.IGNORECASE):
            has_cause = True
        if re.search(r"【解决方案】|已修复|已合入|fix", body, re.IGNORECASE):
            has_fix = True

        comments_summary.append({
            "author": author,
            "created": created,
            "body": body[:2000],
            "has_keywords": bool(ANALYSIS_KEYWORDS.search(body)),
        })

    has_analysis_chain = has_cause and (has_gerrit or has_fix)

    assignee = f.get("assignee")
    reporter = f.get("reporter")

    return {
        "key": issue.get("key"),
        "summary": f.get("summary", ""),
        "status": f.get("status", {}).get("name", ""),
        "severity": severity,
        "project": project,
        "fault_time": fault_time,
        "created": str(f.get("created", ""))[:16],
        "updated": str(f.get("updated", ""))[:16],
        "assignee": assignee.get("displayName", "N/A") if assignee else "N/A",
        "reporter": reporter.get("displayName", "N/A") if reporter else "N/A",
        "cause_status": _safe_value(f.get(CAUSE_STATUS)),
        "fix_status": _safe_value(f.get(FIX_STATUS)),
        "verify_status": _safe_value(f.get(VERIFY_STATUS)),
        "description": desc,
        "comments_count": len(comments_raw),
        "comments": comments_summary,
        "has_analysis_chain": has_analysis_chain,
        "has_gerrit": has_gerrit,
        "has_cause": has_cause,
        "has_fix": has_fix,
        "attachments_inventory": {
            cat: {
                "count": len(items),
                "total_mb": round(sum(i["size_mb"] for i in items), 2),
                "files": items,
            }
            for cat, items in att_groups.items()
        },
        "total_attachments": len(attachments),
        "total_size_mb": round(sum(a.get("size", 0) for a in attachments) / 1048576, 1),
    }


def print_text_report(ctx: dict):
    print(f"\n{'='*72}")
    print(f"  {ctx['key']}  [{ctx['status']}]  Severity {ctx['severity']}")
    print(f"{'='*72}")
    print(f"  标题:     {ctx['summary']}")
    print(f"  负责人:   {ctx['assignee']}   报告人: {ctx['reporter']}")
    print(f"  项目线:   {ctx['project']}")
    print(f"  故障时间: {ctx['fault_time'] or '未填写'}")
    print(f"  创建:     {ctx['created']}  更新: {ctx['updated']}")
    print(f"  原因分析: {ctx['cause_status']}  对策: {ctx['fix_status']}  验证: {ctx['verify_status']}")

    chain = "✅ 是" if ctx["has_analysis_chain"] else "❌ 否"
    print(f"\n  评论已有完整分析链: {chain}")
    if ctx["has_cause"]:
        print(f"    - 含原因分析")
    if ctx["has_gerrit"]:
        print(f"    - 含 Gerrit 链接")
    if ctx["has_fix"]:
        print(f"    - 含修复信息")

    print(f"\n  --- 描述 (前 2000 字符) ---")
    print(f"  {ctx['description'][:2000]}")

    print(f"\n  --- 评论 ({ctx['comments_count']} 条) ---")
    for c in ctx["comments"]:
        kw_tag = " [含关键字]" if c["has_keywords"] else ""
        print(f"\n  {c['author']} @ {c['created']}{kw_tag}")
        print(f"  {c['body'][:2000]}")

    print(f"\n  --- 附件清单 (共 {ctx['total_attachments']} 个, {ctx['total_size_mb']} MB) ---")
    inv = ctx["attachments_inventory"]
    for cat in ["android_log", "small_log", "other", "large_archive", "image", "video"]:
        if cat in inv:
            info = inv[cat]
            print(f"  [{cat}] {info['count']} 个, {info['total_mb']} MB")
            for f in info["files"]:
                print(f"    {f['filename']:55s} {f['size_mb']:8.2f} MB")
    print(f"{'='*72}")


def main():
    if sys.platform == "win32":
        for s in (sys.stdout, sys.stderr):
            if hasattr(s, "reconfigure"):
                try:
                    s.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

    ap = argparse.ArgumentParser(description="Fetch Jira issue context for AI pre-analysis")
    ap.add_argument("issue_key", help="Jira issue key, e.g. BAIC-12345")
    ap.add_argument("-j", "--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    ctx = fetch_and_summarize(args.issue_key)
    if args.json:
        print(json.dumps(ctx, ensure_ascii=False, indent=2))
    else:
        print_text_report(ctx)


if __name__ == "__main__":
    main()
