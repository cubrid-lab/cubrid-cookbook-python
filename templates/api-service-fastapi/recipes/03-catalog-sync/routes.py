# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import CatalogItem, SyncRun, utc_now
from schemas import CatalogItemResponse, CatalogSyncRequest, SyncRunResponse

router = APIRouter(prefix="/catalog")


@router.post("/sync", response_model=SyncRunResponse)
def sync_catalog(
    payload: CatalogSyncRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SyncRunResponse:
    run = SyncRun(source=payload.source, status="running", total_rows=len(payload.items))
    db.add(run)
    db.flush()

    for item_payload in payload.items:
        existing = db.scalar(
            select(CatalogItem).where(CatalogItem.external_sku == item_payload.external_sku)
        )

        if existing is not None:
            _ = db.execute(
                update(CatalogItem)
                .where(CatalogItem.id == existing.id)
                .values(
                    name=item_payload.name,
                    price=item_payload.price,
                    available=item_payload.available,
                    source_version=CatalogItem.source_version + 1,
                    last_synced_at=utc_now(),
                )
            )
            run.updated_cnt += 1
            continue

        nested = db.begin_nested()
        try:
            item = CatalogItem(
                external_sku=item_payload.external_sku,
                name=item_payload.name,
                price=item_payload.price,
                available=item_payload.available,
                source_version=1,
                last_synced_at=utc_now(),
            )
            db.add(item)
            db.flush()
            nested.commit()
            run.created_cnt += 1
        except IntegrityError:
            nested.rollback()
            existing = db.scalar(
                select(CatalogItem).where(CatalogItem.external_sku == item_payload.external_sku)
            )
            if existing is not None:
                _ = db.execute(
                    update(CatalogItem)
                    .where(CatalogItem.id == existing.id)
                    .values(
                        name=item_payload.name,
                        price=item_payload.price,
                        available=item_payload.available,
                        source_version=CatalogItem.source_version + 1,
                        last_synced_at=utc_now(),
                    )
                )
                run.updated_cnt += 1
            else:
                run.failed_cnt += 1
    run.status = "completed"
    run.finished_at = utc_now()
    db.add(run)
    db.commit()
    db.refresh(run)
    return SyncRunResponse.model_validate(run)


@router.get("/items", response_model=list[CatalogItemResponse])
def list_catalog_items(
    *,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Annotated[Session, Depends(get_db)],
) -> list[CatalogItemResponse]:
    stmt = select(CatalogItem).order_by(CatalogItem.id.asc()).offset(skip).limit(limit)
    items = db.scalars(stmt).all()
    return [CatalogItemResponse.model_validate(item) for item in items]


@router.get("/items/{item_id}", response_model=CatalogItemResponse)
def get_catalog_item(item_id: int, db: Annotated[Session, Depends(get_db)]) -> CatalogItemResponse:
    item = db.get(CatalogItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog item not found")
    return CatalogItemResponse.model_validate(item)


@router.get("/sync-runs", response_model=list[SyncRunResponse])
def list_sync_runs(
    *,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Annotated[Session, Depends(get_db)],
) -> list[SyncRunResponse]:
    stmt = select(SyncRun).order_by(SyncRun.id.desc()).offset(skip).limit(limit)
    runs = db.scalars(stmt).all()
    return [SyncRunResponse.model_validate(run) for run in runs]


@router.get("/sync-runs/{run_id}", response_model=SyncRunResponse)
def get_sync_run(run_id: int, db: Annotated[Session, Depends(get_db)]) -> SyncRunResponse:
    run = db.get(SyncRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync run not found")
    return SyncRunResponse.model_validate(run)
