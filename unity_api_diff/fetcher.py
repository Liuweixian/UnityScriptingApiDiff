"""Download and cache Unity documentation data."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, TypeVar

import requests

from .parser import ApiSnapshot, extract_class_members, extract_signatures, parse_toc_js
from .paths import TMP_DIR
from .progress import ProgressTracker
from .versions import VERSIONS_INFO_URL, DEFAULT_VERSIONS, UnityVersion, parse_versions_info

T = TypeVar("T")

DEFAULT_CACHE_DIR = TMP_DIR
USER_AGENT = "UnityScriptingApiDiff/0.1 (+https://github.com/)"
DEFAULT_WORKERS = 8
DEFAULT_REQUEST_DELAY = 0.12
DEFAULT_MAX_RETRIES = 6
RETRYABLE_STATUS_CODES = {429, 503}


class FetchError(RuntimeError):
    pass


@dataclass
class _InFlight:
    event: threading.Event
    text: str | None = None
    error: BaseException | None = None


class _RateLimiter:
    """Space out request starts while allowing multiple in-flight downloads."""

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def wait_turn(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next_slot)
            self._next_slot = scheduled + self._min_interval
        delay = scheduled - now
        if delay > 0:
            time.sleep(delay)


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
        self.workers = max(1, workers)
        self.request_delay = request_delay
        self.max_retries = max_retries
        self._rate_limiter = _RateLimiter(request_delay)
        self._thread_local = threading.local()
        self._in_flight: dict[str, _InFlight] = {}
        self._in_flight_lock = threading.Lock()

    def _cache_path(self, key: str, suffix: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{digest}{suffix}"

    def _write_cache(self, cache_file: Path, text: str) -> None:
        tmp = cache_file.with_suffix(cache_file.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(cache_file)

    def _read_cache(self, cache_file: Path) -> str | None:
        if not cache_file.exists():
            return None
        try:
            return cache_file.read_text(encoding="utf-8")
        except OSError:
            return None

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers["User-Agent"] = USER_AGENT
            self._thread_local.session = session
        return session

    def fetch_text(self, url: str, use_cache: bool = True) -> str:
        cache_file = self._cache_path(url, ".txt")
        if use_cache:
            cached = self._read_cache(cache_file)
            if cached is not None:
                return cached

        owner = False
        flight: _InFlight | None = None
        with self._in_flight_lock:
            flight = self._in_flight.get(url)
            if flight is None:
                flight = _InFlight(event=threading.Event())
                self._in_flight[url] = flight
                owner = True

        if not owner:
            assert flight is not None
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            if flight.text is not None:
                return flight.text
            cached = self._read_cache(cache_file)
            if cached is not None:
                return cached
            raise FetchError(f"In-flight fetch failed without result for {url}")

        assert flight is not None
        try:
            text = self._fetch_text_network(url, cache_file)
            flight.text = text
            return text
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            flight.event.set()
            with self._in_flight_lock:
                self._in_flight.pop(url, None)

    def _fetch_text_network(self, url: str, cache_file: Path) -> str:
        last_error: FetchError | None = None
        for attempt in range(self.max_retries):
            try:
                self._rate_limiter.wait_turn()
                response = self._session().get(url, timeout=60)
            except requests.RequestException as exc:
                last_error = FetchError(f"Request failed for {url}: {exc}")
                time.sleep(min(2**attempt, 30))
                continue

            if response.status_code == 200:
                text = response.text
                self._write_cache(cache_file, text)
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

    def _fetch_jobs(
        self,
        jobs: list[tuple[str, str]],
        extract: Callable[[str, str], T],
        use_cache: bool = True,
        progress: ProgressTracker | None = None,
    ) -> dict[tuple[str, str], T]:
        """Fetch pages for (version, link) jobs with cache pre-scan and deduplicated downloads."""
        version_cache: dict[str, UnityVersion] = {}
        results: dict[tuple[str, str], T] = {}
        pending: list[tuple[str, str, str]] = []

        for version, link in jobs:
            if version not in version_cache:
                version_cache[version] = UnityVersion.parse(version)
            url = version_cache[version].page_url(link)
            cache_file = self._cache_path(url, ".txt")
            if use_cache:
                cached_html = self._read_cache(cache_file)
                if cached_html is not None:
                    results[(version, link)] = extract(cached_html, link)
                    continue
            pending.append((version, link, url))

        if progress:
            progress.begin(cached=len(results), network_total=len(pending))

        def fetch_one(version: str, link: str, url: str) -> tuple[str, str, T]:
            html = self.fetch_text(url, use_cache=use_cache)
            return version, link, extract(html, link)

        if not pending:
            return results

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = [
                executor.submit(fetch_one, version, link, url)
                for version, link, url in pending
            ]
            for future in as_completed(futures):
                version, link, value = future.result()
                results[(version, link)] = value
                if progress:
                    progress.step(f"{version} {link}")

        return results

    def fetch_class_members(
        self,
        version: str,
        type_links: list[str],
        use_cache: bool = True,
        progress: ProgressTracker | None = None,
    ) -> dict[str, set[str]]:
        jobs = [(version, link) for link in type_links]
        raw = self._fetch_jobs(jobs, extract_class_members, use_cache=use_cache, progress=progress)
        return {link: raw[(version, link)] for link in type_links}

    def fetch_class_members_batch(
        self,
        jobs: list[tuple[str, str]],
        use_cache: bool = True,
        progress: ProgressTracker | None = None,
    ) -> dict[tuple[str, str], set[str]]:
        return self._fetch_jobs(jobs, extract_class_members, use_cache=use_cache, progress=progress)

    def fetch_member_signatures(
        self,
        version: str,
        member_links: list[str],
        use_cache: bool = True,
        progress: ProgressTracker | None = None,
    ) -> dict[str, list[str]]:
        jobs = [(version, link) for link in member_links]

        def extract_sigs(html: str, _link: str) -> list[str]:
            return extract_signatures(html)

        raw = self._fetch_jobs(jobs, extract_sigs, use_cache=use_cache, progress=progress)
        return {link: raw[(version, link)] for link in member_links}

    def fetch_member_signatures_batch(
        self,
        jobs: list[tuple[str, str]],
        use_cache: bool = True,
        progress: ProgressTracker | None = None,
    ) -> dict[tuple[str, str], list[str]]:
        def extract_sigs(html: str, _link: str) -> list[str]:
            return extract_signatures(html)

        return self._fetch_jobs(jobs, extract_sigs, use_cache=use_cache, progress=progress)
