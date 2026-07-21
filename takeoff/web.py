from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from takeoff.config import Settings
from takeoff.models import ActorId
from takeoff.scenario import build_scenario
from takeoff.web_sessions import (
    SessionRegistry,
    production_session_factory,
)


STATIC_DIR = Path(__file__).with_name("static")

ROLE_LABELS = {
    ActorId.CEO: "OpenBrain CEO",
    ActorId.ALIGN: "Alignment Lead",
    ActorId.POTUS: "US President & NSC",
    ActorId.CHINA: "DeepCent Leadership",
    ActorId.AGENT4: "Agent-4",
}


class CreateGameRequest(BaseModel):
    actor_id: ActorId


class ProposalRequest(BaseModel):
    text: str
    submission_id: str


def create_app(registry: SessionRegistry) -> FastAPI:
    app = FastAPI(title="TAKEOFF", docs_url=None, redoc_url=None)
    app.state.registry = registry
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def privacy_headers(request, call_next):
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/game/{token}")
    def game_page(token: str) -> FileResponse:
        return FileResponse(STATIC_DIR / "game.html")

    @app.get("/api/roles")
    def roles() -> dict[str, object]:
        scenario = build_scenario()
        return {
            "purpose": scenario.purpose,
            "briefing": scenario.briefing,
            "mechanics": {
                "turns": scenario.rules.turns,
                "target": scenario.rules.target,
                "reasons_max": scenario.rules.reasons_max,
            },
            "roles": [
                {
                    "id": actor.id.value,
                    "label": ROLE_LABELS[actor.id],
                    "brief": actor.public_brief,
                }
                for actor in scenario.actors
            ],
        }

    @app.post("/api/games", status_code=201)
    def create_game(request: CreateGameRequest) -> dict[str, str]:
        session = registry.create(request.actor_id)
        return {"token": session.token, "url": f"/game/{session.token}"}

    @app.get("/api/games/{token}")
    def game_view(
        token: str,
        after_version: int | None = Query(default=None, ge=0),
    ) -> Response:
        session = registry.get(token)
        if session is None:
            raise HTTPException(status_code=404, detail="Game not found or expired.")
        version = session.version()
        if after_version is not None and after_version == version:
            return Response(status_code=204)
        try:
            view = session.view()
        except ValueError:
            return JSONResponse(
                status_code=202,
                content={"version": version, "status": "starting"},
            )
        return JSONResponse(content=view.model_dump(mode="json"))

    @app.post("/api/games/{token}/proposal", status_code=202)
    def submit_proposal(token: str, request: ProposalRequest) -> dict[str, object]:
        session = registry.get(token)
        if session is None:
            raise HTTPException(status_code=404, detail="Game not found or expired.")
        try:
            accepted = session.submit(request.submission_id, request.text)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"accepted": accepted}

    return app


def create_production_app() -> FastAPI:
    settings = Settings.from_env()
    registry = SessionRegistry(production_session_factory(settings))
    return create_app(registry)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "takeoff.web:create_production_app",
        factory=True,
        host="0.0.0.0",
        port=8080,
        workers=1,
    )
