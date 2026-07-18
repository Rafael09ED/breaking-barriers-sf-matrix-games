import json

from pydantic import BaseModel

from takeoff.models import (
    ActorId,
    Fact,
    FactEvaluationContext,
    Visibility,
)
from takeoff.openrouter import StructuredModelClient
from takeoff.prompts import fact_evaluation_messages
from takeoff.scenario import build_scenario
from takeoff.umpire import LlmUmpire


class FakeClient(StructuredModelClient):
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def generate(self, messages, schema: type[BaseModel], schema_name: str) -> str:
        self.calls += 1
        return self.responses.pop(0)


def evaluation_context(*, covert: bool = False) -> FactEvaluationContext:
    scenario = build_scenario(turns=6)
    trigger = Fact(
        id="F5",
        text="Agent-5 training was suspended for 60 days.",
        visibility=Visibility.COVERT if covert else Visibility.PUBLIC,
        known_by=(ActorId.POTUS,) if covert else (),
        trigger_evaluation_at=4,
    )
    return FactEvaluationContext(
        scenario=scenario,
        turn=4,
        trigger_fact=trigger,
        facts=(*scenario.start_facts, trigger),
    )


def test_fact_evaluation_may_record_no_change() -> None:
    result = LlmUmpire(
        FakeClient(['{"rationale":"No new status is established.","new_fact":null}'])
    ).evaluate_trigger(evaluation_context())

    assert result.attempts == 1
    assert result.evaluation.new_fact is None


def test_fact_evaluation_can_append_and_schedule_later_review() -> None:
    payload = {
        "rationale": "The review period ended but the later facts preserve the pause.",
        "new_fact": {
            "text": "The 60-day review ended while Agent-5 training remained paused.",
            "visibility": "public",
            "known_by": [],
            "source_fact_ids": ["F5"],
            "supersedes_fact_ids": ["F5"],
            "trigger_evaluation_at": 6,
        },
    }

    result = LlmUmpire(FakeClient([json.dumps(payload)])).evaluate_trigger(
        evaluation_context()
    )

    assert result.attempts == 1
    assert result.evaluation.new_fact is not None
    assert result.evaluation.new_fact.trigger_evaluation_at == 6


def test_fact_evaluation_retries_invalid_schedule() -> None:
    invalid = {
        "rationale": "Schedule another review immediately.",
        "new_fact": {
            "text": "The review remained open.",
            "visibility": "public",
            "known_by": [],
            "source_fact_ids": ["F5"],
            "supersedes_fact_ids": [],
            "trigger_evaluation_at": 4,
        },
    }
    valid = {"rationale": "No new status is established.", "new_fact": None}
    client = FakeClient([json.dumps(invalid), json.dumps(valid)])

    result = LlmUmpire(client).evaluate_trigger(evaluation_context())

    assert result.attempts == 2
    assert client.calls == 2


def test_covert_trigger_cannot_directly_produce_public_fact() -> None:
    invalid = {
        "rationale": "Reveal the private suspension.",
        "new_fact": {
            "text": "The private suspension became public.",
            "visibility": "public",
            "known_by": [],
            "source_fact_ids": ["F5"],
            "supersedes_fact_ids": [],
            "trigger_evaluation_at": None,
        },
    }
    valid = {"rationale": "No public revelation occurred.", "new_fact": None}
    client = FakeClient([json.dumps(invalid), json.dumps(valid)])

    result = LlmUmpire(client).evaluate_trigger(evaluation_context(covert=True))

    assert result.attempts == 2


def test_fact_evaluation_prompt_contains_full_ledger() -> None:
    messages = fact_evaluation_messages(evaluation_context())
    prompt = messages[1]["content"]

    assert "COMPLETE PRIVILEGED ACTIVE LEDGER" in prompt
    assert "[F1] Agent-4 performs AI research beyond top human level." in prompt
    assert "[F5] Agent-5 training was suspended for 60 days." in prompt