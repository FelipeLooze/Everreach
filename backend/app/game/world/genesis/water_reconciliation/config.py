from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReconciliationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    water_version: Literal[2] = 2
    max_domains_per_revision: int = Field(default=8, ge=1, le=16)
    max_evidence_per_revision: int = Field(default=16, ge=1, le=32)
    max_transfers_per_revision: int = Field(default=16, ge=1, le=32)
    max_event_rows: int = Field(default=128, ge=1, le=512)
    max_payload_bytes: int = Field(default=1_048_576, ge=4096, le=4_194_304)
    required_probe_spacing_m: int = Field(default=2, ge=1, le=1000)
    ocean_reference_component_ids: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("water_version", mode="before")
    @classmethod
    def integer_version(cls, v):
        if type(v) is not int:
            raise ValueError("W2 needs an explicit integer version")
        return v


class TransferIntent(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    transfer_id: str = Field(min_length=1, max_length=128)
    source_node: int = Field(ge=0)
    target_node: int | None = Field(default=None, ge=0)
    source_account: str = Field(min_length=1, max_length=240)
    target_account: str = Field(default="unlocalized:channel", min_length=1, max_length=240)
    amount_liters: int = Field(ge=0)
    evidence_keys: list[str] = Field(default_factory=list, max_length=32)
    coast_evidence_key: str | None = None


class RevisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    operation_id: str = Field(min_length=1, max_length=128)
    logical_minute: int = Field(ge=0, le=2**62)
    expected_heads: dict[str, str] = Field(min_length=1, max_length=16)
    evidence_keys: list[str] = Field(default_factory=list, max_length=32)
    transfers: list[TransferIntent] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def unique_addresses(self):
        if any(not k.isdigit() or str(int(k)) != k for k in self.expected_heads):
            raise ValueError("W2 domain keys must be canonical H1 node numbers")
        if len({t.transfer_id for t in self.transfers}) != len(self.transfers):
            raise ValueError("Duplicated W2 transfer intent")
        return self

    def canonical(self):
        value = self.model_dump()
        value["evidence_keys"] = sorted(set(value["evidence_keys"]))
        value["transfers"].sort(key=lambda t: t["transfer_id"])
        for t in value["transfers"]:
            t["evidence_keys"] = sorted(set(t["evidence_keys"]))
        return value
