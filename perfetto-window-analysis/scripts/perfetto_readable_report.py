#!/usr/bin/env python3
import argparse
import ast
import contextlib
import csv
import hashlib
import os
import platform
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence
from urllib.request import urlopen

SHELL_URL = "https://get.perfetto.dev/trace_processor"
LOGCAT_TS_RE = re.compile(
    r"^(?P<ts>\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+\d+\s+\d+\s+\w\s+[^:]+:\s*(?P<message>.*)$"
)


@dataclass
class TimeContext:
    start_ns: int
    end_ns: int
    offset_ns: int
    start_wall_ns: int
    end_wall_ns: int


@dataclass
class EventCandidate:
    label: str
    naive_time: datetime
    source: str
    raw: str


@dataclass
class EventWindow:
    label: str
    wall_time: datetime
    source: str
    raw: str


@dataclass
class ReportTable:
    title: str
    slug: str
    columns: Sequence[str]
    rows: list[dict[str, object]]


def require_perfetto():
    try:
        from perfetto.trace_processor import TraceProcessor, TraceProcessorConfig
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing Python package 'perfetto'. Install it with: py -m pip install --user perfetto"
        ) from exc
    return TraceProcessor, TraceProcessorConfig


def ensure_shell_wrapper() -> Path:
    wrapper = Path(tempfile.gettempdir()) / "trace_processor_python_api"
    if wrapper.exists() and wrapper.stat().st_size > 0:
        return wrapper
    with contextlib.closing(urlopen(SHELL_URL, timeout=120)) as resp, wrapper.open("wb") as fh:
        fh.write(resp.read())
    return wrapper


def parse_manifest(wrapper: Path) -> Sequence[dict]:
    text = wrapper.read_text(encoding="utf-8")
    match = re.search(r"TRACE_PROCESSOR_SHELL_MANIFEST = (\[.*?\])\n\n# -----", text, re.S)
    if not match:
        raise SystemExit(f"Unable to parse manifest from {wrapper}")
    return ast.literal_eval(match.group(1))


def resolve_manifest_entry(manifest: Sequence[dict]) -> dict:
    plat = sys.platform.lower()
    machine = platform.machine().lower()
    for entry in manifest:
        if entry.get("platform") == plat and machine in entry.get("machine", []):
            return entry
    raise SystemExit(f"No trace processor prebuilt for {plat}-{machine}")


def download_if_needed(entry: dict) -> Path:
    cache_dir = Path.home() / ".local" / "share" / "perfetto" / "prebuilts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    root, ext = os.path.splitext(entry["file_name"])
    sha256 = entry["sha256"]
    target = cache_dir / f"{root}-{sha256[:16]}{ext}"
    if target.exists() and target.stat().st_size > 0:
        return target

    tmp = target.with_suffix(target.suffix + ".download")
    hasher = hashlib.sha256()
    with contextlib.closing(urlopen(entry["url"], timeout=300)) as resp, tmp.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            hasher.update(chunk)
    actual = hasher.hexdigest()
    if actual != sha256:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"Checksum mismatch for trace processor: {actual} != {sha256}")
    current_mode = tmp.stat().st_mode
    os.chmod(tmp, current_mode | stat.S_IEXEC)
    os.replace(tmp, target)
    return target


def open_tp(trace_path: Path):
    TraceProcessor, TraceProcessorConfig = require_perfetto()
    wrapper = ensure_shell_wrapper()
    entry = resolve_manifest_entry(parse_manifest(wrapper))
    bin_path = download_if_needed(entry)
    config = TraceProcessorConfig(bin_path=str(bin_path), load_timeout=60)
    return TraceProcessor(trace=str(trace_path), config=config)


def rows(tp, sql: str):
    return list(tp.query(sql))


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "table"


def ns_to_wall(ns_value: int) -> datetime:
    return datetime.fromtimestamp(ns_value / 1e9, tz=timezone.utc)


