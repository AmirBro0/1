import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import claim_next, create_job, finish, get_job, init
from app.model import ModelError, load_rules, run_model
from app.worker import process_job


KEY = "test-secret-key-longer-than-24-chars"
RULES = Path(__file__).resolve().parents[1] / "rules.json"


def settings(tmp_path, model_command=()):
    return Settings(tmp_path, RULES, KEY, 1000, 180, 10, 24, 1, tuple(model_command), "ffmpeg", "ffprobe")


def test_api_upload_auth_and_status(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    from app import api
    monkeypatch.setattr(api, "settings", settings(tmp_path))
    with TestClient(api.app) as client:
        assert client.get('/api/v1/capabilities').status_code == 401
        assert client.get('/api/v1/capabilities', headers=[(b'X-API-Key', b'\xff')]).status_code == 401
        capabilities = client.get('/api/v1/capabilities', headers={'X-API-Key': KEY})
        assert capabilities.json()['max_upload_bytes'] == 1000
        assert client.get('/static/styles.css').status_code == 200
        assert client.get('/static/config.js').status_code == 200
        payload = b"\x00\x00\x00\x18ftypqt  " + b"0" * 20
        denied = client.post("/api/v1/analyze", files={"file": ("clip.mov", payload)})
        assert denied.status_code == 401
        invalid = client.post("/api/v1/analyze", headers={"X-API-Key": KEY},
                              files={"file": ("clip.txt", payload)})
        assert invalid.status_code == 415
        too_big = client.post("/api/v1/analyze", headers={"X-API-Key": KEY},
                              files={"file": ("clip.mov", payload * 100)})
        assert too_big.status_code == 413
        response = client.post("/api/v1/analyze", headers={"X-API-Key": KEY},
                               files={"file": ("clip.mov", payload)})
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        status = client.get(f"/api/v1/jobs/{job_id}", headers={"X-API-Key": KEY})
        assert status.json() == {"job_id": job_id, "status": "processing", "verdict": None, "violations": []}
        assert get_job(tmp_path, job_id)["status"] == "queued"
        result = {"job_id": job_id, "status": "done", "verdict": "no_violation", "violations": []}
        finish(tmp_path, job_id, result)
        assert client.get(f"/api/v1/jobs/{job_id}", headers={"X-API-Key": KEY}).json() == result


def test_model_contract_accepts_known_event_and_rejects_unknown(tmp_path):
    script = tmp_path / "infer.py"
    script.write_text("import json,sys\nrequest=json.load(sys.stdin)\nprint(json.dumps({'schema_version':1,'events':[{'event_type':'cash_disbursement_no_visible_recount','timestamp_sec':2.0,'observation':'Выдача без пересчёта.','evidence_timestamps_sec':[2.0]}]}))\n", encoding="utf-8")
    config = settings(tmp_path, (sys.executable, str(script)))
    events = run_model(tmp_path / "clip.mov", 4.0, config, load_rules(RULES), time.monotonic() + 10)
    assert events[0]["event_type"] == "cash_disbursement_no_visible_recount"
    script.write_text("import json\nprint(json.dumps({'schema_version':1,'events':[{'event_type':'invented','timestamp_sec':2,'observation':'x'}]}))\n", encoding="utf-8")
    with pytest.raises(ModelError, match="Неизвестный"):
        run_model(tmp_path / "clip.mov", 4.0, config, load_rules(RULES), time.monotonic() + 10)


def test_drop_in_model_adapter(tmp_path, monkeypatch):
    runtime = tmp_path / "model_runtime.py"
    runtime.write_text("def predict(video_path, duration_sec):\n    return [{'event_type':'cash_receipt_no_visible_recount','timestamp_sec':1,'observation':'Приём без пересчёта.'}]\n", encoding="utf-8")
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    config = settings(tmp_path, (sys.executable, "-m", "app.model_adapter"))
    events = run_model(tmp_path / "clip.mov", 4.0, config, load_rules(RULES), time.monotonic() + 10)
    assert events[0]["observation"] == "Приём без пересчёта."


def test_worker_builds_jury_result_and_deletes_video(tmp_path, monkeypatch):
    init(tmp_path)
    clip = tmp_path / "clip.mov"
    clip.write_bytes(b"video")
    create_job(tmp_path, "job-1", clip)
    job = claim_next(tmp_path)
    monkeypatch.setattr("app.worker.probe_video", lambda *args: 5.0)
    monkeypatch.setattr("app.worker.run_model", lambda *args: [
        {"event_type": "cash_receipt_no_visible_recount", "timestamp_sec": 2.0,
         "observation": "На видимом фрагменте приёма наличные не пересчитаны.", "frame_times": [2.0]}])
    monkeypatch.setattr("app.worker.jpeg_frame", lambda *args: "/9j/TEST")
    process_job(job, settings(tmp_path), load_rules(RULES))
    saved = get_job(tmp_path, "job-1")
    result = json.loads(saved["result_json"])
    assert result["verdict"] == "violation"
    assert result["violations"][0]["rule"]["section"] == "пункт 19, подпункт 2"
    assert "Возможный признак" in result["violations"][0]["description"]
    assert result["violations"][0]["evidence_frames"][0]["image_base64"] == "/9j/TEST"
    assert not clip.exists()


def test_worker_failure_is_not_a_negative_verdict(tmp_path, monkeypatch):
    init(tmp_path)
    clip = tmp_path / "clip.mov"
    clip.write_bytes(b"video")
    create_job(tmp_path, "job-2", clip)
    job = claim_next(tmp_path)
    monkeypatch.setattr("app.worker.probe_video", lambda *args: 5.0)
    monkeypatch.setattr("app.worker.run_model", lambda *args: (_ for _ in ()).throw(ModelError("модель недоступна")))
    process_job(job, settings(tmp_path), load_rules(RULES))
    saved = get_job(tmp_path, "job-2")
    assert saved["status"] == "failed"
    assert saved["result_json"] is None


def test_worker_keeps_multiple_events(tmp_path, monkeypatch):
    init(tmp_path)
    clip = tmp_path / "clip.mov"
    clip.write_bytes(b"video")
    create_job(tmp_path, "job-3", clip)
    job = claim_next(tmp_path)
    monkeypatch.setattr("app.worker.probe_video", lambda *args: 5.0)
    monkeypatch.setattr("app.worker.run_model", lambda *args: [
        {"event_type": "cash_receipt_no_visible_recount", "timestamp_sec": 1.0,
         "observation": "Первое событие.", "frame_times": [1.0]},
        {"event_type": "cash_disbursement_no_visible_recount", "timestamp_sec": 3.0,
         "observation": "Второе событие.", "frame_times": [2.9, 3.0]},
    ])
    monkeypatch.setattr("app.worker.jpeg_frame", lambda *args: "/9j/TEST")
    process_job(job, settings(tmp_path), load_rules(RULES))
    result = json.loads(get_job(tmp_path, "job-3")["result_json"])
    assert result["verdict"] == "violation"
    assert [x["timecode_sec"] for x in result["violations"]] == [1.0, 3.0]
    assert len(result["violations"][1]["evidence_frames"]) == 2


def test_successful_empty_model_result_is_no_violation(tmp_path, monkeypatch):
    init(tmp_path)
    clip = tmp_path / "clip.mov"
    clip.write_bytes(b"video")
    create_job(tmp_path, "job-4", clip)
    job = claim_next(tmp_path)
    monkeypatch.setattr("app.worker.probe_video", lambda *args: 5.0)
    monkeypatch.setattr("app.worker.run_model", lambda *args: [])
    process_job(job, settings(tmp_path), load_rules(RULES))
    result = json.loads(get_job(tmp_path, "job-4")["result_json"])
    assert result == {"job_id": "job-4", "status": "done", "verdict": "no_violation", "violations": []}
