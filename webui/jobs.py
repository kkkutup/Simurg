"""Background job runner — launches render / fetch / export subprocesses and tracks
their progress + log so the web UI can poll them. In-memory (fine for a local tool).
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from collections import deque

_PROGRESS_RE = re.compile(r"rendered (\d+)/(\d+)")


class Job:
    def __init__(self, jid: str, cmd: list[str], cwd: str, kind: str, output: str | None):
        self.id = jid
        self.cmd = cmd
        self.cwd = cwd
        self.kind = kind          # "render" | "fetch" | "export"
        self.output = output
        self.status = "running"   # running | done | failed | stopped
        self.rendered = 0
        self.total = 0
        self.progress = 0
        self.log: deque[str] = deque(maxlen=500)
        self.proc: subprocess.Popen | None = None
        self.started = time.time()
        self.ended: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "rendered": self.rendered,
            "total": self.total,
            "output": self.output,
            "cmd": " ".join(self.cmd),
            "elapsed": round((self.ended or time.time()) - self.started, 1),
            "log": list(self.log)[-40:],
        }


class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def start(self, cmd: list[str], cwd: str, kind: str = "render",
              total: int = 0, output: str | None = None) -> str:
        with self._lock:
            self._counter += 1
            jid = str(self._counter)
        job = Job(jid, cmd, cwd, kind, output)
        job.total = total
        self.jobs[jid] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return jid

    def _run(self, job: Job) -> None:
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            job.proc = subprocess.Popen(
                job.cmd, cwd=job.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, creationflags=flags,
            )
            for line in job.proc.stdout:  # type: ignore[union-attr]
                line = line.rstrip("\n")
                if not line:
                    continue
                job.log.append(line)
                m = _PROGRESS_RE.search(line)
                if m:
                    job.rendered, job.total = int(m.group(1)), int(m.group(2))
                    if job.total:
                        job.progress = int(100 * job.rendered / job.total)
            job.proc.wait()
            job.status = "done" if job.proc.returncode == 0 else "failed"
        except Exception as e:  # noqa: BLE001
            job.log.append(f"[runner error] {e}")
            job.status = "failed"
        finally:
            job.ended = time.time()
            if job.status == "done":
                job.progress = 100

    def stop(self, jid: str) -> bool:
        job = self.jobs.get(jid)
        if not job or not job.proc or job.status != "running":
            return False
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(job.proc.pid)],
                               capture_output=True)
            else:
                job.proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        job.status = "stopped"
        job.ended = time.time()
        return True

    def list(self) -> list[dict]:
        return [j.to_dict() for j in sorted(self.jobs.values(),
                                            key=lambda x: -x.started)]

    def get(self, jid: str) -> dict | None:
        j = self.jobs.get(jid)
        return j.to_dict() if j else None

    def active(self) -> dict | None:
        for j in sorted(self.jobs.values(), key=lambda x: -x.started):
            if j.status == "running":
                return j.to_dict()
        return None
