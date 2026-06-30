"""Parse Unity Scripting API documentation data."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

TOC_PREFIX = "var toc = "


@dataclass
class ApiEntry:
    link: str
    path: str
    title: str


@dataclass
class ApiSnapshot:
    version: str
    entries: dict[str, ApiEntry] = field(default_factory=dict)

    @property
    def links(self) -> set[str]:
        return set(self.entries.keys())


def parse_toc_js(content: str, version: str) -> ApiSnapshot:
    text = content.strip()
    if not text.startswith(TOC_PREFIX):
        raise ValueError("Could not parse toc.js content")

    toc = json.loads(text[len(TOC_PREFIX) :].rstrip().rstrip(";"))
    snapshot = ApiSnapshot(version=version)

    def walk(node: dict | None, path: list[str]) -> None:
        if not node:
            return
        title = node.get("title", "")
        link = node.get("link", "")
        current_path = path + [title] if title and title != "toc" else path

        if link and link not in ("null", "toc"):
            snapshot.entries[link] = ApiEntry(
                link=link,
                path=".".join(current_path),
                title=title or link.rsplit(".", 1)[-1],
            )

        for child in node.get("children") or []:
            walk(child, current_path)

    walk(toc, [])
    return snapshot


def extract_class_members(html: str, type_link: str) -> set[str]:
    """Extract member names listed on a type's ScriptReference page."""
    members: set[str] = set()
    prefix = re.escape(type_link) + r"\."
    pattern = re.compile(rf'href="{prefix}([^".]+)\.html"')
    for match in pattern.finditer(html):
        members.add(match.group(1))
    return members


def extract_signatures(html: str) -> list[str]:
    signatures: list[str] = []
    for block in re.findall(r'<div class="signature-CS sig-block">(.*?)</div>', html, re.DOTALL):
        text = re.sub(r"<[^>]+>", "", block)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"^Declaration\s*", "", text)
        if text:
            signatures.append(text)
    return signatures
