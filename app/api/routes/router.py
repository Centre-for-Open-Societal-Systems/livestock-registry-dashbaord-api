from fastapi import APIRouter

from app.api.routes import charts

api_router = APIRouter()
api_router.include_router(charts.router, prefix="/charts", tags=["charts"])
