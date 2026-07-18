import json
import os
from pathlib import Path

from pydantic import ValidationError

from takeoff.events import EVENT_ADAPTER, GameEvent


class JsonlEventStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: GameEvent) -> None:
        payload = EVENT_ADAPTER.dump_json(event).decode("utf-8")
        with self.path.open("a", encoding="utf-8") as transcript:
            transcript.write(payload)
            transcript.write("\n")
            transcript.flush()
            os.fsync(transcript.fileno())

    def load(self) -> list[GameEvent]:
        if not self.path.exists():
            return []

        events: list[GameEvent] = []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                events.append(EVENT_ADAPTER.validate_json(line))
            except (ValidationError, json.JSONDecodeError) as error:
                is_last_line = index == len(lines)
                if is_last_line and not line.rstrip().endswith("}"):
                    break
                raise ValueError(
                    f"invalid transcript event at line {index}: {error}"
                ) from error
        return events