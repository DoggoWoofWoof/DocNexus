from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


class Physician(SQLModel, table=True):
    __tablename__ = "physicians"

    id: str = Field(primary_key=True)
    npi: str = Field(index=True, unique=True)
    first_name: str = Field(index=True)
    last_name: str = Field(index=True)
    specialty: str = Field(index=True)
    affiliation: str
    city: str
    state: str = Field(index=True, min_length=2, max_length=2)
    icd10_claim_volume: dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    total_nsclc_claims: int = Field(index=True)
    volume_tier: str = Field(index=True)
    email: str
    board_certified: bool = True

    @classmethod
    def from_seed_row(cls, row: dict[str, Any]) -> "Physician":
        return cls(
            id=row["id"],
            npi=row["npi"],
            first_name=row["firstName"],
            last_name=row["lastName"],
            specialty=row["specialty"],
            affiliation=row["affiliation"],
            city=row["city"],
            state=row["state"],
            icd10_claim_volume=row["icd10ClaimVolume"],
            total_nsclc_claims=row["totalNSCLCClaims"],
            volume_tier=row["volumeTier"],
            email=row["email"],
            board_certified=row["boardCertified"],
        )


class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"

    id: str = Field(primary_key=True)
    type: str = Field(index=True)
    filename: str
    mime_type: str
    local_path: str
    source_agent: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
