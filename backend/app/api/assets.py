from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models import AssetGroup

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/groups")
def list_asset_groups(_: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    groups = db.scalars(
        select(AssetGroup).options(selectinload(AssetGroup.assets)).order_by(AssetGroup.category, AssetGroup.name)
    ).all()
    return [
        {
            "id": group.id,
            "name": group.name,
            "slug": group.slug,
            "category": group.category,
            "region": group.region,
            "enabled": group.enabled,
            "assets": [
                {
                    "id": asset.id,
                    "symbol": asset.symbol,
                    "display_name": asset.display_name,
                    "market": asset.market,
                    "asset_type": asset.asset_type,
                    "role": asset.role,
                    "enabled": asset.enabled,
                }
                for asset in group.assets
            ],
        }
        for group in groups
    ]

