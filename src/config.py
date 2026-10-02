"""Central settings: Pakistan units, prices, and simulation parameters."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
DB_PATH = ROOT / "data" / "fleet.db"

SEED = 42

# --- Unit conversion (mindweave is US data: miles / gallons / mpg) ---
KM_PER_MILE = 1.609344
LITRES_PER_US_GALLON = 3.785411
MPG_TO_KM_PER_L = KM_PER_MILE / LITRES_PER_US_GALLON  # ~0.4251

# --- Fuel prices, PKR per litre (current rates given by the user) ---
FUEL_PRICE_NOW = {"Petrol": 387.40, "Diesel": 400.35}
# Simulated history: price index rises linearly from this value to 1.0 at the end
# of the period (+/- noise). This is NOT the real historical price series.
FUEL_PRICE_START_INDEX = 0.80
FUEL_PRICE_NOISE = 0.015

# --- Simulation window ---
START_DATE = "2023-01-01"
END_DATE = "2025-12-31"

# --- Fleet layout (mindweave depots mapped to Pakistani cities) ---
DEPOT_CITIES = {1: ("Lahore Depot", "Lahore", "LEA"),
                2: ("Islamabad Depot", "Islamabad", "ICT"),
                3: ("Karachi Depot", "Karachi", "BAB")}
N_DRIVERS = 24

# mindweave vehicle_type -> local model, fuel
VEHICLE_MAP = {
    "Cargo Van": ("Toyota Hiace", "Diesel"),
    "Box Truck": ("Isuzu NPR", "Diesel"),
    "Sprinter Van": ("Mercedes Sprinter", "Diesel"),
}
PETROL_SHARE_CARGO_VAN = 0.25  # share of Hiace vans running petrol

ROUTES = ["City Center Loop", "Airport Route", "Industrial Estate", "University Area",
          "Motorway Express", "Suburban North", "Suburban South", "Old City Delivery",
          "Dry Port Route", "Ring Road"]

# --- Trips ---
ACTIVE_DAY_PROB = 0.78          # Sundays are mostly off, see generator
SUNDAY_ACTIVE_PROB = 0.15
TRIP_KM_MEAN, TRIP_KM_SD = 240, 65   # mindweave: 149 +/- 40 miles
TRIP_KM_MIN, TRIP_KM_MAX = 40, 450
FUEL_ANOMALY_RATE = 0.015       # injected leak/theft trips (ground truth for evaluation)

# --- Maintenance ---
# type: (interval_km or None, interval_days or None, base cost PKR, critical for breakdown risk)
SERVICES = {
    "Oil Change":           (10_000, None, 14_000, True),
    "Tire Rotation":        (10_000, None, 3_000, False),
    "Brake Inspection":     (20_000, None, 18_000, True),
    "Air Filter":           (15_000, None, 4_500, False),
    "Alignment":            (20_000, None, 5_000, False),
    "Coolant Flush":        (40_000, None, 9_000, True),
    "Engine Tune-Up":       (30_000, None, 25_000, True),
    "Transmission Service": (60_000, None, 55_000, True),
    "Battery Replacement":  (None, 650, 38_000, False),
    "Wiper Replacement":    (None, 365, 3_000, False),
}
COST_TYPE_MULT = {"Cargo Van": 1.0, "Sprinter Van": 1.4, "Box Truck": 1.6}
COST_INFLATION_PER_YEAR = 0.12

# Breakdown repair: type -> (median cost PKR, service that is reset)
BREAKDOWNS = {
    "Engine Failure":       (180_000, "Engine Tune-Up"),
    "Transmission Failure": (150_000, "Transmission Service"),
    "Brake Failure":        (60_000, "Brake Inspection"),
    "Overheating":          (45_000, "Coolant Flush"),
    "Lubrication Failure":  (70_000, "Oil Change"),
}

# Breakdown hazard per active day = BASE * exp(DEBT*debt + AGE*age_yrs + HARSH*(driver_harsh-1))
HAZARD_BASE = 0.0011
HAZARD_DEBT = 10.0
HAZARD_AGE = 0.30
HAZARD_HARSH = 2.5

# --- Alerts / cost impact (business assumptions, change to match the real fleet) ---
AS_OF_DATE = "2026-01-01"            # "today" for scoring = day after the last simulated day
DOWNTIME_COST_PER_DAY_PKR = 25_000   # lost delivery revenue + replacement hire per vehicle-day
SERVICE_RISK_REDUCTION = 0.60        # assumed share of breakdown risk removed by the overdue service
RISK_HIGH, RISK_MEDIUM = 0.30, 0.15  # probability cut-offs for alert tiers (30-day breakdown risk)
