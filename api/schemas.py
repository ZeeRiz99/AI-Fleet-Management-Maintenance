"""Request validation and the main response shapes (also documented at /docs)."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

import config as C

AlertCategory = Literal["maintenance_due", "maintenance_overdue", "high_risk", "fuel_anomaly", "health_warning", "operational"]


# ----------------------------------------------------------------------------- requests
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ServiceRecordRequest(BaseModel):
    vehicle_id: int = Field(gt=0)
    service: str = Field(description="One of the service types, e.g. 'Brake Inspection'")
    cost: float | None = Field(default=None, ge=0, le=5_000_000, description="PKR; omitted = standard estimate")
    notes: str | None = Field(default=None, max_length=200)

    @field_validator("service")
    @classmethod
    def known_service(cls, value):
        if value not in C.SERVICES:
            raise ValueError(f"unknown service; use one of: {', '.join(C.SERVICES)}")
        return value


class FuelCheckRequest(BaseModel):
    vehicle_id: int = Field(gt=0)
    distance_km: float = Field(gt=0, le=2000)
    fuel_litres: float = Field(gt=0, le=500)


# ----------------------------------------------------------------------------- responses
class User(BaseModel):
    username: str
    full_name: str | None = None
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


class Factor(BaseModel):
    feature: str
    label: str
    value: float | int | str | None = None
    display: str
    impact: float
    direction: str


class Recommendation(BaseModel):
    service: str
    overdue_pct: int
    service_cost: float
    expected_loss: float
    net_saving: float
    text: str


class Prediction(BaseModel):
    vehicle_id: int
    registration: str
    risk_probability: float
    risk_tier: str
    health_score: int
    health_band: str
    health_formula: str
    explanation: str
    factors: list[Factor]
    recommendation: Recommendation
    model: str
    as_of: str
    scored_at: str


class NextService(BaseModel):
    service: str
    status: str
    due_in_km: int | None = None
    due_in_days: int | None = None
    overdue_pct: int | None = None


class VehicleSummary(BaseModel):
    id: int
    registration: str
    make_model: str
    vehicle_type: str
    fuel_type: str
    year: int
    depot: str
    status: str
    odometer_km: int | None = None
    health_score: int
    health_band: str
    risk_probability: float
    risk_tier: str
    next_service: NextService | None = None


class Alert(BaseModel):
    id: str
    category: AlertCategory
    severity: Literal["critical", "warning", "info"]
    title: str
    message: str
    vehicle_id: int | None = None
    registration: str | None = None
    date: str
    read: bool


class AlertList(BaseModel):
    total: int
    unread: int
    items: list[Alert]


class FuelCheckResult(BaseModel):
    vehicle_id: int
    registration: str
    abnormal: bool
    verdict: str
    ratio: float
    threshold: float
    baseline_km_per_l: float
    actual_km_per_l: float
    expected_litres: float
    excess_litres: float
    excess_cost: float
    explanation: str


class ServiceRecordResult(BaseModel):
    record: dict
    before: Prediction
    after: Prediction
