#!/usr/bin/env python3
"""
Smart Jira Android Log Analyzer

Only downloads the android log matching the bug's occurrence time,
instead of all (potentially dozens of) attachments.

Usage:
    python smart_jira_log.py BAIC-12345
    python smart_jira_log.py BAIC-12345 --time "2026-03-28 11:24:28"
    python smart_jira_log.py BAIC-12345 --earlier
    python smart_jira_log.py BAIC-12345 --list
    python smart_jira_log.py BAIC-12345 --index 2
    python smart_jira_log.py BAIC-12345 --window 30 --all-errors
    python smart_jira_log.py BAIC-12345 --download-only -o ./logs
    python smart_jira_log.py BAIC-12345 --json
"""

import os
import sys
import re
import time
import json
import zipfile
import gzip
import tempfile
import base64
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import requests
from urllib.parse import quote

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ═══════════════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════════════

JIRA_URL  = os.environ.get("JIRA_URL", "")
JIRA_USER = os.environ.get("JIRA_USER", "")
JIRA_PASS = os.environ.get("JIRA_PASS", "")

# android_20260328-112428.zip  /  android_20260328_112428.zip  /  android_20260328.zip
ANDROID_LOG_RE = re.compile(
    r"^android[_\-]?(\d{8})[_\-]?(\d{6})?.*\.(?:zip|gz|tar|7z|rar)(?:\.\d+)?$",
    re.IGNORECASE,
)

# AutoTestManagerMain 等工具导出的分段包：Logs_2026_04_07_21_44_50.zip.001
LOGS_ARCHIVE_RE = re.compile(
    r"^Logs_(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})\.zip$",
    re.IGNORECASE,
)

# Segment suffix patterns: .001 .002 / .z01 .z02 / .part1 etc.
SEGMENT_SUFFIX_RE = re.compile(
    r"^(.*\.(?:zip|7z|rar))(?:\.(\d+)|\.z(\d+)|\.part(\d+))$", re.IGNORECASE
)

ERROR_KEYWORDS = [
    re.compile(r"(?i)\bFatal signal\b"),
    re.compile(r"(?i)\b(?:java|kotlin)\.\w+Exception\b"),
    re.compile(r"(?i)\bANR in\b"),
    re.compile(r"(?i)\bSIGSEGV\b"),
    re.compile(r"(?i)\btombstone\b"),
    re.compile(r"(?i)\bOutOfMemoryError\b"),
    re.compile(r"(?i)\b(?:FATAL|E/AndroidRuntime)\b"),
    re.compile(r"(?i)\bProcess .+ has died\b"),
    re.compile(r"(?i)\bForce finishing activity\b"),
    re.compile(r"(?i)\bDIED\b.*pid"),
    re.compile(r"(?i)\bCRASH\b"),
    re.compile(r"(?i)\bBuild fingerprint:"),
    re.compile(r"(?i)\bCaused by:\s"),
    re.compile(r"(?i)\bNullPointerException\b"),
    re.compile(r"(?i)\bIllegalStateException\b"),
    re.compile(r"(?i)\bWindowManager:.*not attached"),
    re.compile(r"(?i)\bActivityManager: Force removing"),
]

