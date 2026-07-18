from dataclasses import dataclass
import logging
from typing import Protocol

from pydantic import ValidationError

from takeoff.models import Argument, PlayerContext, PlayerProposal
from takeoff.openrouter import ModelOutputError, StructuredModelClient
from takeoff.prompts import corrective_player_messages, player_messages


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProposalResult:
    argument: Argument
    attempts: int
    spend_fail_chit_on_failure: bool = False


class Controller(Protocol):
    def propose(self, context: PlayerContext) -> ProposalResult: ...


class LlmController:
    def __init__(self, client: StructuredModelClient) -> None:
        self._client = client

    def propose(self, context: PlayerContext) -> ProposalResult:
        messages = player_messages(context)
        last_error = "unknown validation error"
        errors: list[str] = []
        for attempt in range(1, 3):
            request_messages = (
                messages
                if attempt == 1
                else corrective_player_messages(messages, last_error)
            )
            try:
                content = self._client.generate(
                    request_messages,
                    PlayerProposal,
                    "takeoff_player_argument",
                )
                proposal = PlayerProposal.model_validate_json(content)
                return ProposalResult(
                    argument=Argument(
                        action=proposal.action,
                        intended_result=proposal.intended_result,
                        reasons=proposal.reasons,
                    ),
                    attempts=attempt,
                    spend_fail_chit_on_failure=(
                        proposal.spend_fail_chit_on_failure
                        and context.fail_chits > 0
                    ),
                )
            except (ValidationError, ModelOutputError, ValueError) as error:
                last_error = str(error)
                errors.append(f"attempt {attempt}: {last_error}")
                logger.error(
                    "Invalid player response for %s on attempt %d: %s",
                    context.actor.id.value,
                    attempt,
                    last_error,
                )

        raise ModelOutputError(
            f"player response invalid after 2 attempts for {context.actor.id.value}: "
            + " | ".join(errors)
        )