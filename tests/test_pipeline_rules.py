import hashlib
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from app import db
from app.config import Settings
from app.oko.pipeline.analyzer import _select
from app.oko.pipeline.detectors.base import Candidate
from app.oko.rules.catalog import RULES
from app.worker import process_integrated_job


def configuration(folder, **overrides):
    options = dict(data_dir=folder, rules_path=Path(__file__).parents[1] / "rules.json",
                   api_key="test-only-key-not-a-production-secret", max_upload_bytes=1_000_000,
                   max_video_seconds=10, model_timeout_seconds=1, retention_hours=24,
                   worker_concurrency=1, model_command=(), ffmpeg="ffmpeg", ffprobe="ffprobe")
    options.update(overrides)
    return Settings(**options)


def test_confidence_boundary_and_unverified_rules_never_become_reported(tmp_path):
    assert len(RULES) == 21
    config = configuration(tmp_path).pipeline_settings()
    candidates = [Candidate(rule_id="V03", t_start=1, confidence=.29),
                  Candidate(rule_id="V03", t_start=2, confidence=.3),
                  Candidate(rule_id="V03", t_start=3, confidence=.5),
                  Candidate(rule_id="V18", t_start=4, confidence=.99),
                  Candidate(rule_id="X00", t_start=5, confidence=.99)]
    reported, review = _select(candidates, config)
    assert [(item.rule.id, item.timecode) for item in reported] == [("V03", 3)]
    assert [(item.rule.id, item.timecode) for item in review] == [("V03", 2), ("V18", 4), ("X00", 5)]


def test_real_team_process_timeout_is_failed_and_child_has_no_api_key(tmp_path, monkeypatch):
    db.init(tmp_path)
    video = tmp_path / "intake.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 12, (160, 96))
    assert writer.isOpened()
    rng = np.random.default_rng(19)
    frame = rng.integers(0, 255, (96, 160, 3), dtype=np.uint8)
    for _ in range(24):
        writer.write(frame)
    writer.release()
    model = tmp_path / "slow_model.py"
    model.write_text("import os,sys,time,json\nassert 'API_KEY' not in os.environ\njson.load(sys.stdin)\ntime.sleep(8)\n", encoding="utf-8")
    monkeypatch.setenv("API_KEY", "isolated-test-secret-must-not-reach-model")
    config = configuration(tmp_path, model_command=(sys.executable, str(model)), enable_team_model=True)
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    job_id = db.create_run(tmp_path, video, "intake.mp4", "video/mp4", digest, "timeout-run", digest,
                           config_snapshot={"detectors": ["obstruction", "team"]})["job_id"]
    started = time.monotonic()
    process_integrated_job(db.claim_next(tmp_path), config)
    run = db.get_run(tmp_path, job_id)
    assert run["status"] == "failed"
    assert run["api_result"] is None
    assert "лимит времени" in run["error"]
    assert time.monotonic() - started < 8


def test_detector_failure_cannot_be_reported_as_a_clean_video(tmp_path, monkeypatch):
    from app.oko.pipeline.analyzer import analyze
    from app.oko.pipeline.detectors.obstruction import ObstructionDetector

    video = tmp_path / "detector-failure.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 12, (160, 96))
    assert writer.isOpened()
    frame = np.random.default_rng(3).integers(0, 255, (96, 160, 3), dtype=np.uint8)
    for _ in range(12):
        writer.write(frame)
    writer.release()

    def broken_end(self, ctx):
        raise RuntimeError("isolated detector failure")

    monkeypatch.setattr(ObstructionDetector, "end", broken_end)
    with pytest.raises(ValueError, match="Нет работающих детекторов"):
        analyze(video, configuration(tmp_path).pipeline_settings(), time.monotonic() + 20)