def format_wall(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds")


def parse_time_text(raw: str, default_year: int) -> datetime:
    text = raw.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%m-%d %H:%M:%S.%f",
        "%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                parsed = parsed.replace(year=default_year)
            return parsed
        except ValueError:
            continue
    raise SystemExit(f"Unsupported event time format: {raw}")


def to_aware(dt: datetime, offset_hours: int) -> datetime:
    return dt.replace(tzinfo=timezone(timedelta(hours=offset_hours))).astimezone(timezone.utc)


def parse_manual_events(raw_events: Sequence[str], default_year: int) -> list[EventCandidate]:
    events: list[EventCandidate] = []
    for item in raw_events:
        label = item
        timestamp = item
        if "=" in item:
            maybe_label, maybe_time = item.split("=", 1)
            if ":" in maybe_time:
                label = maybe_label.strip()
                timestamp = maybe_time.strip()
        events.append(
            EventCandidate(
                label=label,
                naive_time=parse_time_text(timestamp, default_year),
                source="cli",
                raw=item,
            )
        )
    return events


def extract_logcat_events(
    logcat_path: Path,
    patterns: Sequence[str],
    default_year: int,
    event_limit: int | None,
) -> list[EventCandidate]:
    matches: list[EventCandidate] = []
    with logcat_path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line_no, line in enumerate(fh, 1):
            match = LOGCAT_TS_RE.match(line)
            if not match:
                continue
            message = match.group("message").strip()
            naive_time = parse_time_text(match.group("ts"), default_year)
            for pattern in patterns:
                if pattern in line:
                    matches.append(
                        EventCandidate(
                            label=f"{pattern} #{line_no}",
                            naive_time=naive_time,
                            source=message[:140] if message else line.strip()[:140],
                            raw=line.strip(),
                        )
                    )
    if event_limit is not None and len(matches) > event_limit:
        matches = matches[-event_limit:]
    return matches


def infer_offset_hours(candidates: Sequence[EventCandidate], context: TimeContext, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    if not candidates:
        local_offset = datetime.now().astimezone().utcoffset()
        return int((local_offset or timedelta()).total_seconds() // 3600)

    best_offset = 0
    best_score = (-1, -1.0)
    margin_ns = int(30 * 60 * 1e9)
    for offset in range(-12, 15):
        inside = 0
        closeness = 0.0
        for candidate in candidates:
            event_ns = int(to_aware(candidate.naive_time, offset).timestamp() * 1e9)
            if context.start_wall_ns - margin_ns <= event_ns <= context.end_wall_ns + margin_ns:
                inside += 1
                delta = abs(event_ns - (context.start_wall_ns + context.end_wall_ns) // 2)
                closeness -= delta / 1e9
        score = (inside, closeness)
        if score > best_score:
            best_score = score
            best_offset = offset
    return best_offset


def materialize_events(candidates: Sequence[EventCandidate], offset_hours: int) -> list[EventWindow]:
    windows = [
        EventWindow(
            label=candidate.label,
            wall_time=to_aware(candidate.naive_time, offset_hours),
            source=candidate.source,
            raw=candidate.raw,
        )
        for candidate in candidates
    ]
    windows.sort(key=lambda item: item.wall_time)
    return windows


def get_time_context(tp) -> TimeContext:
    trace_bounds = rows(tp, "select start_ts, end_ts from trace_bounds")
    if not trace_bounds:
        raise SystemExit("trace_bounds is empty")
    clocks = rows(
        tp,
        """
        select clock_name, clock_value
        from clock_snapshot
        where snapshot_id = (select min(snapshot_id) from clock_snapshot)
          and clock_name in ('REALTIME', 'BOOTTIME')
        """,
    )
    values = {row.clock_name: row.clock_value for row in clocks}
    if "REALTIME" not in values or "BOOTTIME" not in values:
        raise SystemExit("clock_snapshot is missing REALTIME/BOOTTIME mapping")
    start_ns = trace_bounds[0].start_ts
    end_ns = trace_bounds[0].end_ts
    offset_ns = values["REALTIME"] - values["BOOTTIME"]
    return TimeContext(
        start_ns=start_ns,
        end_ns=end_ns,
        offset_ns=offset_ns,
        start_wall_ns=start_ns + offset_ns,
        end_wall_ns=end_ns + offset_ns,
    )


def wall_to_trace_ns(dt: datetime, context: TimeContext) -> int:
    return int(dt.timestamp() * 1e9) - context.offset_ns


def add_table(tables: list[ReportTable], title: str, slug: str, columns: Sequence[str], query_rows: Iterable[object]) -> None:
    table_rows: list[dict[str, object]] = []
    for row in query_rows:
        table_rows.append({column: getattr(row, column) for column in columns})
    tables.append(ReportTable(title=title, slug=slug, columns=columns, rows=table_rows))


def render_table(title: str, columns: Sequence[str], data: Iterable[dict[str, object]]) -> str:
    out = [f"## {title}"]
    out.append(" | ".join(columns))
    out.append(" | ".join(["---"] * len(columns)))
    for row in data:
        values = []
        for col in columns:
            val = row.get(col)
            values.append("" if val is None else str(val))
        out.append(" | ".join(values))
    return "\n".join(out)


def render_report(header_lines: Sequence[str], tables: Sequence[ReportTable]) -> str:
    sections = ["\n".join(header_lines)]
    sections.extend(render_table(table.title, table.columns, table.rows) for table in tables)
    return "\n\n".join(sections) + "\n"


def export_csv(tables: Sequence[ReportTable], csv_dir: Path) -> None:
    csv_dir.mkdir(parents=True, exist_ok=True)
    for index, table in enumerate(tables, 1):
        path = csv_dir / f"{index:02d}_{table.slug}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(table.columns))
            writer.writeheader()
            writer.writerows(table.rows)


def build_window_tables(tp, process_name: str, context: TimeContext, event: EventWindow, window_ms: int, index: int) -> list[ReportTable]:
    center_ns = wall_to_trace_ns(event.wall_time, context)
    half_window_ns = int(window_ms * 1e6)
    start_ns = max(context.start_ns, center_ns - half_window_ns)
    end_ns = min(context.end_ns, center_ns + half_window_ns)
    process_sql = sql_quote(process_name)
    label_slug = slugify(event.label)
    event_title = f"Window {index:02d} {event.label}"

    tables: list[ReportTable] = []
    tables.append(
        ReportTable(
            title=f"{event_title} Summary",
            slug=f"window_{index:02d}_{label_slug}_summary",
            columns=["label", "wall_time", "trace_offset_s", "window_ms", "source"],
            rows=[
                {
                    "label": event.label,
                    "wall_time": format_wall(event.wall_time),
                    "trace_offset_s": round((center_ns - context.start_ns) / 1e9, 3),
                    "window_ms": window_ms,
                    "source": event.source,
                }
            ],
        )
    )

    main_rows = rows(
        tp,
        f"""
        select replace(slice.name, char(10), ' ') as name,
               round(sum((min(slice.ts + slice.dur, {end_ns}) - max(slice.ts, {start_ns})) / 1e6), 3) as overlap_ms,
               count(*) as cnt
        from slice
        join thread_track tt on slice.track_id = tt.id
        join thread t on tt.utid = t.utid
        join process p on t.upid = p.upid
        where p.name = {process_sql}
          and t.is_main_thread = 1
          and slice.dur > 0
          and slice.ts < {end_ns}
          and slice.ts + slice.dur > {start_ns}
        group by slice.name
        order by sum(min(slice.ts + slice.dur, {end_ns}) - max(slice.ts, {start_ns})) desc
        limit 20
        """,
    )
    add_table(
        tables,
        f"{event_title} Main Thread Slices",
        f"window_{index:02d}_{label_slug}_main_thread",
        ["name", "overlap_ms", "cnt"],
        main_rows,
    )

    render_rows = rows(
        tp,
        f"""
        select replace(slice.name, char(10), ' ') as name,
               round(sum((min(slice.ts + slice.dur, {end_ns}) - max(slice.ts, {start_ns})) / 1e6), 3) as overlap_ms,
               count(*) as cnt
        from slice
        join thread_track tt on slice.track_id = tt.id
        join thread t on tt.utid = t.utid
        join process p on t.upid = p.upid
        where p.name = {process_sql}
          and t.name = 'RenderThread'
          and slice.dur > 0
          and slice.ts < {end_ns}
          and slice.ts + slice.dur > {start_ns}
        group by slice.name
        order by sum(min(slice.ts + slice.dur, {end_ns}) - max(slice.ts, {start_ns})) desc
        limit 20
        """,
    )
    add_table(
        tables,
        f"{event_title} RenderThread Slices",
        f"window_{index:02d}_{label_slug}_render_thread",
        ["name", "overlap_ms", "cnt"],
        render_rows,
    )

    sched_rows = rows(
        tp,
        f"""
        select coalesce(p.name, '') as process_name,
               coalesce(t.name, '') as thread_name,
               t.tid,
               round(sum((min(s.ts_end, {end_ns}) - max(s.ts, {start_ns})) / 1e6), 3) as running_ms,
               count(*) as slices
        from sched s
        join thread t on s.utid = t.utid
        left join process p on t.upid = p.upid
        where s.utid != 0
          and s.end_state = 'R'
          and s.ts < {end_ns}
          and s.ts_end > {start_ns}
        group by s.utid
        order by sum(min(s.ts_end, {end_ns}) - max(s.ts, {start_ns})) desc
        limit 15
        """,
    )
    add_table(
        tables,
        f"{event_title} Running Threads",
        f"window_{index:02d}_{label_slug}_running_threads",
        ["process_name", "thread_name", "tid", "running_ms", "slices"],
        sched_rows,
    )

    frame_rows = rows(
        tp,
        f"""
        select replace(slice.name, char(10), ' ') as name,
               round(slice.dur / 1e6, 3) as dur_ms,
               round((slice.ts - {center_ns}) / 1e6, 3) as start_delta_ms
        from slice
        join thread_track tt on slice.track_id = tt.id
        join thread t on tt.utid = t.utid
        join process p on t.upid = p.upid
        where p.name = {process_sql}
          and t.is_main_thread = 1
          and slice.name like 'Choreographer#doFrame%'
          and slice.ts < {end_ns}
          and slice.ts + slice.dur > {start_ns}
        order by abs(slice.ts - {center_ns}), slice.dur desc
        limit 12
        """,
    )
    add_table(
        tables,
        f"{event_title} Nearby Frames",
        f"window_{index:02d}_{label_slug}_frames",
        ["name", "dur_ms", "start_delta_ms"],
        frame_rows,
    )
    return tables


def filter_events_to_trace(events: Sequence[EventWindow], context: TimeContext, window_ms: int) -> list[EventWindow]:
    half_window_ns = int(window_ms * 1e6)
    kept: list[EventWindow] = []
    for event in events:
        center_ns = wall_to_trace_ns(event.wall_time, context)
        if center_ns + half_window_ns < context.start_ns:
            continue
        if center_ns - half_window_ns > context.end_ns:
            continue
        kept.append(event)
    return kept


def build_report(
    trace_path: Path,
    process_name: str,
    manual_events: Sequence[str],
    logcat_path: Path | None,
    event_patterns: Sequence[str],
    event_limit: int | None,
    window_ms: int,
    event_tz_offset_hours: int | None,
):
    with open_tp(trace_path) as tp:
        context = get_time_context(tp)
        start_wall = ns_to_wall(context.start_wall_ns)
        end_wall = ns_to_wall(context.end_wall_ns)

        header_lines = [
            "# Perfetto Readable Report",
            f"trace: {trace_path}",
            f"process: {process_name}",
            f"trace_wall_start_utc: {format_wall(start_wall)}",
            f"trace_wall_end_utc: {format_wall(end_wall)}",
        ]
        tables: list[ReportTable] = []
        tables.append(
            ReportTable(
                title="Trace Bounds",
                slug="trace_bounds",
                columns=["start_ts", "end_ts", "start_wall_utc", "end_wall_utc", "duration_s"],
                rows=[
                    {
                        "start_ts": context.start_ns,
                        "end_ts": context.end_ns,
                        "start_wall_utc": format_wall(start_wall),
                        "end_wall_utc": format_wall(end_wall),
                        "duration_s": round((context.end_ns - context.start_ns) / 1e9, 3),
                    }
                ],
            )
        )

        top_threads = rows(
            tp,
            """
            select coalesce(p.name, '') as process_name,
                   coalesce(t.name, '') as thread_name,
                   t.tid,
                   round(sum(s.dur) / 1e9, 3) as running_s,
                   count(*) as slices
            from sched s
            join thread t on s.utid = t.utid
            left join process p on t.upid = p.upid
            where s.utid != 0 and s.end_state = 'R'
            group by s.utid
            order by sum(s.dur) desc
            limit 20
            """,
        )
        add_table(
            tables,
            "Top Running Threads",
            "top_running_threads",
            ["process_name", "thread_name", "tid", "running_s", "slices"],
            top_threads,
        )

        process_sql = sql_quote(process_name)
        main_slices = rows(
            tp,
            f"""
            select slice.name,
                   round(sum(slice.dur) / 1e6, 3) as total_ms,
                   count(*) as cnt
            from slice
            join thread_track tt on slice.track_id = tt.id
            join thread t on tt.utid = t.utid
            join process p on t.upid = p.upid
            where p.name = {process_sql} and t.is_main_thread = 1 and slice.dur > 0
            group by slice.name
            order by sum(slice.dur) desc
            limit 30
            """,
        )
        add_table(tables, "Main Thread Top Slices", "main_thread_top_slices", ["name", "total_ms", "cnt"], main_slices)

        render_slices = rows(
            tp,
            f"""
            select slice.name,
                   round(sum(slice.dur) / 1e6, 3) as total_ms,
                   count(*) as cnt
            from slice
            join thread_track tt on slice.track_id = tt.id
            join thread t on tt.utid = t.utid
            join process p on t.upid = p.upid
            where p.name = {process_sql} and t.name = 'RenderThread' and slice.dur > 0
            group by slice.name
            order by sum(slice.dur) desc
            limit 30
            """,
        )
        add_table(tables, "RenderThread Top Slices", "renderthread_top_slices", ["name", "total_ms", "cnt"], render_slices)

        slow_frames = rows(
            tp,
            f"""
            select replace(slice.name, char(10), ' ') as name,
                   round(slice.dur / 1e6, 3) as dur_ms,
                   round((slice.ts - (select start_ts from trace_bounds)) / 1e9, 3) as since_start_s,
                   round((slice.ts + {context.offset_ns}) / 1e9, 3) as wall_epoch_s
            from slice
            join thread_track tt on slice.track_id = tt.id
            join thread t on tt.utid = t.utid
            join process p on t.upid = p.upid
            where p.name = {process_sql}
              and t.is_main_thread = 1
              and slice.name like 'Choreographer#doFrame%'
              and slice.dur > 16e6
            order by slice.dur desc
            limit 20
            """,
        )
        add_table(
            tables,
            "Slow Main Frames",
            "slow_main_frames",
            ["name", "dur_ms", "since_start_s", "wall_epoch_s"],
            slow_frames,
        )

        ui_hotspots = rows(
            tp,
            f"""
            select replace(slice.name, char(10), ' ') as name,
                   round(sum(slice.dur) / 1e6, 3) as total_ms,
                   count(*) as cnt
            from slice
            join thread_track tt on slice.track_id = tt.id
            join thread t on tt.utid = t.utid
            join process p on t.upid = p.upid
            where p.name = {process_sql}
              and t.is_main_thread = 1
              and slice.dur > 0
              and (
                    slice.name like '%inflate%'
                 or slice.name like '%layout%'
                 or slice.name like '%measure%'
                 or slice.name like '%draw%'
                 or slice.name like '%RecyclerView%'
                 or slice.name like '%Fragment%'
              )
            group by slice.name
            order by sum(slice.dur) desc
            limit 30
            """,
        )
        add_table(tables, "UI Hotspots", "ui_hotspots", ["name", "total_ms", "cnt"], ui_hotspots)

        candidates = parse_manual_events(manual_events, start_wall.year)
        if logcat_path and event_patterns:
            candidates.extend(extract_logcat_events(logcat_path, event_patterns, start_wall.year, event_limit))
        inferred_offset = infer_offset_hours(candidates, context, event_tz_offset_hours)
        header_lines.append(f"event_time_offset_hours: {inferred_offset}")

        events = materialize_events(candidates, inferred_offset)
        events = filter_events_to_trace(events, context, window_ms)
        if events:
            tables.append(
                ReportTable(
                    title="Event Windows",
                    slug="event_windows",
                    columns=["label", "wall_time_utc", "trace_offset_s", "source"],
                    rows=[
                        {
                            "label": event.label,
                            "wall_time_utc": format_wall(event.wall_time),
                            "trace_offset_s": round((wall_to_trace_ns(event.wall_time, context) - context.start_ns) / 1e9, 3),
                            "source": event.source,
                        }
                        for event in events
                    ],
                )
            )
            for index, event in enumerate(events, 1):
                tables.extend(build_window_tables(tp, process_name, context, event, window_ms, index))

        return render_report(header_lines, tables), tables


def main():
    parser = argparse.ArgumentParser(description="Make a Perfetto trace readable with prebuilt SQL summaries.")
    parser.add_argument("trace", help="Path to trace.perfetto-trace")
    parser.add_argument("--process", default="com.autolink.music", help="Target process name")
    parser.add_argument("--out", help="Optional report output path")
    parser.add_argument("--csv-dir", help="Optional directory for CSV exports")
    parser.add_argument("--event-time", action="append", default=[], help="Manual event time, optionally label=time")
    parser.add_argument("--logcat", help="Optional logcat file used to extract event times")
    parser.add_argument("--event-pattern", action="append", default=[], help="Substring to match in logcat for event windows")
    parser.add_argument("--event-limit", type=int, default=6, help="Keep only the latest N extracted logcat events")
    parser.add_argument("--window-ms", type=int, default=1000, help="Half window size around each event in milliseconds")
    parser.add_argument("--event-tz-offset-hours", type=int, help="Override timezone offset for event times, such as 8 for CST")
    args = parser.parse_args()

    trace_path = Path(args.trace)
    if not trace_path.is_file():
        raise SystemExit(f"Trace file not found: {trace_path}")
    logcat_path = Path(args.logcat) if args.logcat else None
    if logcat_path and not logcat_path.is_file():
        raise SystemExit(f"Logcat file not found: {logcat_path}")

    report, tables = build_report(
        trace_path=trace_path,
        process_name=args.process,
        manual_events=args.event_time,
        logcat_path=logcat_path,
        event_patterns=args.event_pattern,
        event_limit=args.event_limit,
        window_ms=args.window_ms,
        event_tz_offset_hours=args.event_tz_offset_hours,
    )
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"wrote report to {out_path}")
    else:
        print(report)
    if args.csv_dir:
        export_csv(tables, Path(args.csv_dir))
        print(f"wrote csv tables to {Path(args.csv_dir)}")


if __name__ == "__main__":
    main()
