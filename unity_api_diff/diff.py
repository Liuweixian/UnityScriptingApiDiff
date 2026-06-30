"""Compare Unity Scripting API snapshots between versions."""

from __future__ import annotations

from dataclasses import dataclass, field

from .parser import ApiEntry, ApiSnapshot
from .versions import UnityVersion


def split_namespace_class(link: str) -> tuple[str, str]:
    """Split a type link into (namespace, class_name)."""
    if "." in link:
        namespace, class_name = link.rsplit(".", 1)
        return namespace, class_name
    return "", link


def group_entries_by_namespace(
    entries: list[ApiEntry],
) -> list[tuple[str, list[ApiEntry]]]:
    buckets: dict[str, list[ApiEntry]] = {}
    for entry in entries:
        namespace, _ = split_namespace_class(entry.link)
        buckets.setdefault(namespace, []).append(entry)
    return [
        (namespace, sorted(items, key=lambda e: e.title.lower()))
        for namespace, items in sorted(buckets.items(), key=lambda x: x[0].lower())
    ]


def group_member_diffs_by_namespace(
    diffs: list["TypeMemberDiff"],
) -> list[tuple[str, list["TypeMemberDiff"]]]:
    buckets: dict[str, list[TypeMemberDiff]] = {}
    for diff in diffs:
        buckets.setdefault(diff.namespace, []).append(diff)
    return [
        (namespace, sorted(items, key=lambda d: d.type_title.lower()))
        for namespace, items in sorted(buckets.items(), key=lambda x: x[0].lower())
    ]


@dataclass
class MemberInfo:
    name: str
    member_link: str
    signatures: list[str] = field(default_factory=list)


@dataclass
class MemberChange:
    type_link: str
    member_name: str
    member_link: str
    old_signatures: list[str] = field(default_factory=list)
    new_signatures: list[str] = field(default_factory=list)


@dataclass
class TypeMemberDiff:
    type_link: str
    type_title: str
    namespace: str
    added_members: list[MemberInfo] = field(default_factory=list)
    removed_members: list[MemberInfo] = field(default_factory=list)
    changed_members: list[MemberChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added_members or self.removed_members or self.changed_members)


@dataclass
class ApiDiff:
    from_version: str
    to_version: str
    added: list[ApiEntry] = field(default_factory=list)
    removed: list[ApiEntry] = field(default_factory=list)
    member_diffs: list[TypeMemberDiff] = field(default_factory=list)

    @property
    def changed_types(self) -> list[TypeMemberDiff]:
        return [diff for diff in self.member_diffs if diff.has_changes]

    @property
    def summary(self) -> dict[str, int]:
        changed_member_count = sum(
            len(d.added_members) + len(d.removed_members) + len(d.changed_members)
            for d in self.member_diffs
        )
        return {
            "added": len(self.added),
            "removed": len(self.removed),
            "changed_types": len(self.changed_types),
            "changed_members": changed_member_count,
        }


def diff_snapshots(old: ApiSnapshot, new: ApiSnapshot) -> ApiDiff:
    old_links = old.links
    new_links = new.links

    added_links = sorted(new_links - old_links)
    removed_links = sorted(old_links - new_links)

    return ApiDiff(
        from_version=old.version,
        to_version=new.version,
        added=[new.entries[link] for link in added_links],
        removed=[old.entries[link] for link in removed_links],
    )


def diff_members(
    diff: ApiDiff,
    old_members: dict[str, set[str]],
    new_members: dict[str, set[str]],
    old_signatures: dict[str, list[str]] | None = None,
    new_signatures: dict[str, list[str]] | None = None,
) -> ApiDiff:
    common_links = sorted(
        set(old_members.keys()) & set(new_members.keys())
    )

    member_diffs: list[TypeMemberDiff] = []
    for type_link in common_links:
        old_set = old_members.get(type_link, set())
        new_set = new_members.get(type_link, set())
        added = sorted(new_set - old_set)
        removed = sorted(old_set - new_set)

        changed: list[MemberChange] = []
        if old_signatures and new_signatures:
            for member in sorted(old_set & new_set):
                member_link = f"{type_link}.{member}"
                old_sigs = old_signatures.get(member_link, [])
                new_sigs = new_signatures.get(member_link, [])
                if old_sigs != new_sigs:
                    changed.append(
                        MemberChange(
                            type_link=type_link,
                            member_name=member,
                            member_link=member_link,
                            old_signatures=old_sigs,
                            new_signatures=new_sigs,
                        )
                    )

        if added or removed or changed:
            namespace, title = split_namespace_class(type_link)
            added_infos = [
                MemberInfo(
                    name=member,
                    member_link=f"{type_link}.{member}",
                    signatures=(
                        new_signatures.get(f"{type_link}.{member}", [])
                        if new_signatures
                        else []
                    ),
                )
                for member in added
            ]
            removed_infos = [
                MemberInfo(
                    name=member,
                    member_link=f"{type_link}.{member}",
                    signatures=(
                        old_signatures.get(f"{type_link}.{member}", [])
                        if old_signatures
                        else []
                    ),
                )
                for member in removed
            ]
            member_diffs.append(
                TypeMemberDiff(
                    type_link=type_link,
                    type_title=title,
                    namespace=namespace,
                    added_members=added_infos,
                    removed_members=removed_infos,
                    changed_members=changed,
                )
            )

    diff.member_diffs = member_diffs
    return diff


def doc_url(version: str, link: str) -> str:
    return UnityVersion.parse(version).page_url(link)
