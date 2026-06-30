"""Project directory layout helpers."""

from __future__ import annotations

from pathlib import Path

TMP_DIR = Path("tmp")
REPORT_DIR = Path("report")


def report_stem(
    from_version: str,
    to_version: str,
    *,
    members: bool = False,
    signatures: bool = False,
) -> str:
    """Build a filename stem like ``2021.3-to-2022.3-members``."""
    stem = f"{from_version}-to-{to_version}"
    if signatures:
        stem += "-signatures"
    elif members:
        stem += "-members"
    return stem


def default_html_report(
    from_version: str,
    to_version: str,
    *,
    members: bool = False,
    signatures: bool = False,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR / f"{report_stem(from_version, to_version, members=members, signatures=signatures)}.html"


def default_json_report(
    from_version: str,
    to_version: str,
    *,
    members: bool = False,
    signatures: bool = False,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR / f"{report_stem(from_version, to_version, members=members, signatures=signatures)}.json"
