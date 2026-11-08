import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./warehouse_twin.db")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
SIM_SEED = int(os.getenv("SIM_SEED", "42"))
SIM_TICK_HZ = float(os.getenv("SIM_TICK_HZ", "20"))
BROADCAST_HZ = float(os.getenv("BROADCAST_HZ", "10"))
DEFAULT_SPEED = float(os.getenv("SIM_DEFAULT_SPEED", "3"))
PERSISTENCE_ENABLED = os.getenv("PERSISTENCE_ENABLED", "1") == "1"
