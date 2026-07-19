from threading import Event

from fastapi.testclient import TestClient

from takeoff.controllers import ProposalResult
from takeoff.events import GameStarted, GameState, TurnStarted, reduce_event
from takeoff.models import ActorId, Argument
from takeoff.scenario import build_scenario
from takeoff.web import create_app
from takeoff.web_sessions import GameSession, SessionRegistry, WebHumanController


class EchoParser:
    def parse(self, context, submission):
        return ProposalResult(
            argument=Argument(
                action=submission,
                intended_result="Produce one result.",
                reasons=("One stated reason.",),
            ),
            attempts=1,
        )


def session_factory(completed: Event, clock=None):
    def factory(token, human_actor):
        human = WebHumanController(EchoParser())

        def run(on_commit):
            scenario = build_scenario(turns=1)
            game_id = __import__("uuid").uuid4()
            state = GameState()
            started = GameStarted(game_id=game_id, seq=1, scenario=scenario)
            state = reduce_event(state, started)
            on_commit(started, state)
            turn = TurnStarted(
                game_id=game_id,
                seq=2,
                turn=1,
                actor_order=tuple(ActorId),
            )
            state = reduce_event(state, turn)
            on_commit(turn, state)
            human.propose(
                __import__("takeoff.ledger", fromlist=["build_player_context"])
                .build_player_context(state, human_actor)
            )
            completed.set()
            return state

        if clock is None:
            return GameSession(token, human_actor, human, run)
        return GameSession(token, human_actor, human, run, clock=clock)

    return factory


def wait_for_waiting(client, token):
    for _ in range(30):
        response = client.get(f"/api/games/{token}")
        if response.status_code == 200 and response.json()["status"] == "waiting_human":
            return response.json()
    raise AssertionError("game did not wait for human")


def test_create_poll_and_submit_human_game() -> None:
    completed = Event()
    app = create_app(SessionRegistry(session_factory(completed)))
    client = TestClient(app)

    created = client.post("/api/games", json={"actor_id": "ALIGN"})
    assert created.status_code == 201
    token = created.json()["token"]
    assert created.json()["url"] == f"/game/{token}"

    view = wait_for_waiting(client, token)
    assert view["human_actor"] == "ALIGN"
    assert view["private_brief"]
    assert view["facts"]

    submitted = client.post(
        f"/api/games/{token}/proposal",
        json={"text": "Run a bounded audit.", "submission_id": "mobile-1"},
    )
    assert submitted.status_code == 202
    assert submitted.json() == {"accepted": True}
    assert completed.wait(timeout=1)

    duplicate = client.post(
        f"/api/games/{token}/proposal",
        json={"text": "Different text.", "submission_id": "mobile-1"},
    )
    assert duplicate.status_code == 202
    assert duplicate.json() == {"accepted": False}


def test_poll_version_unknown_token_and_out_of_turn_submission() -> None:
    app = create_app(SessionRegistry(session_factory(Event())))
    client = TestClient(app)
    token = client.post("/api/games", json={"actor_id": "CEO"}).json()["token"]
    view = wait_for_waiting(client, token)

    unchanged = client.get(
        f"/api/games/{token}", params={"after_version": view["version"]}
    )
    assert unchanged.status_code == 204
    assert client.get("/api/games/not-a-game").status_code == 404
    missing_game = client.get("/game/not-a-game")
    assert missing_game.status_code == 200
    assert "You will have to start a new game." in missing_game.text

    accepted = client.post(
        f"/api/games/{token}/proposal",
        json={"text": "Take one action.", "submission_id": "first"},
    )
    assert accepted.status_code == 202
    conflict = client.post(
        f"/api/games/{token}/proposal",
        json={"text": "Take another action.", "submission_id": "second"},
    )
    assert conflict.status_code == 409


def test_pages_and_api_set_privacy_headers() -> None:
    client = TestClient(create_app(SessionRegistry(session_factory(Event()))))

    index = client.get("/")
    health = client.get("/healthz")
    roles = client.get("/api/roles")

    assert index.status_code == 200
    assert "TAKEOFF" in index.text
    assert health.json() == {"status": "ok"}
    assert len(roles.json()["roles"]) == 5
    for response in (index, health, roles):
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-content-type-options"] == "nosniff"


def test_inactive_game_expires_and_returns_not_found() -> None:
    now = [1_000.0]
    clock = lambda: now[0]
    registry = SessionRegistry(
        session_factory(Event(), clock),
        inactivity_timeout=600,
        cleanup_interval=3_600,
        clock=clock,
    )
    client = TestClient(create_app(registry))
    token = client.post("/api/games", json={"actor_id": "ALIGN"}).json()["token"]
    wait_for_waiting(client, token)

    now[0] += 599
    assert registry.expire_inactive() == 0
    assert client.get(f"/api/games/{token}").status_code == 200

    now[0] += 1
    assert registry.expire_inactive() == 1
    assert registry.get(token) is None
    assert client.get(f"/api/games/{token}").status_code == 404
