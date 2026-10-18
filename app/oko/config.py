"""Immutable OKO pipeline options, supplied only by app.config.Settings.

There is no second environment loader, API key generator or data directory.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_keys: tuple[str, ...]
    workers: int
    deadline_sec: float
    reserve_sec: float
    max_upload_mb: int
    max_queue: int
    sample_fps: float
    threshold: float
    review_threshold: float
    detectors: tuple[str, ...]
    keep_videos: bool
    face_blur: str
    evidence_max_width: int
    jpeg_quality: int
    api_extra_fields: bool
    max_violations: int
    team_model_command: tuple[str, ...] = ()
    team_rules_path: str = ""
    model_timeout_seconds: int = 210
    max_video_seconds: float = 3600.0

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

