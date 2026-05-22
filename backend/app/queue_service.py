from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Callable, Optional

from app.config import settings
from app.models import (
    CallNextResponse,
    Patient,
    PatientStatus,
    PriorityLevel,
    PriorityResponse,
    QueueState,
    UrgencyAssessment,
)


def _mock_patients() -> list[Patient]:
    dept, room = settings.department, settings.room
    rows = [
        ("p001", "A012", "王建国", "Wang Jianguo", PatientStatus.COMPLETED),
        ("p002", "A013", "陈秀英", "Chen Xiuying", PatientStatus.COMPLETED),
        ("p003", "A014", "刘志强", "Liu Zhiqiang", PatientStatus.WAITING, PriorityLevel.URGENT),
        ("p004", "A015", "David Smith", "David Smith", PatientStatus.WAITING),
        ("p005", "A016", "李婷婷", "Li Tingting", PatientStatus.WAITING),
        ("p006", "A017", "张伟", "Zhang Wei", PatientStatus.WAITING),
        ("p007", "A018", "赵敏", "Zhao Min", PatientStatus.WAITING),
        ("p008", "A019", "孙丽华", "Sun Lihua", PatientStatus.WAITING),
        ("p009", "A020", "周海涛", "Zhou Haitao", PatientStatus.WAITING),
        ("p010", "A021", "吴芳", "Wu Fang", PatientStatus.WAITING),
    ]
    patients: list[Patient] = []
    for row in rows:
        priority = row[5] if len(row) > 5 else PriorityLevel.NORMAL
        patients.append(
            Patient(
                id=row[0],
                ticket_number=row[1],
                name=row[2],
                name_en=row[3],
                department=dept,
                room=room,
                status=row[4],
                priority=priority,
            )
        )
    return patients


class QueueService:
    """内存队列，单科室单诊室 MVP。"""

    AVG_MINUTES_PER_PATIENT = 8

    def __init__(self) -> None:
        self._patients: list[Patient] = _mock_patients()
        self._current: Optional[Patient] = None
        self._calling_paused = False
        self._recently_called: list[Patient] = []
        self._listeners: list[Callable[[str, dict], None]] = []
        self._lock = asyncio.Lock()
        self._last_event_at = datetime.now(timezone.utc).isoformat()

    def subscribe(self, listener: Callable[[str, dict], None]) -> None:
        self._listeners.append(listener)

    def _emit(self, event_type: str, payload: dict) -> None:
        self._last_event_at = datetime.now(timezone.utc).isoformat()
        for listener in list(self._listeners):
            listener(event_type, payload)

    def get_state(self) -> QueueState:
        waiting = [
            p
            for p in self._patients
            if p.status == PatientStatus.WAITING
        ]
        waiting.sort(
            key=lambda p: (
                0 if p.priority == PriorityLevel.URGENT else 1,
                self._patients.index(p),
            )
        )
        return QueueState(
            department=settings.department,
            room=settings.room,
            doctor_name=settings.doctor_name,
            calling_paused=self._calling_paused,
            current=self._current,
            waiting=waiting,
            recently_called=self._recently_called[-5:],
            demo_patient_id="p005",
        )

    def get_patient(self, patient_id: str) -> Optional[Patient]:
        for p in self._patients:
            if p.id == patient_id:
                return deepcopy(p)
        return None

    def estimate_wait_minutes(self, patient_id: str) -> int:
        state = self.get_state()
        found = False
        ahead = 0
        for p in state.waiting:
            if p.id == patient_id:
                found = True
                break
            ahead += 1
        if not found:
            return 0
        if state.current and state.current.status in (
            PatientStatus.CALLED,
            PatientStatus.IN_CONSULTATION,
        ):
            ahead += 1
        return max(ahead * self.AVG_MINUTES_PER_PATIENT, 0)

    def position_in_queue(self, patient_id: str) -> int:
        state = self.get_state()
        for i, p in enumerate(state.waiting):
            if p.id == patient_id:
                return i
        return -1

    async def call_next(self) -> CallNextResponse:
        async with self._lock:
            if self._calling_paused:
                return CallNextResponse(called=None, state=self.get_state())

            if self._current and self._current.status == PatientStatus.CALLED:
                self._set_status(self._current.id, PatientStatus.IN_CONSULTATION)

            waiting = [
                p
                for p in self._patients
                if p.status == PatientStatus.WAITING
            ]
            waiting.sort(
                key=lambda p: (
                    0 if p.priority == PriorityLevel.URGENT else 1,
                    self._patients.index(p),
                )
            )
            if not waiting:
                return CallNextResponse(called=None, state=self.get_state())

            nxt = waiting[0]
            self._set_status(nxt.id, PatientStatus.CALLED)
            self._current = self._find(nxt.id)
            self._recently_called.append(deepcopy(self._current))
            state = self.get_state()
            self._emit(
                "patient_called",
                {
                    "patient": self._current.model_dump(),
                    "state": state.model_dump(),
                },
            )
            return CallNextResponse(called=deepcopy(self._current), state=state)

    async def skip_current(self) -> QueueState:
        async with self._lock:
            if self._current:
                self._set_status(self._current.id, PatientStatus.SKIPPED)
                self._current = None
            state = self.get_state()
            self._emit("queue_updated", {"state": state.model_dump()})
            return state

    async def set_paused(self, paused: bool) -> QueueState:
        async with self._lock:
            self._calling_paused = paused
            state = self.get_state()
            self._emit(
                "calling_paused",
                {"paused": paused, "state": state.model_dump()},
            )
            return state

    async def apply_priority(
        self,
        patient_id: str,
        assessment: UrgencyAssessment,
    ) -> PriorityResponse:
        async with self._lock:
            pos_before = self.position_in_queue(patient_id)
            approved = assessment.recommendation == "approve" and assessment.is_medical_emergency
            patient = self._find(patient_id)
            if patient and approved:
                patient.priority = PriorityLevel.URGENT
                patient.priority_reason = assessment.summary_zh
            state = self.get_state()
            pos_after = self.position_in_queue(patient_id)
            self._emit(
                "priority_applied",
                {
                    "patient_id": patient_id,
                    "approved": approved,
                    "assessment": assessment.model_dump(),
                    "state": state.model_dump(),
                },
            )
            return PriorityResponse(
                patient_id=patient_id,
                assessment=assessment,
                queue_position_before=pos_before,
                queue_position_after=pos_after,
                approved=approved,
            )

    def _find(self, patient_id: str) -> Optional[Patient]:
        for p in self._patients:
            if p.id == patient_id:
                return p
        return None

    def _set_status(self, patient_id: str, status: PatientStatus) -> None:
        p = self._find(patient_id)
        if p:
            p.status = status

    def snapshot_for_sync(self) -> dict:
        return {
            "state": self.get_state().model_dump(),
            "server_time": self._last_event_at,
        }


queue_service = QueueService()
