from fastapi import APIRouter

from api.deps import OrgDep

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("")
async def list_budgets(org: OrgDep) -> list:
    raise NotImplementedError


@router.post("", status_code=201)
async def create_budget(org: OrgDep) -> dict:
    raise NotImplementedError


@router.patch("/{budget_id}")
async def update_budget(budget_id: str, org: OrgDep) -> dict:
    raise NotImplementedError


@router.delete("/{budget_id}", status_code=204)
async def delete_budget(budget_id: str, org: OrgDep) -> None:
    raise NotImplementedError
