from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.events import EventsBatch, PurchaseIn
from app.services import events_service
from app.services.runtime import runtime

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", status_code=202)
async def ingest(batch: EventsBatch, db: AsyncSession = Depends(get_db)):
    n = await events_service.record(db, batch.events)
    return {"accepted": n}


@router.post("/purchase")
async def purchase(p: PurchaseIn, db: AsyncSession = Depends(get_db)):
    if runtime.catalog is None:
        raise HTTPException(503, "catalog not loaded")
    c = runtime.catalog
    prices = {
        int(i["product_id"]): float(c.price[c.id_to_pos[int(i["product_id"])]])
        for i in p.items
        if int(i["product_id"]) in c.id_to_pos
    }
    if not prices:
        raise HTTPException(422, "no valid products")
    return await events_service.purchase(db, p, prices)
