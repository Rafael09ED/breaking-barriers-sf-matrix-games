from dataclasses import dataclass
import json
import logging
import re
from typing import Protocol
import unicodedata

from pydantic import ValidationError

from takeoff.models import (
    Adjudication,
    FactEvaluationContext,
    FactEvaluationResult,
    UmpireContext,
    Visibility,
)
from takeoff.openrouter import ModelOutputError, StructuredModelClient
from takeoff.prompts import (
    corrective_umpire_messages,
    fact_evaluation_messages,
    umpire_messages,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdjudicationResult:
    adjudication: Adjudication
    attempts: int


@dataclass(frozen=True)
class TriggerEvaluationResult:
    evaluation: FactEvaluationResult
    attempts: int


class Umpire(Protocol):
    def adjudicate(self, context: UmpireContext) -> AdjudicationResult: ...

    def evaluate_trigger(
        self, context: FactEvaluationContext
    ) -> TriggerEvaluationResult: ...


class LlmUmpire:
    def __init__(self, client: StructuredModelClient) -> None:
        self._client = client

    def adjudicate(self, context: UmpireContext) -> AdjudicationResult:
        messages = umpire_messages(context)
        last_error = "unknown validation error"
        errors: list[str] = []
        for attempt in range(1, 3):
            request_messages = (
                messages
                if attempt == 1
                else corrective_umpire_messages(messages, last_error)
            )
            try:
                content = self._client.generate(
                    request_messages,
                    Adjudication,
                    "takeoff_umpire_adjudication",
                )
                payload = json.loads(content)
                _normalize_adjudication_payload(context, payload)
                adjudication = Adjudication.model_validate(payload)
                _validate_adjudication(context, adjudication)
                return AdjudicationResult(adjudication, attempt)
            except (ValidationError, ModelOutputError, ValueError) as error:
                last_error = str(error)
                errors.append(f"attempt {attempt}: {last_error}")
                logger.error(
                    "Invalid umpire response for %s on attempt %d: %s",
                    context.actor_id.value,
                    attempt,
                    last_error,
                )
        raise ModelOutputError(
            f"umpire response invalid after 2 attempts for {context.actor_id.value}: "
            + " | ".join(errors)
        )

    def evaluate_trigger(
        self, context: FactEvaluationContext
    ) -> TriggerEvaluationResult:
        messages = fact_evaluation_messages(context)
        last_error = "unknown validation error"
        errors: list[str] = []
        for attempt in range(1, 3):
            request_messages = (
                messages
                if attempt == 1
                else corrective_umpire_messages(messages, last_error)
            )
            try:
                content = self._client.generate(
                    request_messages,
                    FactEvaluationResult,
                    "takeoff_fact_evaluation",
                )
                evaluation = FactEvaluationResult.model_validate_json(content)
                _validate_fact_evaluation(context, evaluation)
                return TriggerEvaluationResult(evaluation, attempt)
            except (ValidationError, ModelOutputError, ValueError) as error:
                last_error = str(error)
                errors.append(f"attempt {attempt}: {last_error}")
                logger.error(
                    "Invalid fact evaluation for %s on attempt %d: %s",
                    context.trigger_fact.id,
                    attempt,
                    last_error,
                )
        raise ModelOutputError(
            "fact evaluation invalid after 2 attempts for "
            f"{context.trigger_fact.id}: " + " | ".join(errors)
        )


def _normalize_adjudication_payload(
    context: UmpireContext, payload: object
) -> None:
    if not isinstance(payload, dict):
        return
    pro_strength = payload.get("pro_strength")
    con_strength = payload.get("con_strength")
    if isinstance(pro_strength, int) and isinstance(con_strength, int):
        payload["net_mod"] = pro_strength - con_strength
    for branch in ("new_facts_success", "new_facts_failure"):
        changes = payload.get(branch)
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict) or change.get("operation") != "add":
                continue
            if change.get("visibility") == "public":
                change["known_by"] = []
            elif change.get("visibility") == "covert" and not change.get("known_by"):
                change["known_by"] = [context.actor_id.value]


