"""FleetAI REST API.  Run:  uvicorn api.main:app --host 0.0.0.0 --port 8000   (docs at /docs)"""
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

import config as C

from . import settings as S
from . import state
from .fleet import FleetService, prepare_runtime
from .schemas import (AlertCategory, AlertList, FuelCheckRequest, FuelCheckResult, LoginRequest, Prediction,
                      ServiceRecordRequest, ServiceRecordResult, TokenResponse, User, VehicleSummary)
from .security import admin_user, create_token, current_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("fleet.api")
_service: FleetService | None = None


@asynccontextmanager
async def lifespan(_app):
    global _service
    for warning in state.init():
        log.warning(warning)
    prepare_runtime()
    _service = FleetService()
    log.info("FleetAI API ready: %d vehicles scored as of %s", len(_service.vehicles), C.AS_OF_DATE)
    yield


app = FastAPI(
    title="FleetAI API", version=S.API_VERSION, lifespan=lifespan,
    description="Fleet management & predictive-maintenance API backed by the project's XGBoost risk model, "
                "SHAP explanations and fuel-anomaly detector. Simulated demo data (2023-2025).",
)


@app.exception_handler(Exception)
async def unhandled_error(_request, exc):
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def service() -> FleetService:
    if _service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service is starting, try again shortly")
    return _service


def vehicle_id_or_404(vehicle_id: int, svc: FleetService) -> int:
    if vehicle_id not in svc.vehicle_ids():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Vehicle {vehicle_id} not found")
    return vehicle_id


public = APIRouter(prefix="/api/v1")
api = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])


# ----------------------------------------------------------------------------- public
@public.get("/health", tags=["system"])
def health():
    svc = _service
    return {"status": "ok" if svc else "starting", "version": S.API_VERSION, "as_of": C.AS_OF_DATE,
            "data_start": C.START_DATE, "data_end": C.END_DATE,
            "vehicles": 0 if svc is None else len(svc.vehicles), "scored_at": None if svc is None else svc.scored_at}


@public.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(body: LoginRequest):
    user = state.verify_user(body.username.strip(), body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    token, ttl = create_token(user["username"])
    return {"access_token": token, "expires_in": ttl, "user": user}


# ----------------------------------------------------------------------------- auth / dashboard
@api.get("/auth/me", response_model=User, tags=["auth"])
def me(user=Depends(current_user)):
    return user


@api.get("/dashboard", tags=["dashboard"])
def dashboard(user=Depends(current_user)):
    return service().dashboard(state.read_alert_ids(user["username"]))


# ----------------------------------------------------------------------------- vehicles
@api.get("/vehicles", response_model=list[VehicleSummary], tags=["vehicles"])
def list_vehicles(search: str | None = Query(None, max_length=40), status_: str | None = Query(None, alias="status"),
                  vehicle_type: str | None = None, depot: str | None = None,
                  risk_tier: Literal["High", "Medium", "Low"] | None = None,
                  sort: Literal["risk", "health", "registration", "odometer"] = "risk"):
    return service().list_vehicles(search, status_, vehicle_type, depot, risk_tier, sort)


@api.get("/vehicles/{vehicle_id}", tags=["vehicles"])
def vehicle_detail(vehicle_id: int = Path(gt=0)):
    svc = service()
    return svc.vehicle_detail(vehicle_id_or_404(vehicle_id, svc))


@api.get("/vehicles/{vehicle_id}/trips", tags=["vehicles", "trips"])
def vehicle_trips(vehicle_id: int = Path(gt=0), limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0)):
    svc = service()
    return svc.list_trips(vehicle_id=vehicle_id_or_404(vehicle_id, svc), limit=limit, offset=offset)


# ----------------------------------------------------------------------------- maintenance
@api.get("/maintenance/summary", tags=["maintenance"])
def maintenance_summary():
    return service().maintenance_summary()


@api.get("/maintenance/schedule", tags=["maintenance"])
def maintenance_schedule(status_: Literal["overdue", "due_soon", "ok", "unknown"] | None = Query(None, alias="status"),
                         vehicle_id: int | None = Query(None, gt=0), critical_only: bool = False,
                         limit: int = Query(100, ge=1, le=600)):
    svc = service()
    if vehicle_id is not None:
        vehicle_id_or_404(vehicle_id, svc)
    return svc.maintenance_schedule(status_, vehicle_id, critical_only, limit)


