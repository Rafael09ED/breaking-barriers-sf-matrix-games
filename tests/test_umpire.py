import json
import logging

import pytest
from pydantic import BaseModel

from takeoff.models import (
    ActorId,
    Adjudication,
    Argument,
    Fact,
    UmpireContext,
    Visibility,
)
from takeoff.openrouter import ModelOutputError, StructuredModelClient
from takeoff.scenario import build_scenario
from takeoff.umpire import LlmUmpire


class FakeClient(StructuredModelClient):
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def generate(self, messages, schema: type[BaseModel], schema_name: str) -> str:
        self.calls += 1
        return self.responses.pop(0)


def context() -> UmpireContext:
    scenario = build_scenario()
    return UmpireContext(
        scenario=scenario,
        turn=1,
        actor_id=ActorId.ALIGN,
        argument=Argument(
            action="Run a bounded interpretability audit.",
            intended_result="Produce material alignment evidence.",
            reasons=("Existing interpretability results are ambiguous.",),
        ),
        facts=scenario.start_facts,
    )


def valid_adjudication(*, net_mod: int = 0) -> str:
    return json.dumps(
        {
            "veto": None,
            "pros": [
                {
                    "claim": "Ambiguous results",
                    "rationale": "Specific",
                    "reason_index": 1,
                }
            ],
            "cons": [
                {"claim": "Audit may miss deception", "rationale": "Coverage"},
                {"claim": "Access is constrained", "rationale": "Operational"},
            ],
            "pro_strength": 2,
            "pro_strength_rationale": "The prior anomaly and targeted follow-up are concrete.",
            "con_strength": 2,
            "con_strength_rationale": "Coverage and access are material limitations.",
            "net_mod": net_mod,
            "success_narration": "The audit isolated a reproducible anomaly.",
            "failure_narration": "The audit consumed scarce time and exposed no clear signal.",
            "new_facts_success": [
                {"operation": "add", "fact_id": None, "text": "The audit isolated a reproducible anomaly."}
            ],
            "new_facts_failure": [
                {"operation": "add", "fact_id": None, "text": "The audit consumed scarce alignment-team time."}
            ],
            "visibility": "public",
            "public_observation": None,
        }
    )


def test_umpire_accepts_semantically_valid_adjudication() -> None:
    result = LlmUmpire(FakeClient([valid_adjudication()])).adjudicate(context())

    assert result.attempts == 1
    assert result.adjudication.net_mod == 0
    assert result.adjudication.pro_strength == 2


def test_umpire_retries_bad_arithmetic_once() -> None:
    client = FakeClient([valid_adjudication(net_mod=2), valid_adjudication()])

    result = LlmUmpire(client).adjudicate(context())

    assert client.calls == 2
    assert result.attempts == 2


def test_umpire_retries_public_adjudication_that_leaks_secret_fact() -> None:
    secret = Fact(
        id="F5",
        text="Agent-4 planted a concealed training-data trigger.",
        visibility=Visibility.COVERT,
        owner=ActorId.AGENT4,
    )
    secret_context = context().model_copy(
        update={"facts": (*context().facts, secret)}
    )
    leaking = json.loads(valid_adjudication())
    leaking["cons"][0]["claim"] = "F5 may compromise the audit."
    client = FakeClient([json.dumps(leaking), valid_adjudication()])

    result = LlmUmpire(client).adjudicate(secret_context)

    assert result.attempts == 2
    assert client.calls == 2


def test_umpire_stops_and_logs_after_two_invalid_responses(caplog) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(
        ModelOutputError, match="umpire response invalid after 2 attempts"
    ) as raised:
        LlmUmpire(FakeClient(["{}", "not json"])).adjudicate(context())

    assert "attempt 1" in str(raised.value)
    assert "attempt 2" in str(raised.value)
    assert "Invalid umpire response for ALIGN on attempt 1" in caplog.text
    assert "Invalid umpire response for ALIGN on attempt 2" in caplog.text


def test_legacy_additive_scores_are_rejected() -> None:
    payload = json.loads(valid_adjudication())
    payload["pros"][0]["weight"] = 2
    payload["cons"][0]["weight"] = 2
    payload["cons"][1]["weight"] = 2
    for field in (
        "pro_strength",
        "pro_strength_rationale",
        "con_strength",
        "con_strength_rationale",
    ):
        payload.pop(field)

    with pytest.raises(ValueError):
        Adjudication.model_validate(payload)