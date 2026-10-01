"""Lightweight, in-memory metrics counters (CP46).

Provides a simple registry of counters and gauges that can be inspected
by health endpoints or tests.  No external metrics backend dependency is
required for Phase 1 — operators can add Prometheus scraping later by
reading the registry.

All metrics are privacy-safe: they carry IDs, stage names, status, and
timing — never document content.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class Counter:
    """A monotonically increasing counter."""

    name: str
    help: str
    labels: dict[str, str]
    value: int = 0

    def inc(self, by: int = 1) -> None:
        self.value += by


@dataclass
class Gauge:
    """A value that can go up or down."""

    name: str
    help: str
    labels: dict[str, str]
    value: float = 0.0

    def set(self, value: float) -> None:
        self.value = value

    def inc(self, by: float = 1.0) -> None:
        self.value += by

    def dec(self, by: float = 1.0) -> None:
        self.value -= by


@dataclass
class Histogram:
    """A simple histogram tracking count, total, and min/max."""

    name: str
    help: str
    labels: dict[str, str]
    count: int = 0
    total_seconds: float = 0.0
    min_seconds: float = 0.0
    max_seconds: float = 0.0

    def observe(self, seconds: float) -> None:
        self.count += 1
        self.total_seconds += seconds
        if self.count == 1:
            self.min_seconds = seconds
        else:
            self.min_seconds = min(self.min_seconds, seconds)
        self.max_seconds = max(self.max_seconds, seconds)

    @property
    def avg_seconds(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_seconds / self.count


_METRICS: dict[tuple[str, tuple[tuple[str, str], ...]], Counter] = {}
_GAUGES: dict[tuple[str, tuple[tuple[str, str], ...]], Gauge] = {}
_HISTOGRAMS: dict[tuple[str, tuple[tuple[str, str], ...]], Histogram] = {}
_lock = threading.Lock()


def _label_key(
    name: str, labels: dict[str, str]
) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (name, tuple(sorted(labels.items())))


class MetricsRegistry:
    """Thread-safe registry of counters, gauges, and histograms.

    Use :func:`get_metrics()` to access the singleton.
    """

    def counter(
        self, name: str, help: str, *, labels: dict[str, str] | None = None
    ) -> Counter:
        labels = labels or {}
        key = _label_key(name, labels)
        with _lock:
            if key not in _METRICS:
                _METRICS[key] = Counter(name, help, labels)
            return _METRICS[key]

    def gauge(
        self, name: str, help: str, *, labels: dict[str, str] | None = None
    ) -> Gauge:
        labels = labels or {}
        key = (name, tuple(sorted(labels.items())))
        with _lock:
            if key not in _GAUGES:
                _GAUGES[key] = Gauge(name, help, labels)
            return _GAUGES[key]

    def histogram(
        self, name: str, help: str, *, labels: dict[str, str] | None = None
    ) -> Histogram:
        labels = labels or {}
        key = (name, tuple(sorted(labels.items())))
        with _lock:
            if key not in _HISTOGRAMS:
                _HISTOGRAMS[key] = Histogram(name, help, labels)
            return _HISTOGRAMS[key]

    def snapshot(self) -> dict[str, list[dict[str, object]]]:
        """Return a point-in-time snapshot of all metrics."""
        with _lock:
            return {
                "counters": [
                    {
                        "name": c.name,
                        "help": c.help,
                        "labels": dict(c.labels),
                        "value": c.value,
                    }
                    for c in _METRICS.values()
                ],
                "gauges": [
                    {
                        "name": g.name,
                        "help": g.help,
                        "labels": dict(g.labels),
                        "value": g.value,
                    }
                    for g in _GAUGES.values()
                ],
                "histograms": [
                    {
                        "name": h.name,
                        "help": h.help,
                        "labels": dict(h.labels),
                        "count": h.count,
                        "total_seconds": h.total_seconds,
                        "avg_seconds": h.avg_seconds,
                        "min_seconds": h.min_seconds,
                        "max_seconds": h.max_seconds,
                    }
                    for h in _HISTOGRAMS.values()
                ],
            }


_instance: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    """Return the singleton :class:`MetricsRegistry`."""
    global _instance
    if _instance is None:
        _instance = MetricsRegistry()
    return _instance


# ---------------------------------------------------------------------------
# Convenience metric accessors (Phase 1 categories)
# ---------------------------------------------------------------------------

def _m() -> MetricsRegistry:
    return get_metrics()


def metrics_queue_depth() -> Gauge:
    """Gauge for pending jobs in the document-processing queue."""
    return _m().gauge(
        "queue_depth",
        "Number of pending jobs in the document-processing queue",
    )


def metrics_job_failures() -> Counter:
    """Counter for failed processing jobs."""
    return _m().counter(
        "job_failures_total",
        "Total number of failed document processing jobs",
    )


def metrics_job_latency() -> Histogram:
    """Histogram for document processing job latency."""
    return _m().histogram(
        "job_latency_seconds",
        "Duration of document processing jobs in seconds",
    )


def metrics_extraction_failures() -> Counter:
    """Counter for LLM extraction failures."""
    return _m().counter(
        "extraction_failures_total",
        "Total number of failed LLM extraction calls",
    )


def metrics_ocr_failures() -> Counter:
    """Counter for OCR failures."""
    return _m().counter(
        "ocr_failures_total",
        "Total number of failed OCR operations",
    )


def metrics_retention_deleted() -> Counter:
    """Counter for objects deleted by the retention policy."""
    return _m().counter(
        "retention_deleted_total",
        "Total number of objects deleted by retention cleanup",
    )


class Timer:
    """Context manager that records elapsed time to a histogram."""

    def __init__(self, histogram: Histogram) -> None:
        self._histogram = histogram
        self._start = 0.0

    def __enter__(self) -> Timer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc: object) -> None:
        elapsed = time.monotonic() - self._start
        self._histogram.observe(elapsed)
