"""Project directory layout helpers."""

from __future__ import annotations

from pathlib import Path

TMP_DIR = Path("tmp")
REPORT_DIR = Path("report")


def report_stem(from_version: str, to_version: str) -> str:
    """Build a filename stem like ``2021.3-to-2022.3``."""
    return f"{from_version}-to-{to_version}"


def default_html_report(from_version: str, to_version: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR / f"{report_stem(from_version, to_version)}.html"


def default_json_report(from_version: str, to_version: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR / f"{report_stem(from_version, to_version)}.json"
