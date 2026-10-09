from collections.abc import Sequence

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.models import Tariff
from app.schemas.tariff import TariffRead
from app.services.tariffs import list_tariffs

router = APIRouter()


@router.get("", response_model=list[TariffRead])
async def get_tariffs(session: SessionDep) -> Sequence[Tariff]:
    return await list_tariffs(session)
