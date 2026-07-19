FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock Readme.md ./
COPY takeoff ./takeoff
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10001 takeoff
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/takeoff /app/takeoff
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER takeoff
EXPOSE 8080
CMD ["takeoff-web"]