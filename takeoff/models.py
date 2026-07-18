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
    owner: ActorId | None = None
    active: bool = True

    @model_validator(mode="after")
    def validate_owner(self) -> "Fact":
        if self.visibility == Visibility.COVERT and self.owner is None:
            raise ValueError("covert facts require an owner")
        if self.visibility == Visibility.PUBLIC and self.owner is not None:
            raise ValueError("public facts cannot have an owner")
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

    @model_validator(mode="after")
    def validate_operation(self) -> "FactChange":
        if self.operation == "add" and (self.fact_id is not None or not self.text):
            raise ValueError("add changes require text and no fact_id")
        if self.operation == "end" and (not self.fact_id or self.text is not None):
            raise ValueError("end changes require fact_id and no text")
        return self


class Adjudication(StrictModel):
    veto: str | None
    pros: tuple[AssessedReason, ...]
    cons: tuple[AssessedClaim, ...] = Field(min_length=2, max_length=4)
    pro_strength: int = Field(ge=0, le=3)
    pro_strength_rationale: str
    con_strength: int = Field(ge=0, le=3)
    con_strength_rationale: str
    net_mod: int = Field(ge=-3, le=3)
    success_narration: str
    failure_narration: str
    new_facts_success: tuple[FactChange, ...] = Field(min_length=1)
    new_facts_failure: tuple[FactChange, ...] = Field(min_length=1)
    visibility: Visibility
    public_observation: str | None


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