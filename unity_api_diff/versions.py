"""Unity documentation version helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

VERSIONS_INFO_URL = "https://docs.unity3d.com/StaticFilesConfig/UnityVersionsInfo.js"

# Fallback when network is unavailable.
DEFAULT_VERSIONS = [
    "6000.7", "6000.6", "6000.5", "6000.3", "6000.0",
    "2023.2", "2023.1", "2022.3", "2022.2", "2022.1",
    "2021.3", "2021.2", "2021.1", "2020.3", "2020.2", "2020.1",
    "2019.4", "2019.3", "2019.2", "2019.1",
    "2018.4", "2018.3", "2018.2", "2018.1",
    "2017.4", "2017.3", "2017.2", "2017.1",
    "5.6", "5.5", "5.4", "5.3", "5.2",
]


@dataclass(frozen=True)
class UnityVersion:
    major: int
    minor: int

    @classmethod
    def parse(cls, value: str) -> UnityVersion:
        value = value.strip()
        if value.startswith("unity"):
            value = value[5:]
        parts = value.split(".")
        if len(parts) != 2:
            raise ValueError(f"Invalid version format: {value!r} (expected e.g. 2022.3)")
        return cls(int(parts[0]), int(parts[1]))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"

    def url_segment(self) -> str:
        if self.major == 5:
            return f"5{self.minor}0"[:3]  # 5.6 -> 560
        return str(self)

    def script_reference_base(self) -> str:
        segment = self.url_segment()
        if self.major == 5:
            return f"https://docs.unity3d.com/{segment}/Documentation/ScriptReference/"
        return f"https://docs.unity3d.com/{self}/Documentation/ScriptReference/"

    def toc_url(self) -> str:
        return f"{self.script_reference_base()}docdata/toc.js"

    def page_url(self, link: str) -> str:
        return f"{self.script_reference_base()}{link}.html"


def parse_versions_info(js_text: str) -> list[str]:
    versions: list[str] = []
    for block in ("supported", "notSupported"):
        pattern = rf'{block}:\s*\[(.*?)\]'
        match = re.search(pattern, js_text, re.DOTALL)
        if not match:
            continue
        for major, minor in re.findall(r"major:\s*(\d+),\s*minor:\s*(\d+)", match.group(1)):
            versions.append(f"{major}.{minor}")
    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for version in versions:
        if version not in seen:
            seen.add(version)
            ordered.append(version)
    return ordered
