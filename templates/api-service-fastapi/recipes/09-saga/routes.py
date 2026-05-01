# pyright: basic
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import and_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .models import InventoryItem, Order, PaymentAccount, SagaStep
    from .schemas import (
        InventoryCreate,
        OrderCreate,
        OrderOut,
        PaymentCreate,
        RecoverRequest,
        SagaStepOut,
    )
except ImportError:
    from database import get_db
    from models import InventoryItem, Order, PaymentAccount, SagaStep
    from schemas import (
        InventoryCreate,
        OrderCreate,
        OrderOut,
        PaymentCreate,
        RecoverRequest,
        SagaStepOut,
    )

router = APIRouter()

STEP_NAMES = ["reserve_inventory", "charge_payment", "confirm_shipment"]


def _get_order_or_404(db: Session, order_key: str):
    order = db.query(Order).filter(Order.order_key == order_key).first()
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


def _get_step(db: Session, order_id, step_name: str):
    step = (
        db.query(SagaStep)
        .filter(and_(SagaStep.order_id == order_id, SagaStep.step_name == step_name))
        .first()
    )
    if step is None:
        raise HTTPException(status_code=404, detail="saga step not found")
    return step


def _compensate(db: Session, order, completed_steps: list[str]) -> None:
    for step_name in reversed(completed_steps):
        if step_name == "charge_payment":
            payment = (
                db.query(PaymentAccount).filter(PaymentAccount.client_id == order.client_id).first()
            )
            if payment is not None:
                db.execute(
                    update(PaymentAccount)
                    .where(PaymentAccount.id == payment.id)
                    .values(
                        held_cents=PaymentAccount.held_cents - order.total_cents,
                        available_cents=PaymentAccount.available_cents + order.total_cents,
                        version=PaymentAccount.version + 1,
                    )
                )
        if step_name == "reserve_inventory":
            inventory = db.query(InventoryItem).filter(InventoryItem.sku == order.sku).first()
            if inventory is not None:
                db.execute(
                    update(InventoryItem)
                    .where(InventoryItem.id == inventory.id)
                    .values(
                        reserved_qty=InventoryItem.reserved_qty - order.quantity,
                        available_qty=InventoryItem.available_qty + order.quantity,
                        version=InventoryItem.version + 1,
                    )
                )
        db.execute(
            update(SagaStep)
            .where(and_(SagaStep.order_id == order.id, SagaStep.step_name == step_name))
            .values(
                compensation_attempt_count=SagaStep.compensation_attempt_count + 1,
                status="compensated",
                compensated_at=datetime.utcnow(),
            )
        )


@router.post("/inventory-items", status_code=201)
def create_inventory_item(payload: InventoryCreate, db: Session = Depends(get_db)):
    item = InventoryItem(sku=payload.sku, available_qty=payload.available_qty)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="duplicate sku") from exc
    return {"sku": item.sku, "available_qty": item.available_qty, "reserved_qty": item.reserved_qty}


@router.post("/payment-accounts", status_code=201)
def create_payment_account(payload: PaymentCreate, db: Session = Depends(get_db)):
    account = PaymentAccount(client_id=payload.client_id, available_cents=payload.available_cents)
    db.add(account)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="duplicate client_id") from exc
    return {
        "client_id": account.client_id,
        "available_cents": account.available_cents,
        "held_cents": account.held_cents,
    }


@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    inventory = db.query(InventoryItem).filter(InventoryItem.sku == payload.sku).first()
    payment = db.query(PaymentAccount).filter(PaymentAccount.client_id == payload.client_id).first()
    if inventory is None:
        raise HTTPException(status_code=404, detail="inventory not found")
    if payment is None:
        raise HTTPException(status_code=404, detail="payment account not found")

    order = Order(
        order_key=payload.order_key,
        client_id=payload.client_id,
        sku=payload.sku,
        quantity=payload.quantity,
        total_cents=payload.total_cents,
    )
    db.add(order)
    try:
        db.flush()
        for step_name in STEP_NAMES:
            db.add(SagaStep(order_id=order.id, step_name=step_name, status="pending"))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="duplicate order_key") from exc

    db.refresh(order)
    return order


