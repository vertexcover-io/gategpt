from datetime import timedelta
from authlib.integrations.base_client import OAuthError
# from authlib.jose.rfc7519 import jwt
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from sqlalchemy import insert
from custom_gpts_paywall.config import JWT_ENCODE_ALGORITHM
import os
from custom_gpts_paywall.dependencies import ConfigDep, DbSession, LoggerDep
from custom_gpts_paywall.models import User
from custom_gpts_paywall.utils import url_for, utcnow

from fastapi import FastAPI, Depends, HTTPException, Request, Response, Cookie
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from authlib.jose import JsonWebToken
from datetime import timedelta

import jwt
from authlib.jose import JsonWebToken
from authlib.jose.errors import DecodeError
from fastapi.exceptions import HTTPException
from fastapi import Cookie
from sqlalchemy.orm import joinedload

from fastapi.templating import Jinja2Templates

auth_router = APIRouter()

templates = Jinja2Templates(directory="templates")

@auth_router.get("/login", name="login_page", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})



@auth_router.get("/login/failed", response_class=HTMLResponse)
def login_failure(request: Request):
    return templates.TemplateResponse("login_fail.html", {"request": request})


@auth_router.post("/login", name="auth_login")
async def oauth_login(config: ConfigDep, request: Request):
    return await config.google_oauth_client.authorize_redirect(
        request,
        redirect_uri=url_for(
            request,
            "oauth_callback_google",
            scheme=config.url_scheme,
        ),
        access_type="offline",
    )

def create_jwt_token(user_email: str, secret_key: str, expires_in: timedelta):
    payload = {"exp": utcnow() + expires_in, "iat": utcnow(), "sub": user_email}
    return jwt.encode(payload, secret_key, algorithm = JWT_ENCODE_ALGORITHM)


def get_current_user(config: ConfigDep, logger: LoggerDep, session: DbSession, jwt_token: str = Cookie(None)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Not authorized :(",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if jwt_token:
        secret_key_bytes = config.secret_key.encode('utf-8')

        try:
            payload = jwt.decode(jwt_token, secret_key_bytes, algorithms = JWT_ENCODE_ALGORITHM)
            user_email = payload.get("sub")
            
            if user_email:
                user = session.query(User).options(joinedload(User.custom_gpt_applications)).filter_by(email=user_email).first()
                if user:
                    # logger.info(user.custom_gpt_applications)
                    payload["gpt_applications"] = user.custom_gpt_applications
                else:
                    raise HTTPException(status_code=401, detail="Invalid user")
            else:
                raise HTTPException(status_code=401, detail="Invalid token")
            return payload
        except DecodeError:
            raise HTTPException(status_code=401, detail="Invalid token or signature")
    else:
        raise credentials_exception

# test route
@auth_router.get("/p1")
async def protected_route(current_user: dict = Depends(get_current_user)):
    return {"message": "You are authorized, welcome!", "user": current_user}




@auth_router.get("/oauth/callback/google", name="oauth_callback_google")
async def oauth_callback_google(
    config: ConfigDep, request: Request, session: DbSession, logger: LoggerDep
):
    try:
        token = await config.google_oauth_client.authorize_access_token(request)
        user_info = token['userinfo']
    except Exception as e:
        error_msg = "Login Failed. Try Again"
        if isinstance(e, OAuthError):
            error_msg = str(e)

        logger.error(f"Error while trying to access access token: {e}", exc_info=True)
        return RedirectResponse(
            url=url_for(request, "login_failure", query_params={"error": error_msg})
        )

    logger.info(f"User info: {user_info}")
    email = user_info["email"]
    name = user_info["name"]
    stmt = (
        pg_insert(User)
        .values(
            {
                "email": email,
                "name": name,
            }
        )
        .on_conflict_do_nothing(index_elements=["email"])
    )
    session.execute(stmt)
    session.commit()

    config_secret_key_bytes = config.secret_key.encode('utf-8')

    jwt_token = create_jwt_token(email, config_secret_key_bytes, config.jwt_token_expiry)
    response = RedirectResponse(
        url=url_for(request, "root", scheme=config.url_scheme),
    )
    response.set_cookie("jwt_token", jwt_token, httponly=True)
    return response