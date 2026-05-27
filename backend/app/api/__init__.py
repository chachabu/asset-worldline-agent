from fastapi import APIRouter

from app.api import assets, auth, forecasts, jobs, model_configs, news, overview, sources

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(overview.router)
api_router.include_router(sources.router)
api_router.include_router(assets.router)
api_router.include_router(news.router)
api_router.include_router(model_configs.router)
api_router.include_router(forecasts.router)
api_router.include_router(jobs.router)