@router.post("/orders/{order_key}/execute", response_model=OrderOut)
def execute_order(order_key: str, db: Session = Depends(get_db)):
    order = _get_order_or_404(db, order_key)
    if order.state in {"completed", "compensated"}:
        return order

    claim = cast(
        Any,
        db.execute(
            update(Order)
            .where(
                and_(Order.id == order.id, Order.version == order.version, Order.state == "pending")
            )
            .values(state="processing", version=Order.version + 1)
        ),
    )
    if claim.rowcount != 1:
        db.rollback()
        latest = _get_order_or_404(db, order_key)
        if latest.state in {"completed", "compensated"}:
            return latest
        raise HTTPException(status_code=409, detail="concurrent execution conflict")
    db.commit()

    order = _get_order_or_404(db, order_key)
    completed_steps: list[str] = []

    inventory = db.query(InventoryItem).filter(InventoryItem.sku == order.sku).first()
    if inventory is None:
        db.execute(
            update(Order)
            .where(Order.id == order.id)
            .values(
                state="compensated", failure_reason="inventory not found", version=Order.version + 1
            )
        )
        db.commit()
        raise HTTPException(status_code=422, detail="inventory not found")
    db.execute(
        update(SagaStep)
        .where(and_(SagaStep.order_id == order.id, SagaStep.step_name == "reserve_inventory"))
        .values(attempt_count=SagaStep.attempt_count + 1)
    )
    reserve = cast(
        Any,
        db.execute(
            update(InventoryItem)
            .where(InventoryItem.id == inventory.id)
            .where(InventoryItem.version == inventory.version)
            .where(InventoryItem.available_qty >= order.quantity)
            .values(
                reserved_qty=InventoryItem.reserved_qty + order.quantity,
                available_qty=InventoryItem.available_qty - order.quantity,
                version=InventoryItem.version + 1,
            )
        ),
    )
    if reserve.rowcount != 1:
        reason = "insufficient inventory or version conflict"
        db.execute(
            update(SagaStep)
            .where(and_(SagaStep.order_id == order.id, SagaStep.step_name == "reserve_inventory"))
            .values(status="failed", detail_text=reason)
        )
        db.execute(
            update(Order)
            .where(Order.id == order.id)
            .values(state="compensated", failure_reason=reason, version=Order.version + 1)
        )
        db.commit()
        raise HTTPException(status_code=422, detail=reason)
    db.execute(
        update(SagaStep)
        .where(and_(SagaStep.order_id == order.id, SagaStep.step_name == "reserve_inventory"))
        .values(status="done", executed_at=datetime.utcnow())
    )
    completed_steps.append("reserve_inventory")
    db.commit()

    payment = db.query(PaymentAccount).filter(PaymentAccount.client_id == order.client_id).first()
    if payment is None:
        _compensate(db, order, completed_steps)
        db.execute(
            update(Order)
            .where(Order.id == order.id)
            .values(
                state="compensated",
                failure_reason="payment account not found",
                version=Order.version + 1,
            )
        )
        db.commit()
        raise HTTPException(status_code=422, detail="payment account not found")
    db.execute(
        update(SagaStep)
        .where(and_(SagaStep.order_id == order.id, SagaStep.step_name == "charge_payment"))
        .values(attempt_count=SagaStep.attempt_count + 1)
    )
    charge = cast(
        Any,
        db.execute(
            update(PaymentAccount)
            .where(PaymentAccount.id == payment.id)
            .where(PaymentAccount.version == payment.version)
            .where(PaymentAccount.available_cents >= order.total_cents)
            .values(
                held_cents=PaymentAccount.held_cents + order.total_cents,
                available_cents=PaymentAccount.available_cents - order.total_cents,
                version=PaymentAccount.version + 1,
            )
        ),
    )
    if charge.rowcount != 1:
        reason = "insufficient funds or version conflict"
        db.execute(
            update(SagaStep)
            .where(and_(SagaStep.order_id == order.id, SagaStep.step_name == "charge_payment"))
            .values(status="failed", detail_text=reason)
        )
        _compensate(db, order, completed_steps)
        db.execute(
            update(Order)
            .where(Order.id == order.id)
            .values(state="compensated", failure_reason=reason, version=Order.version + 1)
        )
        db.commit()
        raise HTTPException(status_code=422, detail=reason)
    db.execute(
        update(SagaStep)
        .where(and_(SagaStep.order_id == order.id, SagaStep.step_name == "charge_payment"))
        .values(status="done", executed_at=datetime.utcnow())
    )
    completed_steps.append("charge_payment")
    db.commit()

    db.execute(
        update(SagaStep)
        .where(and_(SagaStep.order_id == order.id, SagaStep.step_name == "confirm_shipment"))
        .values(
            attempt_count=SagaStep.attempt_count + 1,
            status="done",
            executed_at=datetime.utcnow(),
        )
    )
    db.execute(
        update(Order)
        .where(Order.id == order.id)
        .values(state="completed", failure_reason=None, version=Order.version + 1)
    )
    db.commit()
    db.refresh(order)
    return order


@router.get("/orders/{order_key}", response_model=OrderOut)
def get_order(order_key: str, db: Session = Depends(get_db)):
    return _get_order_or_404(db, order_key)


@router.post("/orders/{order_key}/recover", response_model=OrderOut)
def recover_order(
    order_key: str,
    payload: RecoverRequest = Body(default_factory=RecoverRequest),
    db: Session = Depends(get_db),
):
    order = _get_order_or_404(db, order_key)
    if order.state != "processing":
        return order

    # Check timeout: order must have been stuck longer than timeout_seconds
    now = datetime.utcnow()
    if order.updated_at is not None:
        stuck_seconds = (now - order.updated_at).total_seconds()
        if stuck_seconds < payload.timeout_seconds:
            raise HTTPException(
                status_code=409,
                detail=f"order has only been processing for {int(stuck_seconds)}s, timeout is {payload.timeout_seconds}s",
            )

    # Conditional UPDATE with version guard to prevent racing with active execution
    claim = cast(
        Any,
        db.execute(
            update(Order)
            .where(
                and_(
                    Order.id == order.id,
                    Order.version == order.version,
                    Order.state == "processing",
                )
            )
            .values(state="pending", version=Order.version + 1)
        ),
    )
    if claim.rowcount != 1:
        db.rollback()
        return _get_order_or_404(db, order_key)

    db.commit()
    return _get_order_or_404(db, order_key)


@router.get("/orders/{order_key}/steps", response_model=list[SagaStepOut])
def get_order_steps(order_key: str, db: Session = Depends(get_db)):
    order = _get_order_or_404(db, order_key)
    return (
        db.query(SagaStep).filter(SagaStep.order_id == order.id).order_by(SagaStep.id.asc()).all()
    )
