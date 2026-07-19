from dataclasses import dataclass
from pathlib import Path
from secrets import token_urlsafe
from threading import Condition, Event, Lock, Thread
from time import monotonic
from typing import Callable

from takeoff.config import Settings
from takeoff.controllers import (
    HumanTurnParser,
    LlmController,
    ProposalResult,
    RoutingController,
)
from takeoff.engine import run_live_game
from takeoff.events import GameEvent, GameState
from takeoff.models import ActorId, PlayerContext
from takeoff.openrouter import ModelOutputError, OpenRouterClient
from takeoff.scenario import build_scenario
from takeoff.transcript import JsonlEventStore
from takeoff.umpire import LlmUmpire
from takeoff.web_projection import GameView, build_game_view


SESSION_INACTIVITY_TIMEOUT = 10 * 60


class GameExpiredError(RuntimeError):
    pass


@dataclass(frozen=True)
class HumanInputState:
    status: str
    version: int
    context: PlayerContext | None
    draft: str
    feedback: str | None
    parse_error: str | None


class WebHumanController:
    def __init__(self, parser: HumanTurnParser) -> None:
        self._parser = parser
        self._condition = Condition()
        self._status = "starting"
        self._version = 0
        self._context: PlayerContext | None = None
        self._draft = ""
        self._last_draft = ""
        self._feedback: str | None = None
        self._parse_error: str | None = None
        self._pending: tuple[str, str] | None = None
        self._submission_ids: set[str] = set()
        self._expired = False

    def propose(self, context: PlayerContext) -> ProposalResult:
        with self._condition:
            self._context = context
            self._status = "waiting_human"
            self._feedback = context.veto_feedback
            self._parse_error = None
            self._draft = self._last_draft if context.veto_feedback else ""
            self._advance()

        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._pending is not None or self._expired
                )
                if self._expired:
                    raise GameExpiredError("game expired due to inactivity")
                _, submission = self._pending or ("", "")
                self._pending = None
                self._status = "parsing"
                self._draft = submission
                self._parse_error = None
                self._advance()

            try:
                result = self._parser.parse(context, submission)
            except ModelOutputError as error:
                with self._condition:
                    if self._expired:
                        raise GameExpiredError(
                            "game expired due to inactivity"
                        ) from error
                    self._status = "waiting_human"
                    self._draft = submission
                    self._parse_error = str(error)
                    self._advance()
                continue

            with self._condition:
                if self._expired:
                    raise GameExpiredError("game expired due to inactivity")
                self._status = "running"
                self._last_draft = submission
                self._draft = ""
                self._parse_error = None
                self._advance()
            return result

    def submit(self, submission_id: str, text: str) -> bool:
        if not text.strip():
            raise ValueError("submission text is required")
        if not submission_id:
            raise ValueError("submission_id is required")
        with self._condition:
            if self._expired:
                raise GameExpiredError("game expired due to inactivity")
            if submission_id in self._submission_ids:
                return False
            if self._status != "waiting_human" or self._pending is not None:
                raise ValueError("the game is not waiting for this player")
            self._submission_ids.add(submission_id)
            self._pending = (submission_id, text)
            self._status = "parsing"
            self._draft = text
            self._advance()
            self._condition.notify()
            return True

    def expire(self) -> None:
        with self._condition:
            self._expired = True
            self._status = "expired"
            self._pending = None
            self._context = None
            self._draft = ""
            self._last_draft = ""
            self._feedback = None
            self._parse_error = None
            self._advance()

    def snapshot(self) -> HumanInputState:
        with self._condition:
            return self._snapshot()

    def wait_for_update(
        self, after_version: int, timeout: float | None = None
    ) -> HumanInputState:
        with self._condition:
            self._condition.wait_for(
                lambda: self._version > after_version,
                timeout=timeout,
            )
            return self._snapshot()

    def _snapshot(self) -> HumanInputState:
        return HumanInputState(
            status=self._status,
            version=self._version,
            context=self._context,
            draft=self._draft,
            feedback=self._feedback,
            parse_error=self._parse_error,
        )

    def _advance(self) -> None:
        self._version += 1
        self._condition.notify_all()


