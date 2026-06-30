"""Command-line interface for Unity API diff tool."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .diff import diff_members, diff_snapshots
from .fetcher import (
    DEFAULT_CACHE_DIR,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_DELAY,
    DEFAULT_WORKERS,
    DocFetcher,
)
from .paths import TMP_DIR, default_html_report, default_json_report
from .progress import ProgressTracker
from .report import write_html_report, write_json_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unity-api-diff",
        description="比较 Unity Scripting API 在不同版本之间的增删改，并生成 HTML 报告。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    diff_parser = sub.add_parser("diff", help="比较两个 Unity 版本并生成报告")
    diff_parser.add_argument("--from", dest="from_version", required=True, help="旧版本，如 2021.3")
    diff_parser.add_argument("--to", dest="to_version", required=True, help="新版本，如 2022.3")
    diff_parser.add_argument(
        "-o",
        "--output",
        help="输出 HTML 文件路径 (默认: report/<from>-to-<to>.html)",
    )
    diff_parser.add_argument(
        "--json",
        nargs="?",
        const="",
        metavar="PATH",
        help="同时输出 JSON 报告 (默认: report/<from>-to-<to>.json)",
    )
    diff_parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help=f"临时文件与缓存目录 (默认: {TMP_DIR}/)",
    )
    diff_parser.add_argument("--no-cache", action="store_true", help="不使用本地缓存")
    diff_parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"并发下载线程数 (默认: {DEFAULT_WORKERS})",
    )
    diff_parser.add_argument(
        "--request-delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help=f"每次网络请求后的间隔秒数，用于避免触发限流 (默认: {DEFAULT_REQUEST_DELAY})",
    )
    diff_parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=f"遇到 429/503 时的最大重试次数 (默认: {DEFAULT_MAX_RETRIES})",
    )

    list_parser = sub.add_parser("versions", help="列出可用的 Unity 文档版本")
    list_parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help=f"临时文件与缓存目录 (默认: {TMP_DIR}/)",
    )

    return parser


def cmd_versions(args: argparse.Namespace) -> int:
    fetcher = DocFetcher(cache_dir=args.cache_dir)
    versions = fetcher.list_versions()
    print("可用 Unity 文档版本:")
    for version in versions:
        print(f"  {version}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    fetcher = DocFetcher(
        cache_dir=args.cache_dir,
        workers=args.workers,
        request_delay=args.request_delay,
        max_retries=args.max_retries,
    )
    use_cache = not args.no_cache

    print(f"获取 {args.from_version} 的 API 索引...")
    old_snapshot = fetcher.fetch_snapshot(args.from_version, use_cache=use_cache)
    print(f"  → {len(old_snapshot.entries)} 个 API 条目")

    print(f"获取 {args.to_version} 的 API 索引...")
    new_snapshot = fetcher.fetch_snapshot(args.to_version, use_cache=use_cache)
    print(f"  → {len(new_snapshot.entries)} 个 API 条目")

    diff = diff_snapshots(old_snapshot, new_snapshot)
    print(
        f"类型级差异: +{len(diff.added)} 新增, -{len(diff.removed)} 移除, "
        f"{len(old_snapshot.links & new_snapshot.links)} 共有"
    )

    common = sorted(old_snapshot.links & new_snapshot.links)
    member_jobs = (
        [(args.from_version, link) for link in common]
        + [(args.to_version, link) for link in common]
    )
    print(f"抓取 {len(common)} 个共有类型的成员列表（两版本共 {len(member_jobs)} 项）...")
    member_progress = ProgressTracker("成员列表")
    all_members = fetcher.fetch_class_members_batch(
        member_jobs,
        use_cache=use_cache,
        progress=member_progress,
    )
    old_members = {link: all_members[(args.from_version, link)] for link in common}
    new_members = {link: all_members[(args.to_version, link)] for link in common}

    intersection_links: list[str] = []
    added_only_links: list[str] = []
    removed_only_links: list[str] = []
    for type_link in common:
        old_set = old_members.get(type_link, set())
        new_set = new_members.get(type_link, set())
        for member in old_set & new_set:
            intersection_links.append(f"{type_link}.{member}")
        for member in new_set - old_set:
            added_only_links.append(f"{type_link}.{member}")
        for member in old_set - new_set:
            removed_only_links.append(f"{type_link}.{member}")

    sig_jobs = (
        [(args.from_version, link) for link in intersection_links + removed_only_links]
        + [(args.to_version, link) for link in intersection_links + added_only_links]
    )
    print(f"抓取成员签名（共 {len(sig_jobs)} 项）...")
    sig_progress = ProgressTracker("成员签名")
    all_sigs = fetcher.fetch_member_signatures_batch(
        sig_jobs,
        use_cache=use_cache,
        progress=sig_progress,
    )
    old_sigs = {
        link: all_sigs[(args.from_version, link)]
        for link in intersection_links + removed_only_links
    }
    new_sigs = {
        link: all_sigs[(args.to_version, link)]
        for link in intersection_links + added_only_links
    }

    diff = diff_members(diff, old_members, new_members, old_sigs, new_sigs)
    print(
        f"成员级差异: {len(diff.changed_types)} 个类型有变更, "
        f"{diff.summary['changed_members']} 项成员变更"
    )

    html_output = (
        Path(args.output)
        if args.output
        else default_html_report(args.from_version, args.to_version)
    )
    output = write_html_report(diff, html_output)
    print(f"HTML 报告已生成: {output.resolve()}")

    if args.json is not None:
        json_output = (
            Path(args.json)
            if args.json
            else default_json_report(args.from_version, args.to_version)
        )
        json_path = write_json_report(diff, json_output)
        print(f"JSON 报告已生成: {json_path.resolve()}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "versions":
        return cmd_versions(args)
    if args.command == "diff":
        return cmd_diff(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
