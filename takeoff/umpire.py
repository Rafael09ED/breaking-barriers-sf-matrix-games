from dataclasses import dataclass
import logging
import re
from typing import Protocol

from pydantic import ValidationError

from takeoff.models import Adjudication, UmpireContext
from takeoff.openrouter import ModelOutputError, StructuredModelClient
from takeoff.prompts import corrective_umpire_messages, umpire_messages


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdjudicationResult:
    adjudication: Adjudication
    attempts: int


class Umpire(Protocol):
    def adjudicate(self, context: UmpireContext) -> AdjudicationResult: ...


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
                adjudication = Adjudication.model_validate_json(content)
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
    _validate_public_surface(context, adjudication)
    active_ids = {fact.id for fact in context.facts if fact.active}
    for change in (
        *adjudication.new_facts_success,
        *adjudication.new_facts_failure,
    ):
        if change.operation == "end" and change.fact_id not in active_ids:
            raise ValueError(f"cannot end inactive or unknown fact {change.fact_id}")


def _validate_public_surface(
    context: UmpireContext, adjudication: Adjudication
) -> None:
    hidden_facts = [
        fact
        for fact in context.facts
        if fact.active and fact.visibility.value == "covert"
    ]
    public_texts = [adjudication.public_observation or ""]
    if adjudication.visibility.value == "public":
        public_texts.extend(item.claim for item in adjudication.cons)
        public_texts.extend(
            (adjudication.success_narration, adjudication.failure_narration)
        )
        public_texts.extend(
            change.text or ""
            for change in (
                *adjudication.new_facts_success,
                *adjudication.new_facts_failure,
            )
            if change.operation == "add"
        )
    public_surface = "\n".join(public_texts).casefold()
    for fact in hidden_facts:
        if re.search(rf"\b{re.escape(fact.id.casefold())}\b", public_surface):
            raise ValueError(f"public adjudication leaks hidden fact ID {fact.id}")
        if fact.text.casefold() in public_surface:
            raise ValueError(f"public adjudication leaks hidden fact text {fact.id}")