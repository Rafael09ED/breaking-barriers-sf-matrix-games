from threading import Thread

from takeoff.controllers import ProposalResult
from takeoff.models import ActorId, Argument
from takeoff.openrouter import ModelOutputError
from takeoff.web_sessions import WebHumanController

from tests.test_controllers import context_for


class RecordingParser:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.submissions: list[str] = []

    def parse(self, context, submission):
        self.submissions.append(submission)
        if self.failures:
            self.failures -= 1
            raise ModelOutputError("Could not identify an intended result.")
        return ProposalResult(
            argument=Argument(
                action=submission,
                intended_result="One result.",
                reasons=("One reason.",),
            ),
            attempts=1,
        )


def run_proposal(controller, context, results):
    results.append(controller.propose(context))


def test_web_human_controller_waits_for_submission() -> None:
    controller = WebHumanController(RecordingParser())
    results: list[ProposalResult] = []
    thread = Thread(
        target=run_proposal,
        args=(controller, context_for(ActorId.ALIGN), results),
        daemon=True,
    )
    thread.start()

    assert wait_for_status(controller, "waiting_human").context.actor.id == ActorId.ALIGN
    assert controller.submit("submission-1", "Run a bounded audit.")
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert results[0].argument.action == "Run a bounded audit."
    assert controller.snapshot().status == "running"


def test_parser_failure_preserves_draft_and_waits_again() -> None:
    parser = RecordingParser(failures=1)
    controller = WebHumanController(parser)
    results: list[ProposalResult] = []
    thread = Thread(
        target=run_proposal,
        args=(controller, context_for(ActorId.ALIGN), results),
        daemon=True,
    )
    thread.start()

    wait_for_status(controller, "waiting_human")
    controller.submit("submission-1", "Audit somehow.")
    failed = wait_for_status(controller, "waiting_human", require_error=True)

    assert failed.draft == "Audit somehow."
    assert "intended result" in (failed.parse_error or "")
    assert thread.is_alive()

    controller.submit("submission-2", "Audit to produce evidence.")
    thread.join(timeout=1)
    assert results[0].argument.action == "Audit to produce evidence."


def test_veto_retry_restores_previous_draft() -> None:
    controller = WebHumanController(RecordingParser())
    first_results: list[ProposalResult] = []
    first = Thread(
        target=run_proposal,
        args=(controller, context_for(ActorId.ALIGN), first_results),
        daemon=True,
    )
    first.start()
    wait_for_status(controller, "waiting_human")
    controller.submit("submission-1", "Audit and brief the CEO.")
    first.join(timeout=1)

    veto_context = context_for(ActorId.ALIGN).model_copy(
        update={"veto_feedback": "The proposal combines two undertakings."}
    )
    retry_results: list[ProposalResult] = []
    retry = Thread(
        target=run_proposal,
        args=(controller, veto_context, retry_results),
        daemon=True,
    )
    retry.start()
    waiting = wait_for_status(controller, "waiting_human")

    assert waiting.draft == "Audit and brief the CEO."
    assert waiting.feedback == "The proposal combines two undertakings."

    controller.submit("submission-2", "Run only the audit.")
    retry.join(timeout=1)
    assert retry_results[0].argument.action == "Run only the audit."


def test_duplicate_submission_id_is_idempotent() -> None:
    controller = WebHumanController(RecordingParser())
    results: list[ProposalResult] = []
    thread = Thread(
        target=run_proposal,
        args=(controller, context_for(ActorId.ALIGN), results),
        daemon=True,
    )
    thread.start()
    wait_for_status(controller, "waiting_human")

    assert controller.submit("same-id", "Run an audit.")
    assert not controller.submit("same-id", "Run a different action.")
    thread.join(timeout=1)
    assert results[0].argument.action == "Run an audit."


def wait_for_status(controller, status, require_error=False):
    state = controller.snapshot()
    for _ in range(20):
        if state.status == status and (state.parse_error or not require_error):
            return state
        state = controller.wait_for_update(state.version, timeout=0.1)
    raise AssertionError(f"controller did not reach {status}")