from datetime import timedelta
from authlib.integrations.base_client import OAuthError
# from authlib.jose.rfc7519 import jwt
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, FileResponse
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




auth_router = APIRouter()


@auth_router.get("/login", name="login_page", response_class=FileResponse)
def login_page():
    return "templates/login.html"


@auth_router.get("/login/failed", response_class=FileResponse)
def login_failure():
    return "templates/login_fail.html"


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
    # header = {"alg": "HS256", "typ": "JWT"}
    payload = {"exp": utcnow() + expires_in, "iat": utcnow(), "sub": user_email}
    # jwt_instance = JsonWebToken(["HS256"])
    # jwt_instance = JsonWebToken()
    # return jwt_instance.encode(header, payload, secret_key)
    return jwt.encode(payload, secret_key, algorithm = JWT_ENCODE_ALGORITHM)




def get_current_user(jwt_token: str = Cookie(None)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Not authorized",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if jwt_token:
        # jwt_instance = JsonWebToken(algorithms=["HS256"])
        secret_key_bytes = os.getenv("SECRET_KEY").encode('utf-8')

        try:
            print("Decode", jwt_token)
            payload = jwt.decode(jwt_token, secret_key_bytes, algorithms = JWT_ENCODE_ALGORITHM)
            return payload
        except DecodeError:
            # print(DecodeError)
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
        # user_info = await config.google_oauth_client.parse_id_token(request, token)
        user_info = token['userinfo']
        print(user_info)
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

    # jwt_token = create_jwt_token(email, config.secret_key, config.jwt_token_expiry)
    # convert secret key to bytes
    config_secret_key_bytes = config.secret_key.encode('utf-8')

    jwt_token = create_jwt_token(email, config_secret_key_bytes, config.jwt_token_expiry)
    print("Encode", jwt_token)
    response = RedirectResponse(
        url=url_for(request, "root", scheme=config.url_scheme),
    )
    response.set_cookie("jwt_token", jwt_token, httponly=True)
    return response