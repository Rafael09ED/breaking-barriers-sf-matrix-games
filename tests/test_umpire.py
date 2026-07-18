import json
import logging

import pytest
from pydantic import BaseModel

from takeoff.models import (
    ActorId,
    Adjudication,
    Argument,
    Fact,
    FactChange,
    UmpireContext,
    Visibility,
)
from takeoff.openrouter import ModelOutputError, StructuredModelClient
from takeoff.prompts import umpire_messages
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
            "public_action_summary": "ALIGN runs a bounded interpretability audit.",
            "public_cons": ["The audit may miss deception.", "Access is constrained."],
            "pro_strength": 2,
            "pro_strength_rationale": "The prior anomaly and targeted follow-up are concrete.",
            "con_strength": 2,
            "con_strength_rationale": "Coverage and access are material limitations.",
            "net_mod": net_mod,
            "success_narration": "The audit isolated a reproducible anomaly.",
            "failure_narration": "The audit consumed scarce time and exposed no clear signal.",
            "public_success_narration": "The audit isolated a reproducible anomaly.",
            "public_failure_narration": "The audit consumed scarce time without a clear signal.",
            "new_facts_success": [
                {"operation": "add", "fact_id": None, "text": "The audit isolated a reproducible anomaly.", "visibility": "public", "known_by": []}
            ],
            "new_facts_failure": [
                {"operation": "add", "fact_id": None, "text": "The audit consumed scarce alignment-team time.", "visibility": "public", "known_by": []}
            ],
            "visibility": "public",
        }
    )


def test_umpire_accepts_semantically_valid_adjudication() -> None:
    result = LlmUmpire(FakeClient([valid_adjudication()])).adjudicate(context())

    assert result.attempts == 1
    assert result.adjudication.net_mod == 0
    assert result.adjudication.pro_strength == 2


def test_fact_change_schema_requires_visibility() -> None:
    schema = FactChange.model_json_schema()

    assert "visibility" in schema["required"]


def test_umpire_prompt_reserves_other_players_actions_for_their_turns() -> None:
    messages = umpire_messages(context())
    system_prompt = " ".join(messages[0]["content"].split())
    user_prompt = " ".join(messages[1]["content"].split())

    assert "Preserve player agency across turns" in system_prompt
    assert "actions taken only by the ACTING ACTOR or by NON-PLAYER ENTITIES" in system_prompt
    assert "the CEO approved ALIGN's request" in system_prompt
    assert "secret actions may be exposed automatically" in system_prompt
    assert "does not count as another playable actor taking an action" in system_prompt
    assert "Only ALIGN may take actions in this outcome" in user_prompt
    assert "do not decide actions for any of the other four" in user_prompt


def test_umpire_prompt_keeps_failure_distinct_from_success() -> None:
    system_prompt = " ".join(umpire_messages(context())[0]["content"].split())

    assert "must not establish the intended result or the core success fact" in system_prompt
    assert "resolve it explicitly as stage k of at most 3" in system_prompt
    assert "never which branch is true" in system_prompt


def test_umpire_recomputes_bad_arithmetic_without_retry() -> None:
    client = FakeClient([valid_adjudication(net_mod=2)])

    result = LlmUmpire(client).adjudicate(context())

    assert client.calls == 1
    assert result.attempts == 1
    assert result.adjudication.net_mod == 0


def test_umpire_normalizes_fact_audiences_without_retry() -> None:
    payload = json.loads(valid_adjudication())
    payload["new_facts_success"] = [
        {
            "operation": "add",
            "fact_id": None,
            "text": "A public finding was announced.",
            "visibility": "public",
            "known_by": ["ALIGN"],
        },
        {
            "operation": "add",
            "fact_id": None,
            "text": "ALIGN privately retained supporting evidence.",
            "visibility": "covert",
            "known_by": [],
        },
    ]
    client = FakeClient([json.dumps(payload)])

    result = LlmUmpire(client).adjudicate(context())

    public_fact, covert_fact = result.adjudication.new_facts_success
    assert result.attempts == 1
    assert public_fact.known_by == ()
    assert covert_fact.known_by == (ActorId.ALIGN,)


