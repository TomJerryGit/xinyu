# -*- coding: utf-8 -*-
"""作业系统测试：完成、失败、取消。"""
import time

from jobs import JobManager


def wait_job(manager, job_id, statuses, timeout=6):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = manager.get(job_id)
        if job and job["status"] in statuses:
            return job
        time.sleep(0.05)
    return manager.get(job_id)


def test_job_completes(tmp_path):
    def handler(payload, progress, cancelled):
        progress(30, "处理中")
        time.sleep(0.05)
        progress(100, "完成")
        return {"echo": payload.get("value")}

    manager = JobManager(str(tmp_path / "jobs.db"), {"echo": handler}, max_workers=1)
    try:
        job_id = manager.submit("echo", {"value": 42})
        job = wait_job(manager, job_id, {"done", "failed", "cancelled"})
        assert job["status"] == "done"
        assert job["result"] == {"echo": 42}
        assert job["progress"] == 100
    finally:
        manager.shutdown()


def test_job_failure_is_recorded(tmp_path):
    def handler(payload, progress, cancelled):
        raise RuntimeError("boom")

    manager = JobManager(str(tmp_path / "jobs.db"), {"bad": handler}, max_workers=1)
    try:
        job_id = manager.submit("bad", {})
        job = wait_job(manager, job_id, {"failed"})
        assert job["status"] == "failed"
        assert "boom" in job["error"]
    finally:
        manager.shutdown()


def test_job_cancel(tmp_path):
    def handler(payload, progress, cancelled):
        for index in range(100):
            if cancelled():
                raise RuntimeError("cancelled")
            progress(index, "loop")
            time.sleep(0.03)
        return {"finished": True}

    manager = JobManager(str(tmp_path / "jobs.db"), {"loop": handler}, max_workers=1)
    try:
        job_id = manager.submit("loop", {})
        deadline = time.time() + 3
        while time.time() < deadline:
            job = manager.get(job_id)
            if job and job["status"] == "running":
                break
            time.sleep(0.03)
        assert manager.cancel(job_id) is True
        job = wait_job(manager, job_id, {"cancelled", "done", "failed"})
        assert job["status"] == "cancelled"
    finally:
        manager.shutdown()


def test_job_retry(tmp_path):
    attempts = {"count": 0}

    def handler(payload, progress, cancelled):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("first failure")
        return {"attempt": attempts["count"]}

    manager = JobManager(str(tmp_path / "jobs.db"), {"retry": handler}, max_workers=1)
    try:
        job_id = manager.submit("retry", {})
        failed = wait_job(manager, job_id, {"failed"})
        assert failed["status"] == "failed"
        assert manager.retry(job_id) is True
        done = wait_job(manager, job_id, {"done", "failed"})
        assert done["status"] == "done"
        assert done["result"] == {"attempt": 2}
    finally:
        manager.shutdown()


def test_job_checkpoint_survives_retry(tmp_path):
    def handler(payload, progress, cancelled):
        saved = progress.get_checkpoint()
        if not saved:
            progress.checkpoint({"stage": "half", "items": [1, 2]})
            progress(40, "half")
            raise RuntimeError("simulated crash")
        return saved

    manager = JobManager(str(tmp_path / "jobs.db"), {"resume": handler}, max_workers=1)
    try:
        job_id = manager.submit("resume", {})
        failed = wait_job(manager, job_id, {"failed"})
        assert failed["status"] == "failed"
        assert failed["has_checkpoint"] is True
        assert manager.get_checkpoint(job_id)["stage"] == "half"
        assert manager.retry(job_id) is True
        done = wait_job(manager, job_id, {"done"})
        assert done["status"] == "done"
        assert done["result"]["items"] == [1, 2]
    finally:
        manager.shutdown()


def test_job_rejects_unknown_kind(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"), {}, max_workers=1)
    try:
        try:
            manager.submit("nope", {})
            assert False, "should raise"
        except ValueError:
            pass
    finally:
        manager.shutdown()


def test_metrics_summary(tmp_path, monkeypatch):
    import metrics

    monkeypatch.setattr(metrics, "_path", lambda: str(tmp_path / "metrics.jsonl"))
    metrics.record("startup", total_ms=1234, frozen=False)
    metrics.record("ai_call", task="generate", success=True, latency_ms=800, tokens=100, cost=0.002)
    metrics.record("ai_call", task="generate", success=False, latency_ms=400, tokens=50, cost=0.001)
    metrics.record("job", kind="teaching", status="done", duration_ms=2000)
    summary = metrics.summary(7)
    assert summary["startups"]["last_ms"] == 1234
    assert summary["ai"]["calls"] == 2
    assert summary["ai"]["success_rate"] == 50.0
    assert summary["jobs"]["status"]["done"] == 1