# Ordered by specificity; first match wins
DESC_TIME_PATTERNS = [
    # "发生时间：2026-03-28 11:24:28" / "复现时间: 2026/03/28 11:24"
    (re.compile(
        r"(?:发生|复现|出现|bug|问题|异常|故障|操作)[\s]*(?:时间|time)\s*[:：]\s*"
        r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}[\sT]\d{1,2}:\d{2}(?::\d{2})?)",
        re.IGNORECASE), None),
    # "2026年3月28日 11时24分28秒" / "2026年03月28日 11:24:28"
    (re.compile(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[时:](\d{1,2})[分:]?(\d{1,2})?"),
     "chinese"),
    # fallback generic "2026-03-28 11:24:28" anywhere
    (re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}[\sT]\d{1,2}:\d{2}(?::\d{2})?)"), None),
    # "03-28 11:24:28" (no year)
    (re.compile(r"(?<!\d)(\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)"), "noyear"),
]


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _auth_header() -> dict:
    if not all([JIRA_URL, JIRA_USER, JIRA_PASS]):
        sys.exit("ERROR: 需设置环境变量 JIRA_URL / JIRA_USER / JIRA_PASS")
    token = base64.b64encode(f"{JIRA_USER}:{JIRA_PASS}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def fetch_issue(key: str) -> dict:
    url = f"{JIRA_URL}/rest/api/2/issue/{quote(key)}"
    r = requests.get(url, headers=_auth_header(), timeout=30, verify=False)
    r.raise_for_status()
    return r.json()


def _parse_jira_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def extract_occurrence_time(description: str, created: str) -> Optional[datetime]:
    """Try hard to find the bug occurrence time in description text."""
    text = description or ""
    for pat, kind in DESC_TIME_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if kind == "chinese":
                y, mo, d, h, mi, s = m.groups()
                return datetime(int(y), int(mo), int(d),
                                int(h), int(mi), int(s or 0))
            elif kind == "noyear":
                return datetime.strptime(
                    f"{datetime.now().year}-{m.group(1)}",
                    "%Y-%m-%d %H:%M:%S" if m.group(1).count(":") == 2
                    else "%Y-%m-%d %H:%M")
            else:
                raw = m.group(1).replace("/", "-").replace("T", " ")
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        return datetime.strptime(raw, fmt)
                    except ValueError:
                        continue
        except Exception:
            continue
    return _parse_jira_dt(created)


def parse_filename_time(filename: str) -> Optional[datetime]:
    base = filename
    seg = SEGMENT_SUFFIX_RE.match(filename)
    if seg:
        base = seg.group(1)

    m = ANDROID_LOG_RE.match(base)
    if m:
        date_part = m.group(1)
        time_part = m.group(2) or "000000"
        try:
            return datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S")
        except ValueError:
            return None

    m2 = LOGS_ARCHIVE_RE.match(base)
    if m2:
        y, mo, d, h, mi, s = m2.groups()
        try:
            return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
        except ValueError:
            return None
    return None


def _segment_base(filename: str) -> Optional[str]:
    """Return the base archive name if this is a segment, else None."""
    m = SEGMENT_SUFFIX_RE.match(filename)
    return m.group(1) if m else None


# ═══════════════════════════════════════════════════════════════════════════
#  Attachment filtering & grouping
# ═══════════════════════════════════════════════════════════════════════════

def group_android_attachments(attachments: list) -> List[dict]:
    """
    Return a list of 'logical' android log entries, each containing:
      - filename:       primary filename (the .zip)
      - _parsed_time:   datetime from the filename
      - _files:         list of attachment dicts (single or multi-segment)
      - _total_size:    sum of sizes
    Segments like android_xxx.zip.001 / .002 are merged into one group.
    """
    groups: Dict[str, dict] = {}

    for att in attachments:
        fn = att.get("filename", "")
        fn_lower = fn.lower()

        # Direct match
        ts = parse_filename_time(fn)
        if ts:
            key = fn
            seg_base = _segment_base(fn)
            if seg_base:
                key = seg_base
            grp = groups.setdefault(key, {
                "filename": key,
                "_parsed_time": ts,
                "_files": [],
                "_total_size": 0,
            })
            grp["_files"].append(att)
            grp["_total_size"] += att.get("size", 0)
            continue

        # Might be a segment of an android zip
        seg_base = _segment_base(fn)
        if seg_base:
            ts2 = parse_filename_time(seg_base)
            if ts2:
                grp = groups.setdefault(seg_base, {
                    "filename": seg_base,
                    "_parsed_time": ts2,
                    "_files": [],
                    "_total_size": 0,
                })
                grp["_files"].append(att)
                grp["_total_size"] += att.get("size", 0)

    result = sorted(groups.values(), key=lambda g: g["_parsed_time"])
    return result


def find_best_match(logs: list, target: datetime) -> Tuple[int, dict]:
    """Pick the log whose capture time is closest to *and >= * target.
    Falls back to the latest log if all are before target.
    """
    if not logs:
        return -1, {}
    for i, lg in enumerate(logs):
        if lg["_parsed_time"] >= target:
            return i, lg
    return len(logs) - 1, logs[-1]


# ═══════════════════════════════════════════════════════════════════════════
#  Download & Extract
# ═══════════════════════════════════════════════════════════════════════════

def download_one(att: dict, dest_dir: Path) -> Path:
    url = att["content"]
    fn  = att["filename"]
    dest = dest_dir / fn
    expected = int(att.get("size") or 0)

    max_rounds = 12
    for round_i in range(max_rounds):
        have = dest.stat().st_size if dest.exists() else 0
        if expected and have >= expected:
            return dest
        if have and (not expected or have > expected):
            dest.unlink(missing_ok=True)
            have = 0

        hdrs = dict(_auth_header())
        if have > 0:
            hdrs["Range"] = f"bytes={have}-"

        try:
            r = requests.get(
                url, headers=hdrs, stream=True,
                timeout=(60, 600), verify=False,
            )
            if r.status_code == 416:
                dest.unlink(missing_ok=True)
                time.sleep(1)
                continue
            if have > 0 and r.status_code == 200:
                dest.unlink(missing_ok=True)
                have = 0
            r.raise_for_status()
            append = r.status_code == 206
            if not append and have > 0:
                dest.unlink(missing_ok=True)
                have = 0

            cl = int(r.headers.get("content-length") or 0)
            total = expected or (have + cl if cl else 0)
            done = have
            mode = "ab" if append else "wb"
            with open(dest, mode) as f:
                for chunk in r.iter_content(chunk_size=128 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r  ⬇ {fn}: {min(100, done * 100 // total)}% "
                              f"({done/1048576:.1f}/{total/1048576:.1f} MB)",
                              end="", flush=True)
            print()
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                OSError) as e:
            print(f"\n  ⚠ 下载中断 ({type(e).__name__})，已 {have/1048576:.1f} MB，"
                  f"{'续传' if have else '重试'}…")
            time.sleep(min(2 + round_i * 2, 20))
            continue

        got = dest.stat().st_size if dest.exists() else 0
        if expected and got < expected:
            time.sleep(1)
            continue
        return dest

    raise RuntimeError(f"下载失败（已重试 {max_rounds} 次）: {fn}")


# ── P0 fallback: standalone small log files ───────────────────────────────

_P0_LOG_KEYWORDS = (
    "logcat", "main", "system", "crash", "events", "kernel",
    "radio", "tombstone", "anr", "dropbox",
)
_P0_FILENAME_TIME_RE = re.compile(
    r"(\d{8})[_\-]?(\d{6})|(\d{4}-\d{2}-\d{2})[_\-T](\d{2}-\d{2}-\d{2})"
)
_P0_MAX_BYTES = 50 * 1024 * 1024
_P0_EXTS = (".log.gz", ".log", ".txt")


def _parse_p0_time(name: str) -> Optional[datetime]:
    m = _P0_FILENAME_TIME_RE.search(name)
    if not m:
        return None
    if m.group(1):
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            return None
    try:
        return datetime.strptime(
            m.group(3) + " " + m.group(4).replace("-", ":"),
            "%Y-%m-%d %H:%M:%S",
        )
    except ValueError:
        return None


def _collect_standalone_small_logs(
    atts: list, fault: Optional[datetime]
) -> List[dict]:
    """
    Pick attachments that look like standalone small text logs:
      - extension in (.log.gz, .log, .txt)
      - size < 50 MB
      - filename mentions a known log keyword
    Sort by closeness to fault time when available, else newest first.
    Cap at 6 candidates to avoid pulling tons of irrelevant text files.
    """
    cands: List[Tuple[Optional[datetime], int, dict]] = []
    for a in atts:
        fn = (a.get("filename") or "").lower()
        if not fn.endswith(_P0_EXTS):
            continue
        size = int(a.get("size") or 0)
        if size <= 0 or size >= _P0_MAX_BYTES:
            continue
        if not any(k in fn for k in _P0_LOG_KEYWORDS):
            continue
        t = _parse_p0_time(a["filename"])
        cands.append((t, size, a))

    if not cands:
        return []

    if fault:
        def _key(c):
            t = c[0]
            if t is None:
                return (1, 0)
            return (0, abs((t - fault).total_seconds()))
        cands.sort(key=_key)
    else:
        cands.sort(key=lambda c: c[0] or datetime.min, reverse=True)

    return [c[2] for c in cands[:6]]


def _download_standalone_logs(
    p0_logs: List[dict], work: Path, hdrs: dict
) -> List[Path]:
    """Download P0 small logs and decompress .gz to .log."""
    out: List[Path] = []
    p0_dir = work / "p0_standalone_logs"
    p0_dir.mkdir(parents=True, exist_ok=True)
    for a in p0_logs:
        try:
            local = download_one(a, p0_dir)
        except Exception as e:
            print(f"  ⚠ 下载失败 {a.get('filename')}: {e}")
            continue
        if local.name.lower().endswith(".log.gz"):
            log_path = local.with_name(local.name[:-3])
            try:
                log_path.write_bytes(gzip.open(local, "rb").read())
                print(f"  ✓ {local.name} → {log_path.name}")
                out.append(log_path)
                continue
            except OSError as e:
                print(f"  ⚠ gzip 解压失败 {local.name}: {e}")
        out.append(local)
    return out


def download_group(grp: dict, dest_dir: Path) -> Path:
    """Download all files in the group and reassemble if segmented."""
    files = sorted(grp["_files"], key=lambda a: a["filename"])
    paths = []
    for att in files:
        paths.append(download_one(att, dest_dir))

    if len(paths) == 1:
        return paths[0]

    # Reassemble segments: binary concatenate in filename order
    out = dest_dir / grp["filename"]
    print(f"  🔗 拼接 {len(paths)} 个分段 → {out.name}")
    with open(out, "wb") as fout:
        for p in paths:
            with open(p, "rb") as fin:
                while True:
                    chunk = fin.read(1024 * 1024)
                    if not chunk:
                        break
                    fout.write(chunk)
    return out


def extract_zip(zip_path: Path, dest_dir: Path) -> List[Path]:
    extracted: List[Path] = []
    TEXT_EXTS = {".txt", ".log", ".xml", ".prop", ".csv", ".json", ".cfg", ".ini"}
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                suffix = Path(info.filename).suffix.lower()
                if suffix in TEXT_EXTS:
                    zf.extract(info, dest_dir)
                    extracted.append(dest_dir / info.filename)
                elif suffix == ".gz":
                    zf.extract(info, dest_dir)
                    gz = dest_dir / info.filename
                    try:
                        txt = gz.with_suffix("")
                        txt.write_bytes(gzip.open(gz, "rb").read())
                        extracted.append(txt)
                    except Exception:
                        pass
                elif suffix == ".zip":
                    zf.extract(info, dest_dir)
                    nested_dir = dest_dir / (Path(info.filename).stem + "_nested")
                    nested_dir.mkdir(parents=True, exist_ok=True)
                    extracted.extend(extract_zip(dest_dir / info.filename, nested_dir))
    except zipfile.BadZipFile:
        print(f"  ⚠ 无法解压: {zip_path.name} (可能需要更多分段或文件损坏)")
    return extracted


# ═══════════════════════════════════════════════════════════════════════════
#  Log analysis
# ═══════════════════════════════════════════════════════════════════════════

_LOG_TS_RE = re.compile(
    r"^(?:(\d{4})-)?(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})")


def _parse_log_ts(line: str) -> Optional[datetime]:
    m = _LOG_TS_RE.match(line)
    if not m:
        return None
    y = int(m.group(1)) if m.group(1) else datetime.now().year
    try:
        return datetime(y, int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)), int(m.group(6)))
    except ValueError:
        return None


