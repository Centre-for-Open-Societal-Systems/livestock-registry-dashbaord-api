from fastapi import APIRouter, Depends

from app.api.routes import charts
from app.core.auth import require_caller

# Every chart route needs the caller's token (app/core/auth.py) while
# authentication is on.
api_router = APIRouter(dependencies=[Depends(require_caller)])
api_router.include_router(charts.router, prefix="/charts", tags=["charts"])
