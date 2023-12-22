from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
from pydantic import BaseModel
from authlib.integrations.httpx_client import OAuth2Client
from custom_gpts_paywall.dependencies import DbSession, LoggerDep
from custom_gpts_paywall.models import UserSession


user_session_router = APIRouter()


class CreateSessionRequest(BaseModel):
    gpt_application_id: str


class CreateSessionResponse(BaseModel):
    gpt_application_id: str
    email: str
    name: str


bearer_token_security = HTTPBearer(scheme_name="API Key")


@user_session_router.post("/session", response_model=CreateSessionResponse)
def create_session(
    session: DbSession,
    create_session_request: CreateSessionRequest,
    credentials: Annotated[
        HTTPAuthorizationCredentials, Depends(bearer_token_security)
    ],
    logger: LoggerDep,
):
    client = OAuth2Client(token={"access_token": credentials.credentials})

    # Google's userinfo endpoint
    userinfo_endpoint = "https://www.googleapis.com/oauth2/v3/userinfo"

    # Make a GET request to the userinfo endpoint
    try:
        response = client.get(userinfo_endpoint)
    except (httpx.RequestError, httpx.httpx.NetworkError) as exc:
        logger.error(
            f"A network error occurred while validating access token: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Network Error while validating token"
        )
    except httpx.HTTPStatusError as exc:
        error_msg = "Error while validating token"
        logger.errror(
            f"Error while validating token: Status Code: {exc.response.status_code}. Response: {exc.response.content}",
            exc_info=exc,
        )
        raise HTTPException(status_code=exc.response.status_code, detail=error_msg)

    # Parse the response to get user information
    user_info = response.json()
    user_session = UserSession(
        gpt_application_id=create_session_request.gpt_application_id,
        email=user_info["email"],
        name=user_info["name"],
    )
    session.add(user_session)
    session.commit()
    return {
        "gpt_application_id": create_session_request.gpt_application_id,
        "email": user_info["email"],
        "name": user_info["name"],
    }