def analyze_file(fp: Path, target: Optional[datetime],
                 window_min: int = 10) -> List[dict]:
    findings: List[dict] = []
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            lines = fp.read_text(encoding=enc).splitlines()
            break
        except (UnicodeDecodeError, UnicodeError):
            lines = []
    if not lines:
        return findings

    t_lo = t_hi = None
    if target:
        t_lo = target - timedelta(minutes=window_min)
        t_hi = target + timedelta(minutes=window_min)

    in_window = target is None
    for i, line in enumerate(lines):
        if target and not in_window:
            ts = _parse_log_ts(line)
            if ts and t_lo and ts >= t_lo:
                in_window = True
        if target and in_window:
            ts = _parse_log_ts(line)
            if ts and t_hi and ts > t_hi:
                break
        if not in_window:
            continue

        for pat in ERROR_KEYWORDS:
            if pat.search(line):
                ctx_start = max(0, i - 2)
                ctx_end   = min(len(lines), i + 13)
                findings.append({
                    "file": fp.name,
                    "line": i + 1,
                    "hit":  line.strip()[:300],
                    "ctx":  "\n".join(lines[ctx_start:ctx_end]),
                })
                break
    return findings


def analyze_all(extracted: List[Path], target: Optional[datetime],
                window_min: int = 10) -> List[dict]:
    PRIO = ["logcat", "main", "system", "events", "crash", "anr", "tombstone"]
    rank = lambda p: (
        0 if any(k in p.name.lower() for k in PRIO) else 1,
        p.name.lower()
    )
    result: List[dict] = []
    for fp in sorted(extracted, key=rank):
        sz = fp.stat().st_size
        if sz > 500 * 1024 * 1024:
            print(f"  ⚠ 跳过超大文件: {fp.name} ({sz/1048576:.0f} MB)")
            continue
        result.extend(analyze_file(fp, target, window_min))
    return result


