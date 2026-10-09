from contextlib import asynccontextmanager
from typing import List

import redis
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cache
from app.database import engine, get_db
from app.models import Base, Invoice
from app.rate_limiter import rate_limit
from app.schemas import InvoiceCreate, InvoiceOut, InvoiceUpdate


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # create tables on startup if missing
    yield


app = FastAPI(title="GuardianGate", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}  # not rate limited, so Docker/monitors can ping freely


@app.post("/invoices", response_model=InvoiceOut, status_code=201, dependencies=[Depends(rate_limit)])
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db), r: redis.Redis = Depends(cache.get_redis)):
    invoice = Invoice(**payload.model_dump())
    db.add(invoice)
    try:
        db.commit()                    # transaction: all-or-nothing
    except IntegrityError:
        db.rollback()                  # undo on failure (duplicate invoice_number)
        raise HTTPException(status_code=409, detail="Invoice number already exists")
    db.refresh(invoice)
    cache.invalidate_lists(r)          # list pages are now stale
    return invoice


@app.get("/invoices", response_model=List[InvoiceOut], dependencies=[Depends(rate_limit)])
def list_invoices(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(cache.get_redis),
):
    key = cache.list_key(skip, limit)
    cached = cache.cache_get(r, key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    rows = db.scalars(select(Invoice).order_by(Invoice.id).offset(skip).limit(limit)).all()
    data = [InvoiceOut.model_validate(row).model_dump(mode="json") for row in rows]
    cache.cache_set(r, key, data)
    response.headers["X-Cache"] = "MISS"
    return data


@app.get("/invoices/{invoice_id}", response_model=InvoiceOut, dependencies=[Depends(rate_limit)])
def get_invoice(
    invoice_id: int,
    response: Response,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(cache.get_redis),
):
    key = cache.invoice_key(invoice_id)
    cached = cache.cache_get(r, key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    data = InvoiceOut.model_validate(invoice).model_dump(mode="json")
    cache.cache_set(r, key, data)
    response.headers["X-Cache"] = "MISS"
    return data


@app.patch("/invoices/{invoice_id}", response_model=InvoiceOut, dependencies=[Depends(rate_limit)])
def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdate,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(cache.get_redis),
):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(invoice, field, value)
    db.commit()
    db.refresh(invoice)
    cache.invalidate_invoice(r, invoice_id)
    cache.invalidate_lists(r)
    return invoice


@app.delete("/invoices/{invoice_id}", status_code=204, dependencies=[Depends(rate_limit)])
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), r: redis.Redis = Depends(cache.get_redis)):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db.delete(invoice)
    db.commit()
    cache.invalidate_invoice(r, invoice_id)
    cache.invalidate_lists(r)
    return Response(status_code=204)
