from pydantic import BaseModel, Field

from backend.app.db.models import Physician


class PhysicianRead(BaseModel):
    id: str
    npi: str
    firstName: str
    lastName: str
    specialty: str
    affiliation: str
    city: str
    state: str
    icd10ClaimVolume: dict[str, int]
    totalNSCLCClaims: int
    volumeTier: str
    email: str
    boardCertified: bool

    @classmethod
    def from_model(cls, physician: Physician) -> "PhysicianRead":
        return cls(
            id=physician.id,
            npi=physician.npi,
            firstName=physician.first_name,
            lastName=physician.last_name,
            specialty=physician.specialty,
            affiliation=physician.affiliation,
            city=physician.city,
            state=physician.state,
            icd10ClaimVolume=physician.icd10_claim_volume,
            totalNSCLCClaims=physician.total_nsclc_claims,
            volumeTier=physician.volume_tier,
            email=physician.email,
            boardCertified=physician.board_certified,
        )


class PhysicianFiltersApplied(BaseModel):
    specialty: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    icd10Codes: list[str] = Field(default_factory=list)
    volumeThreshold: str | None = None
    boardCertified: bool | None = None


class PhysicianListResponse(BaseModel):
    count: int
    filtersApplied: PhysicianFiltersApplied
    physicians: list[PhysicianRead]