def _validate_adjudication(
    context: UmpireContext, adjudication: Adjudication
) -> None:
    if adjudication.veto is not None:
        return
    expected_indices = list(range(1, len(context.argument.reasons) + 1))
    actual_indices = [pro.reason_index for pro in adjudication.pros]
    if actual_indices != expected_indices:
        raise ValueError(
            "pros reason_index values must be exactly "
            f"{expected_indices}, got {actual_indices}; assess duplicate or invalid "
            "reasons separately"
        )
    expected_mod = adjudication.pro_strength - adjudication.con_strength
    if adjudication.net_mod != expected_mod:
        raise ValueError(
            f"net_mod must be {expected_mod}, got {adjudication.net_mod}"
        )
    if adjudication.pro_strength == 3 and len(adjudication.pros) < 2:
        raise ValueError(
            "pro_strength 3 requires at least two independently assessed reasons"
        )
    if adjudication.con_strength == 3 and len(adjudication.cons) < 2:
        raise ValueError(
            "con_strength 3 requires at least two independently assessed cons"
        )
    active_ids = {fact.id for fact in context.facts if fact.active}
    active_texts = {
        _normalize_fact_text(fact.text): fact.id
        for fact in context.facts
        if fact.active
    }
    actor_ids = {actor.id for actor in context.scenario.actors}
    for branch_name, changes in (
        ("success", adjudication.new_facts_success),
        ("failure", adjudication.new_facts_failure),
    ):
        branch_texts: set[str] = set()
        for change in changes:
            if (
                adjudication.visibility.value == "covert"
                and change.operation == "add"
                and change.visibility is not None
                and change.visibility.value == "public"
            ):
                raise ValueError("covert adjudications may add only covert facts")
            if change.operation == "end" and change.fact_id not in active_ids:
                raise ValueError(f"cannot end inactive or unknown fact {change.fact_id}")
            unknown_sources = set(change.source_fact_ids) - active_ids
            if unknown_sources:
                raise ValueError(
                    "fact change source_fact_ids contain inactive or unknown facts: "
                    + ", ".join(sorted(unknown_sources))
                )
            unknown_superseded = set(change.supersedes_fact_ids) - active_ids
            if unknown_superseded:
                raise ValueError(
                    "fact change supersedes inactive or unknown facts: "
                    + ", ".join(sorted(unknown_superseded))
                )
            if change.trigger_evaluation_at is not None and not (
                context.turn
                < change.trigger_evaluation_at
                <= context.scenario.rules.turns
            ):
                raise ValueError(
                    "fact trigger_evaluation_at must be a later turn in this game"
                )
            if not set(change.known_by).issubset(actor_ids):
                raise ValueError("fact change known_by contains an unknown actor")
            if change.operation != "add" or change.text is None:
                continue
            normalized_text = _normalize_fact_text(change.text)
            duplicate_id = active_texts.get(normalized_text)
            if duplicate_id is not None:
                raise ValueError(
                    f"{branch_name} fact duplicates active fact {duplicate_id}"
                )
            if normalized_text in branch_texts:
                raise ValueError(
                    f"{branch_name} branch contains duplicate added facts"
                )
            branch_texts.add(normalized_text)


def _normalize_fact_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.rstrip(".!?;:").rstrip()


def _validate_fact_evaluation(
    context: FactEvaluationContext, evaluation: FactEvaluationResult
) -> None:
    new_fact = evaluation.new_fact
    if new_fact is None:
        return
    active_facts = {fact.id: fact for fact in context.facts if fact.active}
    active_ids = set(active_facts)
    if context.trigger_fact.id not in new_fact.source_fact_ids:
        raise ValueError("evaluated fact must cite the triggering fact as a source")
    unknown_sources = set(new_fact.source_fact_ids) - active_ids
    if unknown_sources:
        raise ValueError(
            "evaluated fact source_fact_ids contain inactive or unknown facts: "
            + ", ".join(sorted(unknown_sources))
        )
    unknown_superseded = set(new_fact.supersedes_fact_ids) - active_ids
    if unknown_superseded:
        raise ValueError(
            "evaluated fact supersedes inactive or unknown facts: "
            + ", ".join(sorted(unknown_superseded))
        )
    actor_ids = {actor.id for actor in context.scenario.actors}
    if not set(new_fact.known_by).issubset(actor_ids):
        raise ValueError("evaluated fact known_by contains an unknown actor")
    if (
        context.trigger_fact.visibility == Visibility.COVERT
        and new_fact.visibility == Visibility.PUBLIC
    ):
        raise ValueError("a covert trigger cannot directly produce a public fact")
    if new_fact.trigger_evaluation_at is not None and not (
        context.turn < new_fact.trigger_evaluation_at <= context.scenario.rules.turns
    ):
        raise ValueError("next fact evaluation must be a later turn in this game")
    normalized_text = _normalize_fact_text(new_fact.text)
    for fact in active_facts.values():
        if normalized_text == _normalize_fact_text(fact.text):
            raise ValueError(f"evaluated fact duplicates active fact {fact.id}")