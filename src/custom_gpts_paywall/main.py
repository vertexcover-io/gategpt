import logging
from fastapi import FastAPI, HTTPException, staticfiles
from starlette.middleware.sessions import SessionMiddleware
from custom_gpts_paywall.config import (
    EnvConfig,
    OpenAPISchemaTags,
    create_config,
    templates,
)
from custom_gpts_paywall.routers.root import root_router
from custom_gpts_paywall.routers.openapi_schema import openapi_schema_router
from custom_gpts_paywall.routers.gpt_application import gpt_application_router
from custom_gpts_paywall.routers.oauth2_server import oauth2_router
from custom_gpts_paywall.routers.gpt_app_session import gpt_app_session_router
from custom_gpts_paywall.routers.auth import auth_router


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
    app.mount("/static", staticfiles.StaticFiles(directory="static"), name="static")
    perform_setup(config)
    app.add_middleware(SessionMiddleware, secret_key=config.secret_key)
    app.include_router(root_router)
    app.include_router(
        openapi_schema_router,
        tags=[OpenAPISchemaTags.OpenAPI],
        prefix="/openapi",
    )

    # app.include_router(
    #     verification_router,
    #     include_in_schema=False,
    #     prefix="/api/v1",
    # )
    app.include_router(
        gpt_application_router,
        tags=[OpenAPISchemaTags.CustomGptApplication],
    )

    app.include_router(
        gpt_app_session_router,
        prefix="/api/v1",
        tags=[OpenAPISchemaTags.GPTAppSession],
    )

    app.include_router(
        oauth2_router,
        prefix="/oauth2-server",
        tags=[OpenAPISchemaTags.OAuth2Server],
    )

    app.include_router(auth_router, tags=[OpenAPISchemaTags.Auth])

    @app.exception_handler(404)
    async def custom_404_handler(request, exc: HTTPException):
        logging.warning(f"Resource Not Found: {request.url}. Error: {exc.detail}")
        return templates.TemplateResponse(
            "404.html", status_code=404, context={"request": request}
        )

    @app.exception_handler(500)
    async def internal_exception_handler(request, exc: HTTPException):
        logging.exception(exc)
        return templates.TemplateResponse(
            "500.html", context={"request": request}, status_code=500
        )

    logging.info("App created")
    return app
