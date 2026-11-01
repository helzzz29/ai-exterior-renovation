"""Per-job memory logging: numbers on Linux, silent elsewhere, never raises."""

import sys
from types import SimpleNamespace

from renocore.background import handlers as tasks
from renocore.operations import telemetry as observability


def test_memory_mb_reads_proc_and_getrusage(tmp_path, monkeypatch) -> None:
    statm = tmp_path / "statm"
    statm.write_text("5000 256 100 1 0 300 0\n")
    monkeypatch.setattr(observability, "_STATM", statm)
    monkeypatch.setattr(observability.os, "sysconf", lambda _name: 4096, raising=False)
    fake_resource = SimpleNamespace(
        RUSAGE_SELF=0, getrusage=lambda _who: SimpleNamespace(ru_maxrss=204800)
    )
    monkeypatch.setitem(sys.modules, "resource", fake_resource)
    assert observability.memory_mb() == (1.0, 200.0)  # 256 pages x 4 KB; 204800 KB peak


def test_memory_mb_unsupported_platform(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(observability, "_STATM", tmp_path / "missing")
    assert observability.memory_mb() == (None, None)


class RecordingLog:
    def __init__(self) -> None:
        self.lines: list[tuple[str, dict]] = []

    def info(self, event: str, **fields) -> None:
        self.lines.append((event, fields))


def test_log_memory_logs_when_available(monkeypatch) -> None:
    recorder = RecordingLog()
    monkeypatch.setattr(tasks, "log", recorder)
    monkeypatch.setattr(tasks, "memory_mb", lambda: (180.5, 240.0))
    tasks.log_memory("render", "end")
    assert recorder.lines == [
        ("job_memory", {"kind": "render", "at": "end", "rss_mb": 180.5, "peak_mb": 240.0})
    ]


def test_log_memory_silent_when_unavailable(monkeypatch) -> None:
    recorder = RecordingLog()
    monkeypatch.setattr(tasks, "log", recorder)
    monkeypatch.setattr(tasks, "memory_mb", lambda: (None, None))
    tasks.log_memory("render", "start")
    assert recorder.lines == []
