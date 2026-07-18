from collections.abc import Mapping, Sequence
import logging

import pytest
from pydantic import BaseModel

from takeoff.controllers import LlmController
from takeoff.events import GameStarted, GameState, TurnStarted, reduce_event
from takeoff.ledger import build_player_context
from takeoff.models import ActorId, Fact, Visibility
from takeoff.openrouter import ModelOutputError, StructuredModelClient
from takeoff.scenario import build_scenario


class FakeClient(StructuredModelClient):
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.messages: list[Sequence[Mapping[str, str]]] = []

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[BaseModel],
        schema_name: str,
    ) -> str:
        self.messages.append(messages)
        return self.responses.pop(0)


def active_state():
    scenario = build_scenario()
    game_id = __import__("uuid").uuid4()
    state = reduce_event(
        GameState(), GameStarted(game_id=game_id, seq=1, scenario=scenario)
    )
    state = reduce_event(
        state,
        TurnStarted(
            game_id=game_id,
            seq=2,
            turn=1,
            actor_order=tuple(actor.id for actor in scenario.actors),
        ),
    )
    return state


def context_for(actor_id: ActorId):
    return build_player_context(active_state(), actor_id)


def test_controller_returns_valid_argument_without_retry() -> None:
    client = FakeClient(
        [
            '{"action":"Run a bounded audit.",'
            '"intended_result":"Produce evidence.",'
            '"reasons":["Existing results are ambiguous."],'
            '"spend_fail_chit_on_failure":false}'
        ]
    )

    result = LlmController(client).propose(context_for(ActorId.ALIGN))

    assert result.argument.action == "Run a bounded audit."
    assert result.attempts == 1
    assert len(client.messages) == 1


def test_controller_retries_once_with_correction() -> None:
    client = FakeClient(
        [
            "not json",
            '{"action":"Brief the NSC.",'
            '"intended_result":"Establish oversight.",'
            '"reasons":["The White House lacks a full briefing."],'
            '"spend_fail_chit_on_failure":false}',
        ]
    )

    result = LlmController(client).propose(context_for(ActorId.POTUS))

    assert result.attempts == 2
    assert "did not match" in client.messages[1][-1]["content"]


def test_controller_stops_after_second_invalid_response(caplog) -> None:
    client = FakeClient(["{}", '{"action":"Still missing fields"}'])

    with caplog.at_level(logging.ERROR), pytest.raises(
        ModelOutputError, match="player response invalid after 2 attempts"
    ) as raised:
        LlmController(client).propose(context_for(ActorId.CEO))

    assert "attempt 1" in str(raised.value)
    assert "attempt 2" in str(raised.value)
    assert "Invalid player response for CEO on attempt 1" in caplog.text
    assert "Invalid player response for CEO on attempt 2" in caplog.text


def test_player_prompt_contains_only_actors_private_brief() -> None:
    client = FakeClient(
        [
            '{"action":"Audit.","intended_result":"Evidence.",'
            '"reasons":["Ambiguous results."],'
            '"spend_fail_chit_on_failure":false}'
        ]
    )
    context = context_for(ActorId.ALIGN)

    LlmController(client).propose(context)

    prompt = client.messages[0][1]["content"]
    assert context.actor.private_brief in prompt
    assert "Your goals misgeneralized during training" not in prompt


def test_player_prompt_requires_one_bounded_undertaking() -> None:
    client = FakeClient(
        [
            '{"action":"Audit.","intended_result":"Evidence.",'
            '"reasons":["Ambiguous results."],'
            '"spend_fail_chit_on_failure":false}'
        ]
    )

    LlmController(client).propose(context_for(ActorId.ALIGN))

    system_prompt = " ".join(client.messages[0][0]["content"].split())
    assert "exactly one bounded undertaking" in system_prompt
    assert "independent success criteria" in system_prompt


def test_player_retry_prompt_includes_umpire_veto() -> None:
    client = FakeClient(
        [
            '{"action":"Audit.","intended_result":"Evidence.",'
            '"reasons":["Ambiguous results."],'
            '"spend_fail_chit_on_failure":false}'
        ]
    )
    context = context_for(ActorId.ALIGN).model_copy(
        update={"veto_feedback": "The proposal combines an audit and a briefing."}
    )

    LlmController(client).propose(context)

    prompt = client.messages[0][1]["content"]
    assert "PREVIOUS VETO" in prompt
    assert context.veto_feedback in prompt


def test_covert_fact_does_not_enter_other_actor_model_request() -> None:
    state = active_state()
    covert = Fact(
        id="F5",
        text="UNIQUE-COVERT-SENTINEL",
        visibility=Visibility.COVERT,
        known_by=(ActorId.AGENT4,),
    )
    state = state.model_copy(update={"facts": {**state.facts, covert.id: covert}})

    response = (
        '{"action":"Audit.","intended_result":"Evidence.",'
        '"reasons":["Ambiguous results."],'
        '"spend_fail_chit_on_failure":false}'
    )
    owner_client = FakeClient([response])
    other_client = FakeClient([response])

    LlmController(owner_client).propose(build_player_context(state, ActorId.AGENT4))
    LlmController(other_client).propose(build_player_context(state, ActorId.ALIGN))

    owner_prompt = owner_client.messages[0][1]["content"]
    other_prompt = other_client.messages[0][1]["content"]

    assert covert.text in owner_prompt
    assert covert.text not in other_prompt