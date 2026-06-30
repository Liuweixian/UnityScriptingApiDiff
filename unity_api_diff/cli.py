"""Command-line interface for Unity API diff tool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .diff import diff_members, diff_snapshots
from .fetcher import DocFetcher
from .report import write_html_report, write_json_report


def _progress(done: int, total: int, label: str) -> None:
    pct = (done / total * 100) if total else 100
    print(f"\r  [{done}/{total}] {pct:5.1f}%  {label[:60]:<60}", end="", flush=True)
    if done == total:
        print()


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
        "-o", "--output", default="api-diff.html", help="输出 HTML 文件路径 (默认: api-diff.html)"
    )
    diff_parser.add_argument("--json", help="同时输出 JSON 报告到指定路径")
    diff_parser.add_argument(
        "--members",
        action="store_true",
        help="深度对比：抓取共有类型的成员增删（较慢，需请求大量页面）",
    )
    diff_parser.add_argument(
        "--signatures",
        action="store_true",
        help="与 --members 联用：对比共有成员的签名变更（更慢）",
    )
    diff_parser.add_argument("--cache-dir", default=".cache", help="缓存目录 (默认: .cache)")
    diff_parser.add_argument("--no-cache", action="store_true", help="不使用本地缓存")
    diff_parser.add_argument("--workers", type=int, default=8, help="并发下载线程数")

    list_parser = sub.add_parser("versions", help="列出可用的 Unity 文档版本")
    list_parser.add_argument("--cache-dir", default=".cache")

    return parser


def cmd_versions(args: argparse.Namespace) -> int:
    fetcher = DocFetcher(cache_dir=args.cache_dir)
    versions = fetcher.list_versions()
    print("可用 Unity 文档版本:")
    for version in versions:
        print(f"  {version}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    if args.signatures and not args.members:
        print("错误: --signatures 需要与 --members 一起使用", file=sys.stderr)
        return 2

    fetcher = DocFetcher(cache_dir=args.cache_dir, workers=args.workers)
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

    if args.members:
        common = sorted(old_snapshot.links & new_snapshot.links)
        print(f"抓取 {len(common)} 个共有类型的成员列表 ({args.from_version})...")
        old_members = fetcher.fetch_class_members(
            args.from_version,
            common,
            use_cache=use_cache,
            on_progress=_progress,
        )
        print(f"抓取 {len(common)} 个共有类型的成员列表 ({args.to_version})...")
        new_members = fetcher.fetch_class_members(
            args.to_version,
            common,
            use_cache=use_cache,
            on_progress=_progress,
        )

        old_sigs = None
        new_sigs = None
        if args.signatures:
            candidate_links: list[str] = []
            for type_link in common:
                old_set = old_members.get(type_link, set())
                new_set = new_members.get(type_link, set())
                for member in old_set & new_set:
                    candidate_links.append(f"{type_link}.{member}")

            print(f"抓取 {len(candidate_links)} 个成员页面的签名进行对比...")
            old_sigs = fetcher.fetch_member_signatures(
                args.from_version,
                candidate_links,
                use_cache=use_cache,
                on_progress=_progress,
            )
            new_sigs = fetcher.fetch_member_signatures(
                args.to_version,
                candidate_links,
                use_cache=use_cache,
                on_progress=_progress,
            )

        diff = diff_members(diff, old_members, new_members, old_sigs, new_sigs)
        print(
            f"成员级差异: {len(diff.changed_types)} 个类型有变更, "
            f"{diff.summary['changed_members']} 项成员变更"
        )

    output = write_html_report(diff, args.output, include_members=args.members)
    print(f"HTML 报告已生成: {output.resolve()}")

    if args.json:
        json_path = write_json_report(diff, args.json)
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