def dedup(findings: List[dict], cap: int = 30) -> List[dict]:
    seen: set = set()
    out: List[dict] = []
    per_file: Dict[str, int] = {}
    for f in findings:
        k = (f["file"], f["hit"][:120])
        if k in seen:
            continue
        seen.add(k)
        c = per_file.get(f["file"], 0)
        if c >= 20:
            continue
        per_file[f["file"]] = c + 1
        out.append(f)
        if len(out) >= cap:
            break
    return out


# ═══════════════════════════════════════════════════════════════════════════
#  Report
# ═══════════════════════════════════════════════════════════════════════════

def print_report(issue: dict, target: Optional[datetime],
                 matched: dict, findings: List[dict],
                 all_logs: list):
    fields = issue.get("fields", {})
    key     = issue.get("key", "?")
    summary = fields.get("summary", "?")
    status  = fields.get("status", {}).get("name", "?")

    print("\n" + "=" * 72)
    print(f"  BUG 分析: {key}")
    print("=" * 72)
    print(f"  标题:     {summary}")
    print(f"  状态:     {status}")
    ts_str = target.strftime("%Y-%m-%d %H:%M:%S") if target else "未识别"
    print(f"  发生时间: {ts_str}")
    print(f"  匹配日志: {matched.get('filename', '无')}")
    lt = matched.get("_parsed_time")
    if lt:
        print(f"  采集时间: {lt.strftime('%Y-%m-%d %H:%M:%S')}")

    print(f"\n  全部 Android 日志 ({len(all_logs)} 个):")
    for i, lg in enumerate(all_logs):
        marker = " ◀ 已分析" if lg["filename"] == matched.get("filename") else ""
        t  = lg["_parsed_time"].strftime("%Y-%m-%d %H:%M:%S")
        mb = lg["_total_size"] / 1048576
        n  = len(lg["_files"])
        seg = f" ({n} 段)" if n > 1 else ""
        print(f"    [{i}] {lg['filename']}  ({t}, {mb:.1f} MB{seg}){marker}")

    print("\n" + "-" * 72)
    findings = dedup(findings)
    if not findings:
        print("  ✅ 在目标时间窗口内未发现明显异常/崩溃")
        print("     建议: --window 60 扩大窗口 / --earlier 追溯更早日志 / --all-errors 全量扫描")
    else:
        print(f"  发现 {len(findings)} 条关键日志:\n")
        for i, f in enumerate(findings):
            print(f"  ── [{i+1}] {f['file']}:{f['line']} ──")
            print(f"  {f['hit']}")
            if f.get("ctx"):
                for cl in f["ctx"].split("\n")[:10]:
                    print(f"    {cl[:160]}")
            print()
    print("-" * 72)


