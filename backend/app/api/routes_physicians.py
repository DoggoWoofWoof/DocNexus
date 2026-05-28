from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from backend.app.db.session import get_session
from backend.app.schemas.physician import PhysicianListResponse
from backend.app.services.physicians import list_physicians


router = APIRouter(prefix="/physicians", tags=["physicians"])


@router.get("", response_model=PhysicianListResponse)
def get_physicians(
    specialty: Annotated[
        list[str] | None,
        Query(description="Specialty terms. Accepts repeated params or comma-separated values."),
    ] = None,
    state: Annotated[
        list[str] | None,
        Query(description="Two-letter state codes. Accepts repeated params or comma-separated values."),
    ] = None,
    region: Annotated[
        list[str] | None,
        Query(description="Named regions such as northeast, west, south, or midwest."),
    ] = None,
    icd10_codes: Annotated[
        list[str] | None,
        Query(description="ICD-10 codes. Accepts repeated params or comma-separated values."),
    ] = None,
    volume_threshold: Annotated[
        str | None,
        Query(description="Minimum tier: low, high, or very_high."),
    ] = None,
    board_certified: Annotated[
        bool | None,
        Query(description="Optional board certification filter."),
    ] = None,
    session: Session = Depends(get_session),
) -> PhysicianListResponse:
    physicians, filters = list_physicians(
        session,
        specialty=specialty,
        state=state,
        region=region,
        icd10_codes=icd10_codes,
        volume_threshold=volume_threshold,
        board_certified=board_certified,
    )
    return PhysicianListResponse(
        count=len(physicians),
        filtersApplied=filters,
        physicians=physicians,
    )
