"""Subprocess runner: no shell, independent process tree, timeout and cancellation.

Isolation: Windows uses a Job Object (KILL_ON_JOB_CLOSE) so that a timeout, a cancel or
a supervisor crash terminates grandchildren too; POSIX uses a new session + killpg.  If
isolation cannot be established the run is refused (IsolationError), never degraded.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

POLL = 0.05


class IsolationError(RuntimeError):
    pass


class ProcessCleanupError(RuntimeError):
    """The child may still be alive (kill/wait failed); carries the PID so the engine can record it."""

    def __init__(self, pid: int | None, problems: list[str]) -> None:
        super().__init__(f"process_unkillable pid={pid}: " + "; ".join(problems))
        self.pid, self.problems = pid, problems


@dataclass(frozen=True)
class ProcessSpec:
    argv: list[str]
    cwd: str
    env: dict[str, str]
    stdin_text: str | None
    timeout_seconds: float
    max_output_bytes: int


@dataclass
class ProcessOutcome:
    pid: int | None = None
    exit_code: int | None = None
    timed_out: bool = False
    cancelled: bool = False
    duration_seconds: float = 0.0
    stdout: bytes = b""
    stderr: bytes = b""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    isolation: str = "none"
    error: str | None = None
    extra: dict = field(default_factory=dict)


class Runner(Protocol):
    def run(self, spec: ProcessSpec, cancel: Callable[[], bool], on_start: Callable[[int], None]) -> ProcessOutcome: ...


class _WindowsJob:
    """Minimal Job Object wrapper (ctypes); one job per child process."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ct = ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.k32 = k32

        class IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("a", "b", "c", "d", "e", "f")]

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self.handle = k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise IsolationError("CreateJobObject falhou")
        info = Extended()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise IsolationError("SetInformationJobObject falhou")

    def assign(self, proc: subprocess.Popen) -> None:
        if not self.k32.AssignProcessToJobObject(self.handle, int(proc._handle)):  # type: ignore[attr-defined]
            raise IsolationError("AssignProcessToJobObject falhou")

    def terminate(self) -> None:
        if self.handle:
            self.k32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if self.handle:
            self.k32.CloseHandle(self.handle)
            self.handle = None


def _pump(stream, limit: int, sink: bytearray, flag: list) -> None:
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                return
            room = limit - len(sink)
            if room > 0:
                sink += chunk[:room]
            if len(chunk) > max(room, 0):
                flag[0] = True  # keep draining so the child never blocks on a full pipe
    except (OSError, ValueError):
        return


def _feed(stream, text: str | None) -> None:
    try:
        if text:
            stream.write(text.encode("utf-8"))
        stream.close()
    except (OSError, ValueError):
        pass  # child exited or closed stdin early


class ProcessRunner:
    def run(self, spec: ProcessSpec, cancel: Callable[[], bool] = lambda: False, on_start: Callable[[int], None] = lambda pid: None) -> ProcessOutcome:
        outcome = ProcessOutcome()
        job = None
        popen_kwargs: dict = {}
        if os.name == "nt":
            job = _WindowsJob()
            popen_kwargs["creationflags"] = 0x00000200 | 0x08000000  # NEW_PROCESS_GROUP | NO_WINDOW
            outcome.isolation = "job_object"
        else:
            popen_kwargs["start_new_session"] = True
            outcome.isolation = "process_group"
        started = time.monotonic()
        try:
            proc = subprocess.Popen(spec.argv, cwd=spec.cwd, env=spec.env, shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_kwargs)
        except OSError as exc:
            if job:
                job.close()
            outcome.error = f"spawn_failed: {exc.__class__.__name__}: {exc}"
            return outcome
        out, err = bytearray(), bytearray()
        flags = ([False], [False])
        threads: list[threading.Thread] = []
        assigned = False
        try:
            # Everything after Popen lives in this try: any failure (isolation, on_start
            # persistence, KeyboardInterrupt) must still terminate the tree and free handles.
            if job:
                job.assign(proc)
                assigned = True
            outcome.pid = proc.pid
            on_start(proc.pid)
            threads = [
                threading.Thread(target=_pump, args=(proc.stdout, spec.max_output_bytes, out, flags[0]), daemon=True),
                threading.Thread(target=_pump, args=(proc.stderr, spec.max_output_bytes, err, flags[1]), daemon=True),
                threading.Thread(target=_feed, args=(proc.stdin, spec.stdin_text), daemon=True),
            ]
            for thread in threads:
                thread.start()
            while proc.poll() is None:
                if cancel():
                    outcome.cancelled = True
                    break
                if time.monotonic() - started > spec.timeout_seconds:
                    outcome.timed_out = True
                    break
                time.sleep(POLL)
        finally:
            # Each cleanup step is independent: a failure in one never skips the others, and
            # any failure is reported (with the PID) even when another exception is in flight.
            problems: list[str] = []
            try:
                abnormal = proc.poll() is None  # still alive: cancel, timeout or an exception above
                self._kill(proc, job if assigned else None, leftovers_only=not abnormal, force_proc=abnormal or not assigned)
            except Exception as exc:  # noqa: BLE001 - must continue cleanup
                problems.append(f"kill falhou: {exc.__class__.__name__}: {exc}")
            try:
                proc.wait(timeout=10)  # bounded: never hang on a child that survived the kill
            except subprocess.TimeoutExpired:
                problems.append("o processo não encerrou em 10 s após kill")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"wait falhou: {exc.__class__.__name__}: {exc}")
            for thread in threads:
                thread.join(timeout=5)
            for stream in (proc.stdout, proc.stderr, proc.stdin):
                try:
                    if stream:
                        stream.close()
                except (OSError, ValueError):
                    pass
            try:
                if job:
                    job.close()
            except Exception as exc:  # noqa: BLE001
                problems.append(f"fechar Job falhou: {exc.__class__.__name__}: {exc}")
            if problems:
                raise ProcessCleanupError(proc.pid, problems)
        outcome.exit_code = proc.returncode
        outcome.duration_seconds = round(time.monotonic() - started, 3)
        outcome.stdout, outcome.stderr = bytes(out), bytes(err)
        outcome.stdout_truncated, outcome.stderr_truncated = flags[0][0], flags[1][0]
        return outcome

    @staticmethod
    def _kill(proc: subprocess.Popen, job, leftovers_only: bool = False, force_proc: bool = False) -> None:
        """Terminate the whole tree.  After a clean exit this only reaps orphaned descendants.

        `job` is passed only once the child really belongs to it; an unassigned child is
        killed directly so a failed assignment cannot leave it running.
        """
        if job is not None:
            job.terminate()
            if force_proc and proc.poll() is None:
                proc.kill()
            return
        if os.name == "nt":
            if force_proc and proc.poll() is None:
                proc.kill()
            return
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        except OSError:
            if not leftovers_only:
                proc.kill()
