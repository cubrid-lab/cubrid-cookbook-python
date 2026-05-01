# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import Customer, Order, OrderItem, Product
from schemas import (
    CustomerCreate,
    CustomerResponse,
    OrderCreate,
    OrderResponse,
    ProductCreate,
    ProductResponse,
)

router = APIRouter()


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate, db: Annotated[Session, Depends(get_db)]
) -> CustomerResponse:
    customer = Customer(name=payload.name, email=str(payload.email))
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    db.refresh(customer)
    return CustomerResponse.model_validate(customer)


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, db: Annotated[Session, Depends(get_db)]) -> CustomerResponse:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return CustomerResponse.model_validate(customer)


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate, db: Annotated[Session, Depends(get_db)]
) -> ProductResponse:
    product = Product(name=payload.name, price=payload.price, stock=payload.stock)
    db.add(product)
    db.commit()
    db.refresh(product)
    return ProductResponse.model_validate(product)


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Annotated[Session, Depends(get_db)]) -> ProductResponse:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductResponse.model_validate(product)


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, db: Annotated[Session, Depends(get_db)]) -> OrderResponse:
    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    items_to_create: list[OrderItem] = []
    total = 0
    for item in payload.items:
        product = db.get(Product, item.product_id)
        if product is None:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        if product.stock < item.quantity:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient stock")

        new_stock = product.stock - item.quantity
        result = cast(
            CursorResult[tuple[object, ...]],
            db.execute(
                update(Product)
                .where(Product.id == item.product_id, Product.version == product.version)
                .values(stock=new_stock, version=product.version + 1)
            ),
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Concurrent update detected. Please retry.",
            )

        unit_price = product.price
        total += unit_price * item.quantity
        items_to_create.append(
            OrderItem(product_id=item.product_id, quantity=item.quantity, unit_price=unit_price)
        )

    order = Order(customer_id=payload.customer_id, status="confirmed", total=total)
    order.items = items_to_create
    db.add(order)
    db.commit()

    stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    created_order = db.scalar(stmt)
    if created_order is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Order not found"
        )
    return OrderResponse.model_validate(created_order)


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Annotated[Session, Depends(get_db)]) -> OrderResponse:
    stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    order = db.scalar(stmt)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderResponse.model_validate(order)


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: int, db: Annotated[Session, Depends(get_db)]) -> OrderResponse:
    stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    order = db.scalar(stmt)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status == "cancelled":
        return OrderResponse.model_validate(order)

    for item in order.items:
        product = db.get(Product, item.product_id)
        if product is None:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        result = cast(
            CursorResult[tuple[object, ...]],
            db.execute(
                update(Product)
                .where(Product.id == item.product_id, Product.version == product.version)
                .values(stock=product.stock + item.quantity, version=product.version + 1)
            ),
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Concurrent update detected. Please retry.",
            )

    order.status = "cancelled"
    db.add(order)
    db.commit()
    refreshed = db.scalar(stmt)
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Order not found"
        )
    return OrderResponse.model_validate(refreshed)
