from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..core.redops import RedOpsService

router = APIRouter(prefix="/api/reference", tags=["reference"],
                   dependencies=[Depends(get_current_user)])

_service = RedOpsService()


@router.get("/known-ids")
def known_ids(search: str | None = None, limit: int = 100, offset: int = 0):
    """The apps.json catalogue of well-known first-party application IDs."""
    apps = _service.reference_known_ids()
    flat = []
    for entry in apps:
        for name, appid in entry.items():
            flat.append({"name": name, "appId": appid})
    if search:
        s = search.lower()
        flat = [a for a in flat if s in a["name"].lower() or s in a["appId"].lower()]
    total = len(flat)
    return {"total": total, "items": flat[offset:offset + limit]}


@router.get("/interest/categories")
def interest_categories():
    return _service.reference_interest_categories()


@router.get("/interest")
def interest(category: str | None = None):
    return _service.reference_interest(category)
