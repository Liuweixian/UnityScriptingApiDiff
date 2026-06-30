"""Download and cache Unity documentation data."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable

import requests

from .parser import ApiSnapshot, extract_class_members, extract_signatures, parse_toc_js
from .paths import TMP_DIR
from .versions import VERSIONS_INFO_URL, DEFAULT_VERSIONS, UnityVersion, parse_versions_info

DEFAULT_CACHE_DIR = TMP_DIR
USER_AGENT = "UnityScriptingApiDiff/0.1 (+https://github.com/)"
DEFAULT_WORKERS = 4
DEFAULT_REQUEST_DELAY = 0.3
DEFAULT_MAX_RETRIES = 6
RETRYABLE_STATUS_CODES = {429, 503}


class FetchError(RuntimeError):
    pass


def _retry_after_seconds(response: requests.Response) -> float | None:
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


class DocFetcher:
    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        workers: int = DEFAULT_WORKERS,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.workers = workers
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._request_lock = threading.Lock()

    def _cache_path(self, key: str, suffix: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{digest}{suffix}"

    def fetch_text(self, url: str, use_cache: bool = True) -> str:
        cache_file = self._cache_path(url, ".txt")
        if use_cache and cache_file.exists():
            return cache_file.read_text(encoding="utf-8")

        last_error: FetchError | None = None
        for attempt in range(self.max_retries):
            try:
                with self._request_lock:
                    response = self.session.get(url, timeout=60)
                    if self.request_delay > 0:
                        time.sleep(self.request_delay)
            except requests.RequestException as exc:
                last_error = FetchError(f"Request failed for {url}: {exc}")
                time.sleep(min(2**attempt, 30))
                continue

            if response.status_code == 200:
                text = response.text
                cache_file.write_text(text, encoding="utf-8")
                return text

            if response.status_code in RETRYABLE_STATUS_CODES:
                retry_after = _retry_after_seconds(response)
                wait = retry_after if retry_after is not None else min(2**attempt + 1, 60)
                last_error = FetchError(f"HTTP {response.status_code} for {url}")
                print(
                    f"\n  限流 HTTP {response.status_code}，{wait:.1f}s 后重试 "
                    f"({attempt + 1}/{self.max_retries})...",
                    flush=True,
                )
                time.sleep(wait)
                continue

            raise FetchError(f"HTTP {response.status_code} for {url}")

        if last_error is not None:
            raise last_error
        raise FetchError(f"Failed after {self.max_retries} retries for {url}")

    def list_versions(self) -> list[str]:
        cache_file = self.cache_dir / "versions.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))

        try:
            js = self.fetch_text(VERSIONS_INFO_URL)
            versions = parse_versions_info(js)
        except (FetchError, requests.RequestException):
            versions = DEFAULT_VERSIONS

        if not versions:
            versions = DEFAULT_VERSIONS

        cache_file.write_text(json.dumps(versions, indent=2), encoding="utf-8")
        return versions

    def fetch_snapshot(self, version: str, use_cache: bool = True) -> ApiSnapshot:
        unity = UnityVersion.parse(version)
        toc_js = self.fetch_text(unity.toc_url(), use_cache=use_cache)
        snapshot = parse_toc_js(toc_js, version)

        meta_file = self.cache_dir / f"toc_{version.replace('.', '_')}.json"
        if use_cache and meta_file.exists():
            cached = json.loads(meta_file.read_text(encoding="utf-8"))
            if cached.get("count") == len(snapshot.entries):
                return snapshot

        meta_file.write_text(
            json.dumps({"version": version, "count": len(snapshot.entries)}, indent=2),
            encoding="utf-8",
        )
        return snapshot

    def fetch_class_members(
        self,
        version: str,
        type_links: list[str],
        use_cache: bool = True,
        on_progress: Callable | None = None,
    ) -> dict[str, set[str]]:
        unity = UnityVersion.parse(version)
        results: dict[str, set[str]] = {}

        def fetch_one(link: str) -> tuple[str, set[str]]:
            url = unity.page_url(link)
            html = self.fetch_text(url, use_cache=use_cache)
            return link, extract_class_members(html, link)

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(fetch_one, link): link for link in type_links}
            done = 0
            total = len(type_links)
            for future in as_completed(futures):
                link, members = future.result()
                results[link] = members
                done += 1
                if on_progress:
                    on_progress(done, total, link)

        return results

    def fetch_member_signatures(
        self,
        version: str,
        member_links: list[str],
        use_cache: bool = True,
        on_progress: Callable | None = None,
    ) -> dict[str, list[str]]:
        unity = UnityVersion.parse(version)
        results: dict[str, list[str]] = {}

        def fetch_one(link: str) -> tuple[str, list[str]]:
            url = unity.page_url(link)
            html = self.fetch_text(url, use_cache=use_cache)
            return link, extract_signatures(html)

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(fetch_one, link): link for link in member_links}
            done = 0
            total = len(member_links)
            for future in as_completed(futures):
                link, signatures = future.result()
                results[link] = signatures
                done += 1
                if on_progress:
                    on_progress(done, total, link)

        return results
