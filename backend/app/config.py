"""Settings (override with environment variables)."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
# jobunicorn code + checkpoints are vendored in jobweb/jobunicorn; its data/ folder comes from the backend Docker image (see README)
REPO = Path(os.environ.get("JOBUNICORN_REPO", BACKEND_DIR.parent / "jobunicorn")).resolve()
DATA_ROOT = Path(os.environ.get("JOBUNICORN_DATA", REPO / "data"))
DB_PATH = Path(os.environ.get("JOBWEB_DB", BACKEND_DIR / "data" / "jobweb.db"))
# PostgreSQL in Docker (postgresql+psycopg://user:pass@host/db); SQLite file at DB_PATH otherwise
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")
CACHE_DIR = Path(os.environ.get("JOBWEB_CACHE", BACKEND_DIR / "data"))  # encoder cache (title_text_w7.npz)
POLICY_PATH = Path(os.environ.get("JOBWEB_POLICY", REPO / "reports" / "post_p10_dqn" / "R3_belief_feats_pen08" / "policy.pt"))
SECRET_KEY = os.environ.get("JOBWEB_SECRET", "dev-secret-change-me")
TOKEN_HOURS = 12
DEMO_WINDOW = 7  # the "current" window shown in the demo (CareerBuilder window 7 = test window of the report)
LOAD_ENGINE = os.environ.get("JOBWEB_ENGINE", "1") == "1"  # set 0 to run the web app without the recommender
EXTRA_USERS = 2000  # reserved embedding rows for seekers who register on the web
EXTRA_JOBS = 5000  # reserved rows for jobs posted on the web
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
