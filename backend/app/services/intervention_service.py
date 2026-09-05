from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.decision import RecoveryDecision
from app.models.intervention import Intervention
from app.schemas.intervention import InterventionListItem, InterventionListResponse


def list_interventions(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    status: str | None,
    provider: str | None,
) -> InterventionListResponse:
    filters = []
    if status:
        filters.append(cast(Intervention.status, String) == status)
    if provider:
        filters.append(Intervention.provider == provider)
    if search:
        value = f"%{search.strip()}%"
        filters.append(
            or_(
                cast(Intervention.id, String).ilike(value),
                cast(RecoveryDecision.payment_id, String).ilike(value),
                Intervention.provider_action_id.ilike(value),
            )
        )

    base = (
        select(Intervention, RecoveryDecision.payment_id)
        .join(RecoveryDecision, Intervention.decision_id == RecoveryDecision.id)
        .where(*filters)
    )
    total = int(
        db.scalar(
            select(func.count())
            .select_from(Intervention)
            .join(RecoveryDecision, Intervention.decision_id == RecoveryDecision.id)
            .where(*filters)
        )
        or 0
    )
    rows = db.execute(
        base.order_by(Intervention.created_at.desc(), Intervention.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return InterventionListResponse(
        items=[
            InterventionListItem(
                intervention_id=item.id,
                payment_id=payment_id,
                action=item.action_type.value,
                provider=item.provider,
                provider_action_id=item.provider_action_id,
                provider_status=item.provider_status,
                status=item.status.value,
                executed_at=item.executed_at,
                created_at=item.created_at,
            )
            for item, payment_id in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
