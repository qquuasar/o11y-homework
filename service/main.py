import os
import time
from datetime import datetime
from decimal import Decimal
from enum import Enum

from fastapi import FastAPI, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Enum as SqlEnum, ForeignKey, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
)

# -------------------------
#     Метрики Prometheus
# -------------------------
REQUEST_COUNT        = Counter("app_requests_total", "Total HTTP requests", ["method", "endpoint"])
REQUEST_LATENCY      = Histogram("app_request_latency_seconds", "Latency in seconds", ["endpoint"])
ORDERS_CREATED       = Counter("orders_created_total", "Total orders created")
ORDERS_PAID          = Counter("orders_paid_total", "Total orders paid")
ORDER_VALUE_HIST     = Histogram("order_value_histogram", "Histogram of order total values")
PRODUCT_STOCK_GAUGE  = Gauge("product_stock", "Stock level for each product", ["product_id"])  # labelled by product id

# -------------------------
#       Database Setup
# -------------------------
DB_USER = os.getenv("POSTGRES_USER", "user")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "pass")
DB_NAME = os.getenv("POSTGRES_DB", "o11y")
DB_HOST = os.getenv("DB_HOST", "db")
DB_URL  = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"

engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -------------------------
#       ORM Models
# -------------------------
class OrderStatus(str, Enum):
    pending = "pending"
    paid = "paid"
    cancelled = "cancelled"

class Product(Base):
    __tablename__ = "products"
    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    description = Column(String, default="")
    price       = Column(Numeric(10, 2), nullable=False)
    stock       = Column(Integer, default=0)
    
    items       = relationship("OrderItem", back_populates="product")

class Order(Base):
    __tablename__ = "orders"
    id           = Column(Integer, primary_key=True, index=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    total_amount = Column(Numeric(12,2), default=0)
    status       = Column(SqlEnum(OrderStatus), default=OrderStatus.pending)

    items        = relationship("OrderItem", back_populates="order")

class OrderItem(Base):
    __tablename__ = "order_items"
    id          = Column(Integer, primary_key=True, index=True)
    order_id    = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id  = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity    = Column(Integer, nullable=False)
    unit_price  = Column(Numeric(10,2), nullable=False)

    order       = relationship("Order", back_populates="items")
    product     = relationship("Product", back_populates="items")

# Create tables
Base.metadata.create_all(bind=engine)

# -------------------------
#     Pydantic Schemas
# -------------------------
class ProductCreate(BaseModel):
    name: str
    description: str
    price: Decimal
    stock: int

class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = None
    stock: int | None = None

class ProductOut(BaseModel):
    id: int
    name: str
    description: str
    price: Decimal
    stock: int

    class Config:
        orm_mode = True

class OrderItemIn(BaseModel):
    product_id: int
    quantity: int

class OrderItemOut(BaseModel):
    product_id: int
    quantity: int
    unit_price: Decimal

    class Config:
        orm_mode = True

class OrderOut(BaseModel):
    id: int
    created_at: datetime
    total_amount: Decimal
    status: OrderStatus
    items: list[OrderItemOut]

    class Config:
        orm_mode = True

class OrderCreate(BaseModel):
    items: list[OrderItemIn]

# -------------------------
#       FastAPI App
# -------------------------
app = FastAPI(title="Cat Food Store (o11y)")

# Dependency: DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Metrics middleware
@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = time.time()
    response = await call_next(request)
    latency = time.time() - start
    REQUEST_COUNT.labels(request.method, request.url.path).inc()
    REQUEST_LATENCY.labels(request.url.path).observe(latency)
    return response

# -------------------------
#       Product Endpoints
# -------------------------
@app.get("/products", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    # Update stock gauge
    for p in products:
        PRODUCT_STOCK_GAUGE.labels(product_id=str(p.id)).set(p.stock)
    return products

@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    PRODUCT_STOCK_GAUGE.labels(product_id=str(product.id)).set(product.stock)
    return product

@app.post("/products", response_model=ProductOut, status_code=201)
def create_product(prod: ProductCreate, db: Session = Depends(get_db)):
    product = Product(**prod.dict())
    db.add(product)
    db.commit()
    db.refresh(product)
    PRODUCT_STOCK_GAUGE.labels(product_id=str(product.id)).set(product.stock)
    return product

@app.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, upd: ProductUpdate, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in upd.dict(exclude_none=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    PRODUCT_STOCK_GAUGE.labels(product_id=str(product.id)).set(product.stock)
    return product

@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.stock > 0:
        raise HTTPException(status_code=400, detail="Cannot delete product with stock > 0")
    db.delete(product)
    db.commit()
    PRODUCT_STOCK_GAUGE.remove(product_id=str(product.id))
    return Response(status_code=204)

# -------------------------
#        Order Endpoints
# -------------------------
@app.post("/orders", response_model=OrderOut, status_code=201)
def create_order(order_in: OrderCreate, db: Session = Depends(get_db)):
    # Проверяем наличие товара
    total = Decimal(0)
    order = Order()
    db.add(order)
    db.flush()  # получает order.id

    items_out: list[OrderItem] = []
    for itm in order_in.items:
        product = db.get(Product, itm.product_id)
        if not product or product.stock < itm.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for product {itm.product_id}")
        line_total = Decimal(product.price) * itm.quantity
        total += line_total
        product.stock -= itm.quantity
        db.add(product)

        oi = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=itm.quantity,
            unit_price=product.price,
        )
        db.add(oi)
        items_out.append(oi)
    
    order.total_amount = total
    ORDERS_CREATED.inc()
    ORDER_VALUE_HIST.observe(float(total))
    db.commit()
    db.refresh(order)
    # Обновляем метрики stock
    for oi in items_out:
        PRODUCT_STOCK_GAUGE.labels(product_id=str(oi.product_id)).set((db.get(Product, oi.product_id)).stock)
    return OrderOut(
        id=order.id,
        created_at=order.created_at,
        total_amount=order.total_amount,
        status=order.status,
        items=[OrderItemOut(product_id=oi.product_id, quantity=oi.quantity, unit_price=oi.unit_price) for oi in items_out]
    )

@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.put("/orders/{order_id}/pay", response_model=OrderOut)
def pay_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=400, detail="Order cannot be paid")
    order.status = OrderStatus.paid
    ORDERS_PAID.inc()
    db.commit()
    db.refresh(order)
    return order

# -------------------------
#      Метрики endpoint
# -------------------------
@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
