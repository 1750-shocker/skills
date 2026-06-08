#!/usr/bin/env python3
"""
从 Jira 分段 .7z.001~NNN 附件中按 HTTP Range 按需读取虚拟连续流，
用 py7zr 列出并只解压匹配的 android_*.zip（禁止先全量下载各段）。

用法:
  python range_extract_7z_jira.py BAIC-59686 --prefix "安卓日志.7z."
  python range_extract_7z_jira.py BAIC-59686 -t "2026-04-09 19:23:00" -o ./out
  python range_extract_7z_jira.py BAIC-59686 -t "..." -o ./out --slice-logcat --decompress-logcat
  python range_extract_7z_jira.py BAIC-59686 --list-only
"""
from __future__ import annotations

import argparse
import base64
import io
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import py7zr
except ImportError:
    print("ERROR: 需要 pip install py7zr", file=sys.stderr)
    sys.exit(1)

# 同目录：按故障时间从 android zip 内只解 logcat 分片
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from extract_logcat_from_android_zip import list_logcat_members, pick_members

JIRA_URL = os.environ.get("JIRA_URL", "")
JIRA_USER = os.environ.get("JIRA_USER", "")
JIRA_PASS = os.environ.get("JIRA_PASS", "")

ANDROID_LOG_RE = re.compile(
    r"^(.*/)?android[_\-]?(\d{8})[_\-]?(\d{6})?.*\.(?:zip|gz|tar|7z|rar)(?:\.\d+)?$",
    re.IGNORECASE,
)