def print_json_report(issue: dict, target: Optional[datetime],
                      matched: dict, findings: List[dict],
                      all_logs: list, work_dir: Path):
    """Output structured JSON for AI consumption."""
    fields = issue.get("fields", {})
    findings = dedup(findings)
    report = {
        "key": issue.get("key", "?"),
        "summary": fields.get("summary", "?"),
        "status": fields.get("status", {}).get("name", "?"),
        "occurrence_time": target.strftime("%Y-%m-%d %H:%M:%S") if target else None,
        "matched_log": matched.get("filename"),
        "matched_log_time": matched.get("_parsed_time", "").strftime("%Y-%m-%d %H:%M:%S")
            if matched.get("_parsed_time") else None,
        "total_android_logs": len(all_logs),
        "work_dir": str(work_dir),
        "findings_count": len(findings),
        "findings": [
            {
                "file": f["file"],
                "line": f["line"],
                "hit": f["hit"],
                "context": f.get("ctx", "")[:500],
            }
            for f in findings[:30]
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════

def _fix_windows_console_utf8() -> None:
    """Avoid UnicodeEncodeError when printing emoji/UTF-8 on GBK consoles."""
    if sys.platform != "win32" or not hasattr(sys.stdout, "buffer"):
        return
    enc = (getattr(sys.stdout, "encoding", None) or "").upper()
    if enc in ("UTF-8", "UTF8"):
        return
    import io

    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )


def main():
    _fix_windows_console_utf8()
    ap = argparse.ArgumentParser(
        description="Smart Jira Android Log Analyzer — "
                    "只下载匹配发生时间的 android 日志")
    ap.add_argument("issue_key", help="Jira issue key, e.g. BAIC-12345")
    ap.add_argument("-t", "--time",
                    help="手动指定发生时间 (YYYY-MM-DD HH:MM:SS)")
    ap.add_argument("-l", "--list", action="store_true",
                    help="仅列出 android 日志附件，不下载")
    ap.add_argument("-i", "--index", type=int,
                    help="直接指定附件索引 (配合 --list 查看)")
    ap.add_argument("-e", "--earlier", action="store_true",
                    help="同时分析前一份日志 (追溯)")
    ap.add_argument("-E", "--auto-earlier", action="store_true",
                    help="若当前日志无发现，自动追溯更早日志")
    ap.add_argument("-w", "--window", type=int, default=10,
                    help="时间窗口（分钟），默认 10")
    ap.add_argument("-a", "--all-errors", action="store_true",
                    help="忽略时间窗口，全量扫描所有错误")
    ap.add_argument("-o", "--output-dir",
                    help="指定工作目录 (默认 temp)")
    ap.add_argument("-D", "--download-only", action="store_true",
                    help="仅下载并解压匹配的 android 日志，不进行分析")
    ap.add_argument("-j", "--json", action="store_true",
                    help="输出 JSON 格式的分析结果 (供 AI 消费)")
    args = ap.parse_args()

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ── 1. Fetch issue ──
    print(f"\n{'='*72}")
    print(f"  Jira Issue: {args.issue_key}")
    print(f"{'='*72}")
    issue = fetch_issue(args.issue_key)
    fields = issue.get("fields", {})
    desc    = fields.get("description", "") or ""
    created = fields.get("created", "")
    atts    = fields.get("attachment", [])

    print(f"  标题:   {fields.get('summary', '?')}")
    print(f"  附件数: {len(atts)}")

    # ── 2. Group android logs ──
    android_logs = group_android_attachments(atts)
    print(f"  Android 日志: {len(android_logs)} 组\n")

    # ── 3. Determine occurrence time (moved before 7z fallback) ──
    if args.time:
        target = datetime.strptime(args.time, "%Y-%m-%d %H:%M:%S")
    else:
        target = extract_occurrence_time(desc, created)
    ts_display = target.strftime("%Y-%m-%d %H:%M:%S") if target else "未识别"
    print(f"  发生时间: {ts_display}")

    work = None  # may be set by 7z fallback

    if not android_logs:
        from range_extract_7z_jira import (
            detect_7z_segment_groups,
            extract_android_from_7z,
            parse_android_zip_time,
        )

        sz_groups = detect_7z_segment_groups(atts)
        if not sz_groups:
            print("⚠ 未找到 android_*.zip 附件，也未找到 7z 分段包。全部附件如下:")
            for a in atts:
                print(f"  - {a['filename']}  ({a.get('size',0)/1048576:.1f} MB)")
            return

        hdrs = _auth_header()
        result: Optional[dict] = None

        for grp in sz_groups:
            total_mb = grp["total_size"] / 1048576
            print(f"\n  📦 发现 7z 分段包: {grp['prefix']}"
                  f"  ({grp['count']} 段, {total_mb:.1f} MB)")
            print(f"  使用 HTTP Range 按需读取 (不全量下载)...")

            if args.output_dir:
                work = Path(args.output_dir)
            else:
                work = Path(tempfile.mkdtemp(prefix=f"jira_{args.issue_key}_"))
            work.mkdir(parents=True, exist_ok=True)

            result = extract_android_from_7z(
                segments=grp["segments"],
                headers=hdrs,
                fault_time=target,
                output_dir=work,
            )
            if result:
                break

        if result and result.get("type") == "android_zip":
            zp: Path = result["path"]
            print(f"\n  ✅ 从 7z 提取 android zip: {zp.name}")
            file_time = parse_android_zip_time(zp.name)
            android_logs = [{
                "filename": zp.name,
                "_parsed_time": file_time or target or datetime.now(),
                "_files": [{"filename": zp.name, "size": zp.stat().st_size}],
                "_total_size": zp.stat().st_size,
                "_local_path": zp,
            }]
        elif result and result.get("type") == "logcat_slices":
            paths: List[Path] = result["paths"]
            total = sum(p.stat().st_size for p in paths)
            print(f"\n  ✅ 从 7z 顶层提取 {len(paths)} 个 logcat 分片")
            android_logs = [{
                "filename": f"7z_logcat_slices ({len(paths)} files)",
                "_parsed_time": target or datetime.now(),
                "_files": [{"filename": p.name, "size": p.stat().st_size}
                           for p in paths],
                "_total_size": total,
                "_local_files": paths,
            }]
        else:
            # ── P0 独立小日志回退 ──
            p0_logs = _collect_standalone_small_logs(atts, target)
            if not p0_logs:
                print("⚠ 7z 包内未找到匹配日志，附件中也无独立小日志。全部附件如下:")
                for a in atts:
                    print(f"  - {a['filename']}  ({a.get('size',0)/1048576:.1f} MB)")
                return
            if work is None:
                if args.output_dir:
                    work = Path(args.output_dir)
                else:
                    work = Path(tempfile.mkdtemp(prefix=f"jira_{args.issue_key}_"))
                work.mkdir(parents=True, exist_ok=True)
            local_paths = _download_standalone_logs(p0_logs, work, hdrs)
            if not local_paths:
                print("⚠ 独立小日志下载失败")
                return
            total = sum(p.stat().st_size for p in local_paths)
            print(f"\n  ✅ P0 独立小日志: 下载 {len(local_paths)} 个, "
                  f"{total/1048576:.1f} MB")
            android_logs = [{
                "filename": f"standalone_logs ({len(local_paths)} files)",
                "_parsed_time": target or datetime.now(),
                "_files": [{"filename": p.name, "size": p.stat().st_size}
                           for p in local_paths],
                "_total_size": total,
                "_local_files": local_paths,
            }]

    # ── list mode ──
    if args.list:
        print("Android 日志附件:")
        for i, lg in enumerate(android_logs):
            t  = lg["_parsed_time"].strftime("%Y-%m-%d %H:%M:%S")
            mb = lg["_total_size"] / 1048576
            n  = len(lg["_files"])
            seg = f" ({n} 段)" if n > 1 else ""
            print(f"  [{i}] {lg['filename']}  (采集: {t}, {mb:.1f} MB{seg})")
        return

    # ── 4. Match ──
    if args.index is not None:
        if not (0 <= args.index < len(android_logs)):
            sys.exit(f"索引超范围 (0 ~ {len(android_logs)-1})")
        idx, matched = args.index, android_logs[args.index]
    elif target:
        idx, matched = find_best_match(android_logs, target)
    else:
        idx = len(android_logs) - 1
        matched = android_logs[idx]

    print(f"  匹配日志: [{idx}] {matched['filename']}")
    print(f"  采集时间: {matched['_parsed_time'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  文件数:   {len(matched['_files'])} 个, "
          f"总计 {matched['_total_size']/1048576:.1f} MB")

    # ── 5. Prepare work dir ──
    if work is None:
        if args.output_dir:
            work = Path(args.output_dir)
        else:
            work = Path(tempfile.mkdtemp(prefix=f"jira_{args.issue_key}_"))
    work.mkdir(parents=True, exist_ok=True)
    print(f"  工作目录: {work}\n")

    # ── 6. Download, extract, analyze (with auto-traceback) ──
    queue = [(idx, matched)]
    if args.earlier and idx > 0:
        queue.insert(0, (idx - 1, android_logs[idx - 1]))

    all_findings: List[dict] = []
    analyzed_names: List[str] = []

    while queue:
        cur_idx, cur_log = queue.pop(0)
        print(f"{'─'*72}")
        print(f"  📥 处理: {cur_log['filename']}")

        if cur_log.get("_local_files"):
            extracted = list(cur_log["_local_files"])
            ext_dir = extracted[0].parent if extracted else work
            print(f"  (本地文件，跳过下载/解压: {len(extracted)} 个)")
        else:
            if cur_log.get("_local_path"):
                zip_path = cur_log["_local_path"]
                print(f"  (已从 7z 提取，跳过下载)")
            else:
                zip_path = download_group(cur_log, work)

            ext_dir = work / (zip_path.stem + "_extracted")
            ext_dir.mkdir(parents=True, exist_ok=True)
            print(f"  📦 解压中...")
            extracted = extract_zip(zip_path, ext_dir)

        print(f"  提取 {len(extracted)} 个文本文件")
        for ef in extracted[:8]:
            print(f"    - {ef.name}  ({ef.stat().st_size/1024:.0f} KB)")
        if len(extracted) > 8:
            print(f"    ... 另有 {len(extracted)-8} 个文件")

        if args.download_only:
            analyzed_names.append(cur_log["filename"])
            print(f"\n  ✅ 下载完成 (--download-only 模式，跳过分析)")
            print(f"  📂 解压目录: {ext_dir}")
            print(f"  文本文件列表:")
            for ef in sorted(extracted, key=lambda p: p.name):
                print(f"    {ef}  ({ef.stat().st_size/1024:.0f} KB)")
            continue

        scan_target = None if args.all_errors else target
        findings = analyze_all(extracted, scan_target, args.window)
        all_findings.extend(findings)
        analyzed_names.append(cur_log["filename"])

        if not findings and args.auto_earlier and cur_idx > 0:
            prev = android_logs[cur_idx - 1]
            if prev["filename"] not in analyzed_names:
                print(f"\n  💡 未发现异常，自动追溯前一份: {prev['filename']}")
                queue.append((cur_idx - 1, prev))

    # ── 7. Report ──
    if args.download_only:
        print(f"\n  📂 文件保存在: {work}")
        return

    if args.json:
        print_json_report(issue, target, matched, all_findings, android_logs, work)
    else:
        print_report(issue, target, matched, all_findings, android_logs)
    print(f"\n  📂 文件保存在: {work}\n")


def _fix_windows_console_encoding() -> None:
    """Avoid UnicodeEncodeError on Windows (cp936/gbk) when printing emoji."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


if __name__ == "__main__":
    _fix_windows_console_encoding()
    main()
