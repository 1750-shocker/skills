#!/usr/bin/env python3
"""
从本地 android_*.zip（车机日志标准结构）中按故障时间只解压 logcat/*.log.gz，
避免整包展开。规则与 SKILL 一致：文件名中时间为转储时间，取「第一个转储时间 > 故障时间」
的文件（该段内包含故障时刻前后日志）。

用法:
  python extract_logcat_from_android_zip.py android_20260410-113520.zip -t "2026-04-09 19:23:00" -o ./out
  python extract_logcat_from_android_zip.py android.zip -t ... --with-previous   # 多解前一个分片作边界参考
  python extract_logcat_from_android_zip.py android.zip -t ... --decompress      # 同时写出 .log
"""
from __future__ import annotations

import argparse
import gzip
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

LOGCAT_RE = re.compile(
    r"(?i)logcat/.*_logcat_(\d{8})-(\d{6})\.log\.gz$"
)


def parse_dump_time(member: str) -> Optional[datetime]:
    m = LOGCAT_RE.search(member.replace("\\", "/"))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def list_logcat_members(zf: zipfile.ZipFile) -> List[Tuple[datetime, str, int]]:
    out: List[Tuple[datetime, str, int]] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        ts = parse_dump_time(info.filename)
        if ts:
            out.append((ts, info.filename, info.file_size))
    out.sort(key=lambda x: x[0])
    return out


def pick_members(
    rows: List[Tuple[datetime, str, int]],
    fault: datetime,
    with_previous: bool,
) -> List[str]:
    """第一个转储时间 > fault；可选再带上时间轴上前一条（便于看轮转边界）。"""
    chosen: List[str] = []
    prev_name: Optional[str] = None
    for ts, name, _ in rows:
        if ts <= fault:
            prev_name = name
            continue
        chosen.append(name)
        if with_previous and prev_name:
            chosen.insert(0, prev_name)
        break
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser(
        description="从 android_*.zip 中按故障时间只解压匹配的 logcat 分片"
    )
    ap.add_argument("android_zip", type=Path, help="本地 android_*.zip 路径")
    ap.add_argument(
        "-t", "--time", required=True, help="故障时间 YYYY-MM-DD HH:MM:SS"
    )
    ap.add_argument("-o", "--output-dir", type=Path, default=Path("."), help="输出目录")
    ap.add_argument(
        "--with-previous",
        action="store_true",
        help="同时解压转储时间≤故障时间的前一条分片（边界参考）",
    )
    ap.add_argument(
        "--decompress",
        action="store_true",
        help="解压 .gz 为同名 .log（UTF-8/gbk 原样字节）",
    )
    args = ap.parse_args()

    fault = datetime.strptime(args.time, "%Y-%m-%d %H:%M:%S")
    zp = args.android_zip
    if not zp.is_file():
        sys.exit(f"找不到文件: {zp}")

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zp, "r") as zf:
        rows = list_logcat_members(zf)
        if not rows:
            sys.exit("zip 内未找到 logcat/*_logcat_*-*.log.gz")

        names = pick_members(rows, fault, args.with_previous)
        if not names:
            sys.exit(
                f"没有「转储时间 > {args.time}」的 logcat 分片（请检查时间或换日志包）"
            )

        print(f"故障时间: {args.time}")
        for n in names:
            info = zf.getinfo(n)
            print(f"  解压: {n}  ({info.file_size / 1048576:.2f} MB)")
            dest_gz = out_dir / Path(n).name
            dest_gz.parent.mkdir(parents=True, exist_ok=True)
            dest_gz.write_bytes(zf.read(n))

            if args.decompress:
                raw = gzip.open(dest_gz, "rb").read()
                if dest_gz.name.lower().endswith(".log.gz"):
                    dest_log = dest_gz.with_name(dest_gz.name[:-3])
                else:
                    dest_log = dest_gz.with_suffix(".log")
                dest_log.write_bytes(raw)
                print(f"       → {dest_log.name}  ({len(raw) / 1048576:.2f} MB)")

        print(f"\n输出目录: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