def _auth_header() -> dict:
    if not all([JIRA_URL, JIRA_USER, JIRA_PASS]):
        sys.exit("ERROR: 需设置环境变量 JIRA_URL / JIRA_USER / JIRA_PASS")
    token = base64.b64encode(f"{JIRA_USER}:{JIRA_PASS}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def fetch_issue(key: str) -> dict:
    from urllib.parse import quote

    url = f"{JIRA_URL}/rest/api/2/issue/{quote(key)}"
    r = requests.get(url, headers=_auth_header(), timeout=30, verify=False)
    r.raise_for_status()
    return r.json()


def parse_android_zip_time(name: str) -> Optional[datetime]:
    base = Path(name).name
    m = ANDROID_LOG_RE.match(base)
    if not m:
        return None
    date_part = m.group(2)
    time_part = m.group(3) or "000000"
    try:
        return datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S")
    except ValueError:
        return None


def list_logcat_entries_from_7z_listing(
    names: List[str],
) -> List[Tuple[datetime, str, int]]:
    """7z 顶层若直接含 logcat/*_logcat_*-*.log.gz（未再打 zip），用于只解小文件。"""
    rows: List[Tuple[datetime, str, int]] = []
    pat = re.compile(
        r"(?i)logcat/.*_logcat_(\d{8})-(\d{6})\.log\.gz$"
    )
    for n in names:
        m = pat.search(n.replace("\\", "/"))
        if not m:
            continue
        try:
            t = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            continue
        rows.append((t, n, 0))
    rows.sort(key=lambda x: x[0])
    return rows


def pick_android_zip(
    names: List[str], fault: Optional[datetime]
) -> Optional[str]:
    """同 smart_jira_log：优先采集时间 >= 故障时间；否则取最后一份。"""
    candidates: List[Tuple[datetime, str]] = []
    for n in names:
        ts = parse_android_zip_time(n)
        if ts:
            candidates.append((ts, n))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    if fault:
        for ts, n in candidates:
            if ts >= fault:
                return n
        return candidates[-1][1]
    return candidates[-1][1]


# ── 自动检测 7z 分段组 ────────────────────────────────────────────────────

SPLIT_7Z_RE = re.compile(r'^(.+\.7z)\.\d{3,}$', re.IGNORECASE)


def detect_7z_segment_groups(attachments: list) -> List[dict]:
    """
    Auto-detect split 7z segment groups from Jira attachment list.
    Returns groups sorted by total_size descending.
    """
    groups: dict[str, dict] = {}
    for att in attachments:
        fn = att.get("filename", "")
        m = SPLIT_7Z_RE.match(fn)
        if not m:
            continue
        base = m.group(1)
        prefix = base + "."

        url = att.get("content", "")
        size = int(att.get("size") or 0)
        if size <= 0:
            continue

        grp = groups.setdefault(prefix, {
            "prefix": prefix,
            "segments": [],
            "total_size": 0,
            "count": 0,
            "filenames": [],
        })
        grp["segments"].append((url, size))
        grp["filenames"].append(fn)
        grp["total_size"] += size
        grp["count"] += 1

    for grp in groups.values():
        paired = sorted(zip(grp["filenames"], grp["segments"]))
        grp["filenames"] = [f for f, _ in paired]
        grp["segments"] = [s for _, s in paired]

    return sorted(groups.values(), key=lambda g: g["total_size"], reverse=True)


# ── LazySegmentFile: 多段 URL → 虚拟连续文件，仅 Range 读取 ───────────────


class LazySegmentFile(io.RawIOBase):
    """
    将多个 HTTP 资源按顺序拼成 seekable 虚拟文件；read/seek 触发 Range GET。
    使用 512KB 块缓存减少重复请求。
    """

    def __init__(
        self,
        segments: List[Tuple[str, int]],
        headers: dict,
        block_size: int = 512 * 1024,
    ):
        super().__init__()
        self._segments = segments  # (url, size)
        self._headers = dict(headers)
        self._block_size = block_size
        self._total = sum(s[1] for s in segments)
        self._pos = 0
        self._cache: dict[int, bytes] = {}

    def _global_to_seg(self, off: int) -> Tuple[int, int]:
        o = 0
        for i, (_, sz) in enumerate(self._segments):
            if off < o + sz:
                return i, off - o
            o += sz
        raise OSError("seek out of range")

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._total + offset
        else:
            raise OSError("invalid whence")
        self._pos = max(0, min(self._pos, self._total))
        return self._pos

    def _fetch_range(self, url: str, start: int, end: int) -> bytes:
        """含端 [start, end]。"""
        hdrs = dict(self._headers)
        hdrs["Range"] = f"bytes={start}-{end}"
        r = requests.get(url, headers=hdrs, timeout=(30, 300), verify=False)
        if r.status_code != 206:
            raise OSError(
                f"Range 请求失败: HTTP {r.status_code}（需要 206 Partial Content）"
            )
        return r.content

    def _read_global(self, start: int, length: int) -> bytes:
        if length <= 0:
            return b""
        out = bytearray()
        cur = start
        remain = length
        while remain > 0:
            si, local = self._global_to_seg(cur)
            url, seg_len = self._segments[si]
            avail = seg_len - local
            take = min(remain, avail)
            chunk = self._fetch_range(url, local, local + take - 1)
            if len(chunk) != take:
                raise OSError(f"Range 长度不符: 期望 {take}, 实际 {len(chunk)}")
            out.extend(chunk)
            cur += take
            remain -= take
        return bytes(out)

    def _get_block(self, block_id: int) -> bytes:
        if block_id in self._cache:
            return self._cache[block_id]
        bs = self._block_size
        start = block_id * bs
        if start >= self._total:
            return b""
        length = min(bs, self._total - start)
        data = self._read_global(start, length)
        self._cache[block_id] = data
        if len(self._cache) > 256:
            self._cache.pop(next(iter(self._cache)))
        return data

    def read(self, size: int = -1) -> bytes:
        if self._pos >= self._total:
            return b""
        if size is None or size < 0:
            size = self._total - self._pos
        end = min(self._pos + size, self._total)
        need = end - self._pos
        out = bytearray()
        p = self._pos
        while len(out) < need:
            bid = p // self._block_size
            blk = self._get_block(bid)
            off_in_blk = p - bid * self._block_size
            take = min(len(blk) - off_in_blk, need - len(out))
            if take <= 0:
                break
            out.extend(blk[off_in_blk : off_in_blk + take])
            p += take
        self._pos = p
        return bytes(out)

    def readinto(self, b) -> int:
        """BufferedReader 依赖 readinto；必须显式实现。"""
        data = self.read(len(b))
        n = len(data)
        b[:n] = data
        return n


def open_7z_from_segments(
    segments: List[Tuple[str, int]], headers: dict
) -> py7zr.py7zr.SevenZipFile:
    raw = LazySegmentFile(segments, headers)
    buf = io.BufferedReader(raw, buffer_size=1024 * 1024)
    return py7zr.SevenZipFile(buf, mode="r")


def extract_android_from_7z(
    segments: List[Tuple[str, int]],
    headers: dict,
    fault_time: Optional[datetime],
    output_dir: Path,
) -> Optional[dict]:
    """
    Open a split 7z via LazySegmentFile.

    Return one of:
      {"type": "android_zip", "path": Path}        — extracted android_*.zip
      {"type": "logcat_slices", "paths": [Path]}   — extracted top-level logcat/*.log.gz
      None                                         — nothing matched
    """
    import gzip

    total_mb = sum(s[1] for s in segments) / 1048576
    print(f"  虚拟卷: {total_mb:.1f} MB (不预下载)")
    print(f"  打开 7z (仅按需 Range 读取头/索引)...")

    with open_7z_from_segments(segments, headers) as z:
        names = z.getnames()
        print(f"  包内文件数: {len(names)}")
        for n in names[:20]:
            print(f"    {n}")
        if len(names) > 20:
            print(f"    ... 另有 {len(names) - 20} 个")

        inner = pick_android_zip(names, fault_time)

        if not inner:
            print(f"  ⚠ 7z 内未找到 android_*.zip")
            logcat_top = list_logcat_entries_from_7z_listing(names)
            if not logcat_top:
                return None
            if not fault_time:
                print(f"  发现 {len(logcat_top)} 个顶层 logcat 分片，但缺少故障时间无法挑选")
                return None
            chosen = pick_members(logcat_top, fault_time, with_previous=False)
            if not chosen:
                print(f"  ⚠ 顶层 logcat 分片中无匹配故障时间者")
                return None
            output_dir.mkdir(parents=True, exist_ok=True)
            lc_dir = output_dir / "logcat_by_fault"
            lc_dir.mkdir(parents=True, exist_ok=True)
            print(f"  从 7z 顶层提取 {len(chosen)} 个 logcat 分片 → {lc_dir}")
            out_paths: List[Path] = []
            for tname in chosen:
                z.extract(targets=[tname], path=lc_dir)
                gz_path = lc_dir / Path(tname).name
                if not gz_path.exists():
                    gz_path = lc_dir / tname
                if not gz_path.exists():
                    for p in lc_dir.rglob(Path(tname).name):
                        gz_path = p
                        break
                if not gz_path.exists():
                    print(f"    ⚠ 提取后未找到: {tname}")
                    continue
                print(f"    ✓ {gz_path.name} ({gz_path.stat().st_size/1048576:.2f} MB)")
                if gz_path.name.lower().endswith(".log.gz"):
                    log_path = gz_path.with_name(gz_path.name[:-3])
                    try:
                        log_path.write_bytes(gzip.open(gz_path, "rb").read())
                        print(f"       → {log_path.name}")
                        out_paths.append(log_path)
                        continue
                    except OSError as e:
                        print(f"       ⚠ 解压失败: {e}")
                out_paths.append(gz_path)
            if not out_paths:
                return None
            return {"type": "logcat_slices", "paths": out_paths}

        ts = parse_android_zip_time(inner)
        ts_s = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "?"
        print(f"  选中: {inner}  (文件名时间: {ts_s})")

        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"  按需解压到: {output_dir}")
        z.extract(targets=[inner], path=output_dir)

        extracted = output_dir / Path(inner).name
        if not extracted.exists():
            extracted = output_dir / inner
        if not extracted.exists():
            for p in output_dir.rglob(Path(inner).name):
                extracted = p
                break

        if extracted.exists():
            print(f"  提取完成: {extracted.name} "
                  f"({extracted.stat().st_size / 1048576:.1f} MB)")
            return {"type": "android_zip", "path": extracted}
        else:
            print(f"  ⚠ 提取后文件不存在: {extracted}")
            return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Range 提取 Jira 分段 7z 内的 android_*.zip")
    ap.add_argument("issue_key", help="如 BAIC-59686")
    ap.add_argument(
        "--prefix",
        default=None,
        help="附件文件名前缀（省略则自动检测）",
    )
    ap.add_argument("-t", "--time", help="故障时间 YYYY-MM-DD HH:MM:SS（用于挑选 android 包）")
    ap.add_argument("-o", "--output-dir", help="解压 android_*.zip 到此目录")
    ap.add_argument(
        "--list-only",
        action="store_true",
        help="仅列出 7z 内文件名，不解压",
    )
    ap.add_argument(
        "--slice-logcat",
        action="store_true",
        help="在已解压的 android_*.zip 内再按故障时间只解 logcat 分片（需 -t 或票上故障时间）",
    )
    ap.add_argument(
        "--with-previous",
        action="store_true",
        help="与 --slice-logcat 合用：多解一条转储时间≤故障时间的分片作边界参考",
    )
    ap.add_argument(
        "--decompress-logcat",
        action="store_true",
        help="与 --slice-logcat 合用：同时写出 .log（去掉 .gz）",
    )
    args = ap.parse_args()

    issue = fetch_issue(args.issue_key)
    fields = issue.get("fields", {})
    atts = fields.get("attachment", [])
    fault: Optional[datetime] = None
    if args.time:
        fault = datetime.strptime(args.time, "%Y-%m-%d %H:%M:%S")
    else:
        raw = fields.get("customfield_12812")
        if raw:
            try:
                fault = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass

    if args.prefix:
        segs = sorted(
            [a for a in atts if a.get("filename", "").startswith(args.prefix)],
            key=lambda a: a["filename"],
        )
        if not segs:
            sys.exit(f"未找到前缀为 {args.prefix!r} 的附件")
    else:
        sz_groups = detect_7z_segment_groups(atts)
        if not sz_groups:
            sys.exit("未找到 7z 分段附件（可用 --prefix 手动指定）")
        if len(sz_groups) > 1:
            print(f"发现 {len(sz_groups)} 组 7z 分段:")
            for i, g in enumerate(sz_groups):
                print(f"  [{i}] {g['prefix']}  ({g['count']} 段, "
                      f"{g['total_size']/1048576:.1f} MB)")
            print(f"使用第 0 组 (最大)；若需其它组，请用 --prefix 指定")
        grp = sz_groups[0]
        segs = sorted(
            [a for a in atts if a.get("filename", "") in set(grp["filenames"])],
            key=lambda a: a["filename"],
        )

    segments: List[Tuple[str, int]] = []
    for a in segs:
        url = a["content"]
        sz = int(a.get("size") or 0)
        if sz <= 0:
            sys.exit(f"附件 {a['filename']} 缺少 size，无法 Range 映射")
        segments.append((url, sz))

    hdrs = _auth_header()
    print(f"虚拟卷大小: {sum(s[1] for s in segments) / 1048576:.1f} MB（不预下载）")
    print("打开 7z（仅按需 Range 读取头/索引）…")

    with open_7z_from_segments(segments, hdrs) as z:
        names = z.getnames()
        print(f"包内文件数: {len(names)}")
        for n in names[:60]:
            print(f"  {n}")
        if len(names) > 60:
            print(f"  … 另有 {len(names) - 60} 个")

        logcat_top = list_logcat_entries_from_7z_listing(names)
        inner = pick_android_zip(names, fault)

        # 7z 顶层直接含 logcat 分片时，只解这些（体积远小于整包 android zip）
        if logcat_top and not inner:
            if not fault:
                sys.exit("7z 内仅有 logcat 分片时，需要故障时间（-t）以挑选文件")
            if args.list_only:
                return
            chosen = pick_members(logcat_top, fault, args.with_previous)
            if not chosen:
                sys.exit("没有「转储时间 > 故障时间」的 logcat 分片")
            out = Path(args.output_dir or ".")
            out.mkdir(parents=True, exist_ok=True)
            lc_dir = out / "logcat_by_fault"
            lc_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n7z 顶层 logcat 分片，只解压 {len(chosen)} 个 → {lc_dir}")
            for tname in chosen:
                z.extract(targets=[tname], path=lc_dir)
                print(f"  ✓ {tname}")
            print(f"完成: {lc_dir.resolve()}")
            return

        if not inner:
            sys.exit("包内未找到 android_*.zip 命名文件，且无顶层 logcat/*.log.gz")

        ts = parse_android_zip_time(inner)
        ts_s = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "?"
        print(f"\n选中: {inner}  (文件名时间≈{ts_s})")
        if fault:
            print(f"故障时间: {fault.strftime('%Y-%m-%d %H:%M:%S')}")

        if args.list_only:
            return

        out = Path(args.output_dir or ".")
        out.mkdir(parents=True, exist_ok=True)
        print(f"\n按需解压到: {out.resolve()}")
        z.extract(targets=[inner], path=out)
        extracted = out / Path(inner).name
        if not extracted.exists():
            extracted = out / inner
        print(f"完成: {extracted}")

        if args.slice_logcat:
            if not fault:
                sys.exit("--slice-logcat 需要故障时间（-t 或票上 customfield_12812）")
            lc_dir = out / "logcat_by_fault"
            lc_dir.mkdir(parents=True, exist_ok=True)
            import gzip

            with zipfile.ZipFile(extracted, "r") as zf:
                rows = list_logcat_members(zf)
                lc_names = pick_members(rows, fault, args.with_previous)
                if not lc_names:
                    sys.exit("android zip 内没有匹配的 logcat 分片")
                print(
                    f"\n--slice-logcat: 从 android zip 只解 {len(lc_names)} 个 logcat → {lc_dir}"
                )
                for n in lc_names:
                    info = zf.getinfo(n)
                    print(f"  ✓ {n}  ({info.file_size / 1048576:.2f} MB)")
                    dest_gz = lc_dir / Path(n).name
                    dest_gz.write_bytes(zf.read(n))
                    if args.decompress_logcat:
                        raw = gzip.open(dest_gz, "rb").read()
                        if dest_gz.name.lower().endswith(".log.gz"):
                            dest_log = dest_gz.with_name(dest_gz.name[:-3])
                        else:
                            dest_log = dest_gz.with_suffix(".log")
                        dest_log.write_bytes(raw)
                        print(f"       → {dest_log.name}")
            print(f"logcat 输出: {lc_dir.resolve()}")


if __name__ == "__main__":
    main()
