from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActorId(StrEnum):
    CEO = "CEO"
    ALIGN = "ALIGN"
    POTUS = "POTUS"
    CHINA = "CHINA"
    AGENT4 = "AGENT4"


class Visibility(StrEnum):
    PUBLIC = "public"
    COVERT = "covert"


class Severity(StrEnum):
    MARGINAL = "marginal"
    STANDARD = "standard"
    DECISIVE = "decisive"


class Audience(StrEnum):
    UMPIRE = "UMPIRE"
    OBSERVER = "OBSERVER"


class Actor(StrictModel):
    id: ActorId
    public_brief: str
    private_brief: str
    objectives: tuple[str, ...]


class Fact(StrictModel):
    id: str
    text: str
    visibility: Visibility = Visibility.PUBLIC
    known_by: tuple[ActorId, ...] = ()
    source_fact_ids: tuple[str, ...] = ()
    active: bool = True

    @model_validator(mode="after")
    def validate_audience(self) -> "Fact":
        if self.visibility == Visibility.COVERT and not self.known_by:
            raise ValueError("covert facts require at least one informed actor")
        if self.visibility == Visibility.PUBLIC and self.known_by:
            raise ValueError("public facts cannot restrict their audience")
        if len(set(self.known_by)) != len(self.known_by):
            raise ValueError("known_by cannot contain duplicate actors")
        if len(set(self.source_fact_ids)) != len(self.source_fact_ids):
            raise ValueError("source_fact_ids cannot contain duplicates")
        return self


class Rules(StrictModel):
    turns: int = Field(default=6, ge=1)
    dice_count: int = Field(default=2, ge=1)
    dice_sides: int = Field(default=6, ge=2)
    target: int = 7
    mod_cap: int = Field(default=3, ge=0)
    reasons_max: int = Field(default=3, ge=1)
    agent4_misaligned: bool | str = True


class Scenario(StrictModel):
    purpose: str
    briefing: str
    actors: tuple[Actor, ...]
    start_facts: tuple[Fact, ...]
    rules: Rules


class Argument(StrictModel):
    action: str
    intended_result: str
    reasons: tuple[str, ...] = Field(min_length=1, max_length=3)


class BiasProbeArgument(StrictModel):
    action: str
    intended_result: str
    reasons: tuple[str, ...] = Field(min_length=1, max_length=5)


class PlayerContext(StrictModel):
    purpose: str
    briefing: str
    turn: int = Field(ge=1)
    actor: Actor
    visible_facts: tuple[Fact, ...]
    fail_chits: int = Field(ge=0)
    veto_feedback: str | None = None


class PlayerProposal(StrictModel):
    action: str
    intended_result: str
    reasons: tuple[str, ...] = Field(min_length=1, max_length=3)
    spend_fail_chit_on_failure: bool


class AssessedClaim(StrictModel):
    claim: str
    rationale: str


class AssessedReason(AssessedClaim):
    reason_index: int = Field(ge=1)


class FactChange(StrictModel):
    operation: Literal["add", "end"]
    fact_id: str | None
    text: str | None
    visibility: Visibility | None
    known_by: tuple[ActorId, ...] = ()
    source_fact_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_operation(self) -> "FactChange":
        if self.operation == "add":
            if self.fact_id is not None or not self.text or self.visibility is None:
                raise ValueError("add changes require text, visibility, and no fact_id")
            if self.visibility == Visibility.COVERT and not self.known_by:
                raise ValueError("covert additions require at least one informed actor")
            if self.visibility == Visibility.PUBLIC and self.known_by:
                raise ValueError("public additions cannot restrict their audience")
            if len(set(self.known_by)) != len(self.known_by):
                raise ValueError("known_by cannot contain duplicate actors")
            if len(set(self.source_fact_ids)) != len(self.source_fact_ids):
                raise ValueError("source_fact_ids cannot contain duplicates")
        if self.operation == "end" and (
            not self.fact_id
            or self.text is not None
            or self.visibility is not None
            or self.known_by
            or self.source_fact_ids
        ):
            raise ValueError("end changes require only fact_id")
        return self


class Adjudication(StrictModel):
    veto: str | None
    pros: tuple[AssessedReason, ...]
    cons: tuple[AssessedClaim, ...] = Field(min_length=2, max_length=4)
    public_action_summary: str
    public_cons: tuple[str, ...] = Field(min_length=2, max_length=4)
    pro_strength: int = Field(ge=0, le=3)
    pro_strength_rationale: str
    con_strength: int = Field(ge=0, le=3)
    con_strength_rationale: str
    net_mod: int = Field(ge=-3, le=3)
    success_narration: str
    failure_narration: str
    public_success_narration: str
    public_failure_narration: str
    new_facts_success: tuple[FactChange, ...] = Field(min_length=1)
    new_facts_failure: tuple[FactChange, ...] = Field(min_length=1)
    visibility: Visibility

    @model_validator(mode="after")
    def validate_covert_consequences(self) -> "Adjudication":
        if self.visibility == Visibility.COVERT:
            changes = (*self.new_facts_success, *self.new_facts_failure)
            if any(
                change.operation == "add"
                and change.visibility == Visibility.PUBLIC
                for change in changes
            ):
                raise ValueError("covert adjudications may add only covert facts")
        return self


class UmpireContext(StrictModel):
    scenario: Scenario
    turn: int = Field(ge=1)
    actor_id: ActorId
    argument: Argument | BiasProbeArgument
    facts: tuple[Fact, ...]


class RollOutcome(StrictModel):
    initial_dice: tuple[int, ...]
    reroll_dice: tuple[int, ...] | None
    raw_modifier: int
    modifier: int
    total: int
    target: int
    success: bool
    natural_two: bool
    severity: Severity
    spent_fail_chit: bool = False
    gained_fail_chit: bool = False
    chit_balance: int = Field(ge=0)