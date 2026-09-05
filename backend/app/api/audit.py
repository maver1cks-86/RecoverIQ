from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.audit import PaymentAuditResponse
from app.services.audit_service import get_payment_audit


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/payments/{payment_id}", response_model=PaymentAuditResponse)
def payment_audit(payment_id: int, db: Session = Depends(get_db)) -> PaymentAuditResponse:
    result = get_payment_audit(db, payment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return result
