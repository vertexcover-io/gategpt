from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from custom_gpts_paywall.config import create_config
from custom_gpts_paywall.routers.root import root_router
from custom_gpts_paywall.routers.openapi_schema import openapi_schema_router
from custom_gpts_paywall.routers.google_oauth import google_oauth_router
from custom_gpts_paywall.routers.verification import verification_router
from custom_gpts_paywall.routers.user_account import user_account_router
from custom_gpts_paywall.routers.oauth2_server import oauth2_router


def create_app() -> FastAPI:
    config = create_config()
    app = FastAPI(
        servers=[
            {
                "url": config.domain_url,
            }
        ],
        tags=[
            {
                "name": "admin",
                "description": "Admin API",
            },
            {
                "name": "gpts",
                "description": "gpts Actions API",
            },
        ],
    )

    app.add_middleware(SessionMiddleware, secret_key=config.secret_key)
    app.include_router(root_router)
    app.include_router(
        openapi_schema_router,
        tags=["openapi"],
        prefix="/openapi",
    )
    app.include_router(
        google_oauth_router,
        tags=["oauth"],
        prefix="/oauth",
    )

    app.include_router(
        verification_router,
        prefix="/api/v1",
    )
    app.include_router(
        user_account_router,
        tags=["admin"],
    )

    app.include_router(
        oauth2_router,
    )

    return app
