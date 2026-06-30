"""Thread-safe CLI progress reporting."""

from __future__ import annotations

import sys
import threading


class ProgressTracker:
    def __init__(self, phase: str) -> None:
        self.phase = phase
        self._lock = threading.Lock()
        self._cached = 0
        self._network_done = 0
        self._network_total = 0
        self._last_label = ""

    def begin(self, cached: int, network_total: int) -> None:
        with self._lock:
            self._cached = cached
            self._network_done = 0
            self._network_total = network_total
            self._last_label = ""
            total = cached + network_total
            if network_total == 0:
                print(f"  {self.phase}: 全部 {cached} 项来自缓存", flush=True)
            else:
                print(
                    f"  {self.phase}: 缓存 {cached}/{total}，"
                    f"待下载 {network_total}",
                    flush=True,
                )

    def step(self, label: str, *, from_cache: bool = False) -> None:
        with self._lock:
            if from_cache:
                return
            self._network_done += 1
            self._last_label = label
            done = self._cached + self._network_done
            total = self._cached + self._network_total
            pct = (done / total * 100) if total else 100.0
            line = (
                f"\r  [{done}/{total}] {pct:5.1f}%  "
                f"(网络 {self._network_done}/{self._network_total})  "
                f"{label[:50]:<50}"
            )
            sys.stdout.write(line)
            sys.stdout.flush()
            if self._network_done == self._network_total:
                sys.stdout.write("\n")
                sys.stdout.flush()
