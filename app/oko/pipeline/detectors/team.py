"""Adapt the existing team's local command contract to OKO candidates."""
from pathlib import Path
from types import SimpleNamespace

from app.model import load_rules, run_model, ModelError
from ...rules.catalog import RULES
from .base import Candidate, Detector

EVENT_RULES = {
    "cash_receipt_no_visible_recount": "V06",
    "cash_disbursement_no_visible_recount": "V05",
}


class TeamDetector(Detector):
    name = "team"

    def end(self, ctx):
        if not ctx.settings.team_model_command:
            raise ModelError("Команда модели команды не настроена")
        definitions = load_rules(Path(ctx.settings.team_rules_path))
        definitions.update({rule_id: {} for rule_id in RULES})
        options = SimpleNamespace(model_command=ctx.settings.team_model_command,
                                  model_timeout_seconds=ctx.settings.model_timeout_seconds)
        events = run_model(ctx.info.path, ctx.info.duration, options, definitions, ctx.deadline)
        result = []
        for event in events:
            rule_id = EVENT_RULES.get(event["event_type"], event["event_type"])
            if rule_id not in RULES:
                raise ModelError("Тип события модели не сопоставлен с каталогом OKO")
            confidence = event.get("confidence")
            result.append(Candidate(
                rule_id=rule_id, t_start=event["timestamp_sec"],
                confidence=confidence if confidence is not None else ctx.settings.threshold,
                observed=event["observation"], evidence_times=event["frame_times"],
                source=self.name, meta={"confidence_unavailable": confidence is None},
            ))
        return result
