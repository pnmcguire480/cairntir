from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    id: str
    topic: str
    choice: str
    supersedes_id: str | None = None


class DecisionLog:
    def __init__(self) -> None:
        self._rows: list[Decision] = []

    def record(
        self, id: str, topic: str, choice: str, supersedes_id: str | None = None
    ) -> Decision:
        if not id or not topic or not choice or any(row.id == id for row in self._rows):
            raise ValueError("invalid or duplicate decision")
        if supersedes_id is not None:
            prior = next((row for row in self._rows if row.id == supersedes_id), None)
            if prior is None or prior.topic != topic:
                raise ValueError("superseded decision must exist in the same topic")
            if any(row.supersedes_id == supersedes_id for row in self._rows):
                raise ValueError("decision is already superseded")
        decision = Decision(id, topic, choice, supersedes_id)
        self._rows.append(decision)
        return decision

    def history(self, topic: str) -> tuple[Decision, ...]:
        return tuple(row for row in self._rows if row.topic == topic)

    def current(self, topic: str) -> tuple[Decision, ...]:
        superseded = set()
        return tuple(row for row in self._rows if row.topic == topic and row.id not in superseded)
