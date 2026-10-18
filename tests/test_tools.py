import base64
from scripts.eval_labels import parse_time
from scripts.smoke_test import check_schema


def test_dataset_clock_formats():
    assert parse_time("1:02") == 62
    assert parse_time("00:01:02") == 62
    assert parse_time("1 мин 2 сек") == 62
    assert parse_time("1:02,5") == 62.5


def test_truncated_jpeg_is_rejected():
    result = {"job_id": "example", "status": "done", "verdict": "violation", "violations": [
        {"type": "example", "timecode_sec": 1, "description": "example п. 12", "evidence_frames": [
            {"timestamp_sec": 1, "image_base64": base64.b64encode(b"\xff\xd8").decode()}]}]}
    assert check_schema(result)
