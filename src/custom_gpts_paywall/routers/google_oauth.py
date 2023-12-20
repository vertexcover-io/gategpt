from logging import Logger
from boto3 import Session
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import shortuuid
from sqlalchemy.orm import joinedload

from custom_gpts_paywall.dependencies import ConfigDep, DbSession, LoggerDep
from custom_gpts_paywall.models import (
    OAuthVerificationRequest,
    OAuthVerificationRequestStatus,
)
from custom_gpts_paywall.utils import utcnow


google_oauth_router = APIRouter()


@google_oauth_router.get("/login/{verification_request_id}")
async def google_oauth_login(
    request: Request,
    verification_request_id: str,
    config: ConfigDep,
    session: DbSession,
):
    now = utcnow()

    verification_request = (
        session.query(OAuthVerificationRequest)
        .filter(
            OAuthVerificationRequest.uuid == verification_request_id,
            OAuthVerificationRequest.status
            == OAuthVerificationRequestStatus.NOT_STARTED,
        )
        .options(
            joinedload(OAuthVerificationRequest.user_account),
        )
        .first()
    )

    if not verification_request:
        raise HTTPException(
            status_code=400,
            detail="Either Verification Link is invalid or has expired. Please try again.",
        )

    user = verification_request.user_account
    if verification_request.created_at + user.token_expiry < now:
        session.query(OAuthVerificationRequest).filter(
            OAuthVerificationRequest.id == verification_request.id,
        ).update(
            {
                OAuthVerificationRequest.status: OAuthVerificationRequestStatus.EXPIRED,
            }
        )
        session.commit()
        raise HTTPException(
            status_code=422,
            detail="Login Link has expired. Please start again.",
        )

    nonce = shortuuid.uuid()
    session.query(OAuthVerificationRequest).filter(
        OAuthVerificationRequest.id == verification_request.id,
    ).update(
        {
            OAuthVerificationRequest.nonce: nonce,
            OAuthVerificationRequest.status: OAuthVerificationRequestStatus.IN_PROGRESS,
            OAuthVerificationRequest.oauth_flow_started_at: utcnow(),
        }
    )
    session.commit()
    return await config.google_oauth_client.authorize_redirect(
        request,
        redirect_uri=request.url_for(
            request,
            "oauth_google_callback",
            scheme=config.url_scheme,
        ),
        state=verification_request_id,
        nonce=nonce,
    )


class OAuthCallBackException(Exception):
    def __init__(self, status: OAuthVerificationRequestStatus, message: str) -> None:
        super().__init__(message)
        self.message = message
        self.status = status

    def __str__(self) -> str:
        return self.message


def _verify_oauth_callback_request(request: Request, logger: Logger) -> tuple[str, str]:
    error = request.query_params.get("error", None)
    code = request.query_params.get("code", None)
    verification_request_uuid = request.query_params.get("state")
    error_description = None
    if error:
        logger.error(
            f"Error while login using google oauth: {error_description}, Verification Request UUId: {verification_request_uuid}"
        )
        error_description = request.query_params.get("error_description")
    elif code is None or verification_request_uuid is None:
        logger.error("Error while login using google oauth: State/Code is not passed")
        error_description = "Google Authentication Failed. Please try again"

    if error_description:
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.FAILED, error_description
        )

    return code, verification_request_uuid


def _verify_oauth_verification_request(
    verification_request_uuid: str, session: Session, logger: Logger
) -> OAuthVerificationRequest:
    now = utcnow()
    verification_request = (
        session.query(OAuthVerificationRequest)
        .options(joinedload(OAuthVerificationRequest.user_account))
        .filter(
            OAuthVerificationRequest.uuid == verification_request_uuid,
        )
        .first()
    )
    if not verification_request:
        logger.error(
            f"Error while login using google oauth: Invalid verification_request_uuid: {verification_request_uuid}"
        )
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.FAILED,
            "Google Authentication Failed. Please try again",
        )
    user = verification_request.user_account
    if verification_request.created_at + user.token_expiry < now:
        logger.warn(
            f"Google Authentication Request Expired. Verification Request UUId: {verification_request_uuid}"
        )
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.EXPIRED,
            "Google Authentication Request Expired.",
        )
    elif verification_request.archived_at is not None:
        logger.warn(
            f"Google Authentication Request Archived. Verification Request UUId: {verification_request_uuid}"
        )
        raise OAuthCallBackException(
            OAuthVerificationRequestStatus.ARCHIVED,
            "Google Authentication Request Expired.",
        )

    return verification_request


@google_oauth_router.get(
    "/google/callback",
)
async def oauth_google_callback(
    request: Request, config: ConfigDep, session: DbSession, logger: LoggerDep
):
    code = None
    http_status_code = None
    response = None
    status = None
    try:
        code, verification_request_uuid = _verify_oauth_callback_request(
            request, logger
        )
        verification_request = _verify_oauth_verification_request(
            verification_request_uuid, session, logger
        )
        status = OAuthVerificationRequestStatus.CALLBACK_COMPLETED
        response = {"authorization_code": code}
        http_status_code = 200
    except OAuthCallBackException as e:
        status = e.status
        code = None
        http_status_code = 422
        response = {"error": e.message}

    session.query(OAuthVerificationRequest).filter(
        OAuthVerificationRequest.id == verification_request.id,
    ).update(
        {
            OAuthVerificationRequest.status: status,
            OAuthVerificationRequest.oauth_callback_completed_at: utcnow(),
            OAuthVerificationRequest.authorization_code: code,
        }
    )
    session.commit()
    return JSONResponse(
        status_code=http_status_code,
        content=response,
    )