@api.get("/maintenance/history", tags=["maintenance"])
def maintenance_history(vehicle_id: int | None = Query(None, gt=0), kind: Literal["Preventive", "Breakdown"] | None = None,
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    svc = service()
    if vehicle_id is not None:
        vehicle_id_or_404(vehicle_id, svc)
    return svc.maintenance_history(vehicle_id, kind, limit, offset)


@api.post("/maintenance", response_model=ServiceRecordResult, status_code=status.HTTP_201_CREATED, tags=["maintenance", "ai"])
def record_service(body: ServiceRecordRequest, user=Depends(current_user)):
    """Record a completed preventive service; the AI model is re-run so the vehicle's risk reflects it."""
    svc = service()
    vehicle_id_or_404(body.vehicle_id, svc)
    return svc.record_service(body.vehicle_id, body.service, body.cost, body.notes, user["username"])


# ----------------------------------------------------------------------------- fuel / drivers / trips
@api.get("/fuel/summary", tags=["fuel"])
def fuel_summary(days: int = Query(30, ge=1, le=1095)):
    return service().fuel_summary(days)


@api.get("/fuel/anomalies", tags=["fuel", "ai"])
def fuel_anomalies(days: int = Query(90, ge=1, le=1095), vehicle_id: int | None = Query(None, gt=0),
                   limit: int = Query(50, ge=1, le=200)):
    return service().fuel_anomalies(days, vehicle_id, limit)


@api.get("/drivers", tags=["drivers"])
def list_drivers(days: int = Query(180, ge=7, le=1095), sort: Literal["safety", "performance", "name"] = "safety"):
    return service().list_drivers(days, sort)


@api.get("/drivers/{driver_id}", tags=["drivers"])
def driver_detail(driver_id: int = Path(gt=0), days: int = Query(180, ge=7, le=1095)):
    svc = service()
    if driver_id not in set(int(i) for i in svc.drivers.index):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Driver {driver_id} not found")
    return svc.driver_detail(driver_id, days)


@api.get("/trips", tags=["trips"])
def list_trips(vehicle_id: int | None = Query(None, gt=0), driver_id: int | None = Query(None, gt=0),
               limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0)):
    return service().list_trips(vehicle_id, driver_id, limit, offset)


# ----------------------------------------------------------------------------- alerts
@api.get("/alerts", response_model=AlertList, tags=["alerts"])
def list_alerts(category: AlertCategory | None = None, unread_only: bool = False, user=Depends(current_user)):
    items = service().alerts(state.read_alert_ids(user["username"]))
    unread = sum(1 for a in items if not a["read"])
    if category:
        items = [a for a in items if a["category"] == category]
    if unread_only:
        items = [a for a in items if not a["read"]]
    return {"total": len(items), "unread": unread, "items": items}


@api.post("/alerts/read-all", tags=["alerts"])
def read_all_alerts(user=Depends(current_user)):
    ids = [a["id"] for a in service().alerts() ]
    state.mark_read(user["username"], ids)
    return {"marked": len(ids)}


@api.post("/alerts/{alert_id}/read", tags=["alerts"])
def read_alert(alert_id: str = Path(min_length=3, max_length=80), user=Depends(current_user)):
    if alert_id not in {a["id"] for a in service().alerts()}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found (it may have been resolved)")
    state.mark_read(user["username"], [alert_id])
    return {"id": alert_id, "read": True}


# ----------------------------------------------------------------------------- AI
@api.get("/ai/model", tags=["ai"])
def model_info():
    return service().model_info()


@api.post("/ai/predict/{vehicle_id}", response_model=Prediction, tags=["ai"])
def predict(vehicle_id: int = Path(gt=0)):
    """Re-run the breakdown-risk model (features from the current database) and explain the result."""
    svc = service()
    vehicle_id_or_404(vehicle_id, svc)
    svc.rescore()
    return svc.prediction(vehicle_id)


@api.post("/ai/fuel-check", response_model=FuelCheckResult, tags=["ai", "fuel"])
def fuel_check(body: FuelCheckRequest):
    svc = service()
    return svc.fuel_check(vehicle_id_or_404(body.vehicle_id, svc), body.distance_km, body.fuel_litres)


# ----------------------------------------------------------------------------- admin
@api.post("/admin/reset-demo", tags=["admin"])
def reset_demo(_admin=Depends(admin_user)):
    """Restore the demo database (undo services recorded through the API)."""
    svc = service()
    with svc.lock:
        prepare_runtime(fresh=True)
        svc.reload()
    return {"status": "reset", "vehicles": len(svc.vehicles)}


app.include_router(public)
app.include_router(api)
