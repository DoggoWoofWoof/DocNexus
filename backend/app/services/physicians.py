from collections.abc import Iterable, Sequence

from sqlmodel import Session, select

from backend.app.db.models import Physician
from backend.app.schemas.physician import PhysicianFiltersApplied, PhysicianRead


VOLUME_RANK = {"low": 1, "high": 2, "very_high": 3}

REGION_STATES = {
    "northeast": {"CT", "MA", "ME", "NH", "NJ", "NY", "PA", "RI", "VT"},
    "west": {"AK", "AZ", "CA", "CO", "HI", "ID", "MT", "NV", "NM", "OR", "UT", "WA", "WY"},
    "south": {"AL", "AR", "DC", "DE", "FL", "GA", "KY", "LA", "MD", "MS", "NC", "OK", "SC", "TN", "TX", "VA", "WV"},
    "midwest": {"IA", "IL", "IN", "KS", "MI", "MN", "MO", "ND", "NE", "OH", "SD", "WI"},
}


def _normalize_values(values: Sequence[str] | None, *, upper: bool = False) -> list[str]:
    if not values:
        return []

    normalized: list[str] = []
    for value in values:
        parts = [part.strip() for part in value.split(",")]
        for part in parts:
            if not part:
                continue
            normalized.append(part.upper() if upper else part.lower())
    return normalized


def _specialty_matches(physician_specialty: str, requested: Iterable[str]) -> bool:
    specialty = physician_specialty.lower()
    for term in requested:
        if term in specialty:
            return True
        if term in {"oncologist", "oncologists", "oncology"} and "oncology" in specialty:
            return True
    return False


def _icd10_matches(physician: Physician, codes: Iterable[str]) -> bool:
    for code in codes:
        if physician.icd10_claim_volume.get(code, 0) > 0:
            return True
    return False


def _volume_matches(physician: Physician, threshold: str | None) -> bool:
    if not threshold:
        return True

    normalized = threshold.lower()
    if normalized not in VOLUME_RANK:
        return True

    return VOLUME_RANK.get(physician.volume_tier, 0) >= VOLUME_RANK[normalized]


def _expand_regions(regions: list[str]) -> set[str]:
    states: set[str] = set()
    for region in regions:
        states.update(REGION_STATES.get(region, set()))
    return states


def list_physicians(
    session: Session,
    *,
    specialty: Sequence[str] | None = None,
    state: Sequence[str] | None = None,
    region: Sequence[str] | None = None,
    icd10_codes: Sequence[str] | None = None,
    volume_threshold: str | None = None,
    board_certified: bool | None = None,
) -> tuple[list[PhysicianRead], PhysicianFiltersApplied]:
    specialties = _normalize_values(specialty)
    states = set(_normalize_values(state, upper=True))
    regions = _normalize_values(region)
    states.update(_expand_regions(regions))
    codes = _normalize_values(icd10_codes, upper=True)

    physicians = session.exec(select(Physician).order_by(Physician.total_nsclc_claims.desc())).all()

    filtered: list[Physician] = []
    for physician in physicians:
        if specialties and not _specialty_matches(physician.specialty, specialties):
            continue
        if states and physician.state.upper() not in states:
            continue
        if codes and not _icd10_matches(physician, codes):
            continue
        if not _volume_matches(physician, volume_threshold):
            continue
        if board_certified is not None and physician.board_certified != board_certified:
            continue
        filtered.append(physician)

    filters = PhysicianFiltersApplied(
        specialty=specialties,
        states=sorted(states),
        regions=regions,
        icd10Codes=codes,
        volumeThreshold=volume_threshold,
        boardCertified=board_certified,
    )

    return [PhysicianRead.from_model(physician) for physician in filtered], filters