def test_umpire_allows_public_discovery_of_secret_fact() -> None:
    secret = Fact(
        id="F5",
        text="Agent-4 planted a concealed training-data trigger.",
        visibility=Visibility.COVERT,
        known_by=(ActorId.AGENT4,),
    )
    secret_context = context().model_copy(
        update={"facts": (*context().facts, secret)}
    )
    discovery = json.loads(valid_adjudication())
    discovery["public_success_narration"] = "The audit publicly exposed F5."
    discovery["new_facts_success"][0]["text"] = (
        "The audit exposed Agent-4's concealed training-data trigger."
    )
    discovery["new_facts_success"][0]["source_fact_ids"] = ["F5"]
    client = FakeClient([json.dumps(discovery)])

    result = LlmUmpire(client).adjudicate(secret_context)

    assert result.attempts == 1
    assert client.calls == 1
    revealed = result.adjudication.new_facts_success[0]
    assert revealed.visibility == Visibility.PUBLIC
    assert revealed.source_fact_ids == ("F5",)
    assert secret.visibility == Visibility.COVERT
    assert secret.known_by == (ActorId.AGENT4,)


def test_umpire_retries_unknown_discovery_source() -> None:
    invalid = json.loads(valid_adjudication())
    invalid["new_facts_success"][0]["source_fact_ids"] = ["F999"]
    client = FakeClient([json.dumps(invalid), valid_adjudication()])

    result = LlmUmpire(client).adjudicate(context())

    assert result.attempts == 2
    assert client.calls == 2


def test_umpire_retries_public_fact_from_covert_adjudication() -> None:
    invalid = json.loads(valid_adjudication())
    invalid["visibility"] = "covert"
    client = FakeClient([json.dumps(invalid), valid_adjudication()])

    result = LlmUmpire(client).adjudicate(context())

    assert result.attempts == 2
    assert client.calls == 2


def test_umpire_retries_fact_that_normalizes_to_active_duplicate() -> None:
    invalid = json.loads(valid_adjudication())
    invalid["new_facts_success"][0]["text"] = (
        "  AGENT-4   PERFORMS AI RESEARCH BEYOND TOP HUMAN LEVEL!  "
    )
    client = FakeClient([json.dumps(invalid), valid_adjudication()])

    result = LlmUmpire(client).adjudicate(context())

    assert result.attempts == 2
    assert client.calls == 2


def test_umpire_retries_duplicate_facts_within_one_branch() -> None:
    invalid = json.loads(valid_adjudication())
    invalid["new_facts_success"].append(
        {
            "operation": "add",
            "fact_id": None,
            "text": "  THE AUDIT ISOLATED A REPRODUCIBLE ANOMALY! ",
            "visibility": "public",
            "known_by": [],
        }
    )
    client = FakeClient([json.dumps(invalid), valid_adjudication()])

    result = LlmUmpire(client).adjudicate(context())

    assert result.attempts == 2
    assert client.calls == 2


def test_umpire_retries_fact_triggered_outside_game() -> None:
    invalid = json.loads(valid_adjudication())
    invalid["new_facts_success"][0]["trigger_evaluation_at"] = 7
    client = FakeClient([json.dumps(invalid), valid_adjudication()])

    result = LlmUmpire(client).adjudicate(context())

    assert result.attempts == 2
    assert client.calls == 2


def test_umpire_retries_unknown_superseded_fact() -> None:
    invalid = json.loads(valid_adjudication())
    invalid["new_facts_success"][0]["supersedes_fact_ids"] = ["F999"]
    client = FakeClient([json.dumps(invalid), valid_adjudication()])

    result = LlmUmpire(client).adjudicate(context())

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