from enum import Enum


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    FAILED = "FAILED"
    RECOVERED = "RECOVERED"
    SUCCEEDED = "SUCCEEDED"
    CANCELLED = "CANCELLED"


class PolicyStatus(str, Enum):
    ALLOWED = "ALLOWED"
    REJECTED = "REJECTED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class InterventionStatus(str, Enum):
    PLANNED = "PLANNED"
    EXECUTED = "EXECUTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