class GameSession:
    def __init__(
        self,
        token: str,
        human_actor: ActorId,
        human_controller: WebHumanController,
        run: Callable[[Callable[[GameEvent, GameState], object]], GameState],
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.token = token
        self.human_actor = human_actor
        self.human_controller = human_controller
        self._run = run
        self._clock = clock
        self._lock = Lock()
        self._events: list[GameEvent] = []
        self._state = GameState()
        self._event_version = 0
        self._status = "starting"
        self._error: str | None = None
        self._thread: Thread | None = None
        self._last_activity = clock()
        self._expired = False

    def start(self) -> None:
        self._thread = Thread(target=self._run_game, daemon=True)
        self._thread.start()

    def submit(self, submission_id: str, text: str) -> bool:
        accepted = self.human_controller.submit(submission_id, text)
        if accepted:
            self._touch()
        return accepted

    def is_inactive(self, now: float, timeout: float) -> bool:
        with self._lock:
            return now - self._last_activity >= timeout

    def expire(self) -> None:
        with self._lock:
            if self._expired:
                return
            self._expired = True
            self._events.clear()
            self._state = GameState()
            self._status = "expired"
            self._error = None
        self.human_controller.expire()

    def version(self) -> int:
        human = self.human_controller.snapshot()
        with self._lock:
            return self._event_version * 1_000_000 + human.version

    def view(self) -> GameView:
        human = self.human_controller.snapshot()
        with self._lock:
            state = self._state
            events = tuple(self._events)
            status = self._status
            event_version = self._event_version
            error = self._error
        if state.scenario is None:
            raise ValueError("game has not started")
        effective_status = status if status in {"completed", "failed"} else human.status
        return build_game_view(
            state=state,
            events=events,
            human_actor=self.human_actor,
            version=event_version * 1_000_000 + human.version,
            status=effective_status,
            feedback=human.feedback,
            parse_error=human.parse_error or error,
            draft=human.draft,
        )

    def _on_commit(self, event: GameEvent, state: GameState) -> None:
        with self._lock:
            if self._expired:
                raise GameExpiredError("game expired due to inactivity")
            self._events.append(event)
            self._state = state
            self._event_version += 1
            self._last_activity = self._clock()
            if self._status == "starting":
                self._status = "running"

    def _run_game(self) -> None:
        try:
            self._run(self._on_commit)
        except GameExpiredError:
            return
        except Exception as error:
            with self._lock:
                if self._expired:
                    return
                self._status = "failed"
                self._error = f"The game stopped: {type(error).__name__}."
                self._event_version += 1
        else:
            with self._lock:
                if self._expired:
                    return
                self._status = "completed"
                self._event_version += 1

    def _touch(self) -> None:
        with self._lock:
            if self._expired:
                raise GameExpiredError("game expired due to inactivity")
            self._last_activity = self._clock()


class SessionRegistry:
    def __init__(
        self,
        factory: Callable[[str, ActorId], GameSession],
        *,
        inactivity_timeout: float = SESSION_INACTIVITY_TIMEOUT,
        cleanup_interval: float = 30,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._factory = factory
        self._inactivity_timeout = inactivity_timeout
        self._cleanup_interval = cleanup_interval
        self._clock = clock
        self._lock = Lock()
        self._sessions: dict[str, GameSession] = {}
        self._stop = Event()
        self._reaper = Thread(target=self._reap_loop, daemon=True)
        self._reaper.start()

    def create(self, human_actor: ActorId) -> GameSession:
        token = token_urlsafe(24)
        session = self._factory(token, human_actor)
        with self._lock:
            self._sessions[token] = session
        session.start()
        return session

    def get(self, token: str) -> GameSession | None:
        with self._lock:
            return self._sessions.get(token)

    def expire_inactive(self) -> int:
        now = self._clock()
        with self._lock:
            expired = [
                (token, session)
                for token, session in self._sessions.items()
                if session.is_inactive(now, self._inactivity_timeout)
            ]
            for token, _ in expired:
                del self._sessions[token]
        for _, session in expired:
            session.expire()
        return len(expired)

    def _reap_loop(self) -> None:
        while not self._stop.wait(self._cleanup_interval):
            self.expire_inactive()


def production_session_factory(
    settings: Settings,
) -> Callable[[str, ActorId], GameSession]:
    def create(token: str, human_actor: ActorId) -> GameSession:
        human_parser = HumanTurnParser(
            OpenRouterClient(
                settings,
                model=settings.player_model,
                temperature=0.1,
                reasoning_effort=settings.player_reasoning_effort,
            )
        )
        human = WebHumanController(human_parser)
        llm = LlmController(
            OpenRouterClient(
                settings,
                model=settings.player_model,
                temperature=0.8,
                reasoning_effort=settings.player_reasoning_effort,
            )
        )
        umpire = LlmUmpire(
            OpenRouterClient(
                settings,
                model=settings.umpire_model,
                temperature=0.1,
                reasoning_effort=settings.umpire_reasoning_effort,
            )
        )
        controller = RoutingController(human_actor, human, llm)
        transcript = JsonlEventStore(Path("/tmp/takeoff") / f"{token}.jsonl")

        def run(on_commit):
            return run_live_game(
                build_scenario(),
                transcript,
                controller,
                umpire,
                write=lambda text: None,
                on_commit=on_commit,
            )

        return GameSession(token, human_actor, human, run)

    return create