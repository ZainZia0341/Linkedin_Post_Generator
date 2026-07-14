from __future__ import annotations

from mangum import Mangum

from app.api.main import app

handler = Mangum(app, lifespan="off")
