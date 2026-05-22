from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PatientStatus(str, Enum):
    WAITING = "waiting"
    CALLED = "called"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class PriorityLevel(str, Enum):
    NORMAL = "normal"
    URGENT = "urgent"


class Patient(BaseModel):
    id: str
    ticket_number: str
    name: str
    name_en: str
    department: str
    room: str
    status: PatientStatus = PatientStatus.WAITING
    priority: PriorityLevel = PriorityLevel.NORMAL
    priority_reason: Optional[str] = None


class QueueState(BaseModel):
    department: str
    room: str
    doctor_name: str
    calling_paused: bool = False
    current: Optional[Patient] = None
    waiting: list[Patient] = Field(default_factory=list)
    recently_called: list[Patient] = Field(default_factory=list)
    demo_patient_id: str = "p005"


class CallNextResponse(BaseModel):
    called: Optional[Patient] = None
    state: QueueState


class PriorityRequest(BaseModel):
    patient_id: str
    reason: str = Field(..., min_length=2, max_length=500)


class UrgencyAssessment(BaseModel):
    is_medical_emergency: bool
    urgency_score: int = Field(ge=0, le=100)
    category: str
    summary_zh: str
    summary_en: str
    recommendation: str  # approve | reject | manual_review
    reject_reason: Optional[str] = None


class PriorityResponse(BaseModel):
    patient_id: str
    assessment: UrgencyAssessment
    queue_position_before: int
    queue_position_after: int
    approved: bool


class WsMessage(BaseModel):
    type: str
    payload: dict
