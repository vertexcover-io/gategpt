import logging
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from custom_gpts_paywall.config import EnvConfig, OpenAPISchemaTags, create_config
from custom_gpts_paywall.routers.root import root_router
from custom_gpts_paywall.routers.openapi_schema import openapi_schema_router
from custom_gpts_paywall.routers.google_oauth import google_oauth_router
from custom_gpts_paywall.routers.verification import verification_router
from custom_gpts_paywall.routers.gpt_application import gpt_application_router
from custom_gpts_paywall.routers.oauth2_server import oauth2_router
from custom_gpts_paywall.routers.user_session import user_session_router


def confugure_logging(config: EnvConfig):
    logging.basicConfig(
        level=config.log_level,
        format="[%(asctime)s]  %(levelname)s: [%(filename)s:%(lineno)d]  %(message)s",
    )


def perform_setup(config: EnvConfig):
    confugure_logging(config)


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
    perform_setup(config)
    app.add_middleware(SessionMiddleware, secret_key=config.secret_key)
    app.include_router(root_router)
    app.include_router(
        openapi_schema_router,
        tags=[OpenAPISchemaTags.OpenAPI],
        prefix="/openapi",
    )
    app.include_router(
        google_oauth_router,
        include_in_schema=False,
        prefix="/oauth",
    )

    app.include_router(
        verification_router,
        include_in_schema=False,
        prefix="/api/v1",
    )
    app.include_router(
        gpt_application_router,
        tags=[OpenAPISchemaTags.CustomGptApplication],
        prefix="/api/v1",
    )

    app.include_router(
        user_session_router,
        prefix="/api/v1",
        tags=[OpenAPISchemaTags.UserSession],
    )

    app.include_router(
        oauth2_router,
        prefix="/oauth2",
        tags=[OpenAPISchemaTags.OAuth2Server],
    )
    logging.info("App created")
    return app
