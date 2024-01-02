from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from sqlalchemy import text

from custom_gpts_paywall.dependencies import DbSession, LoggerDep
from custom_gpts_paywall.routers.auth import get_current_user

from fastapi.templating import Jinja2Templates

root_router = APIRouter()

templates = Jinja2Templates(directory="templates")


@root_router.get("/privacy-policy", response_class=HTMLResponse, name="privacy_policy")
async def privacy_policy():
    return """
    <html>
        <body>
            <h1>Privacy Policy for GPT Verifier</h1>
            <p><strong>Effective Date: 19th Nov, 2023</strong></p>
            <h2>Overview</h2>
            <p>GPT Verifier, powered by custom GPT technology, offers an email verification service. This privacy policy describes how we collect, use, and safeguard your personal information in relation to this service.</p>
            <h2>Data Collection</h2>
            <ol>
                <li><strong>Email Addresses:</strong> We collect email addresses submitted by users for the purpose of verification.</li>
                <li><strong>Verification Data:</strong> Information generated or related to the email verification process is also collected.</li>
            </ol>
            <h2>Use of Data</h2>
            <p>Your data is used exclusively for:</p>
            <ol>
                <li>Conducting email verification processes.</li>
                <li>Enhancing the accuracy and efficiency of our verification service.</li>
            </ol>
            <h2>Data Sharing and Disclosure</h2>
            <ol>
                <li><strong>Service Providers:</strong> We may share data with trusted third parties who assist us in operating our service, conducting our business, or serving our users, so long as those parties agree to keep this information confidential.</li>
                <li><strong>Legal Requirements:</strong> We may disclose your information when we believe release is appropriate to comply with the law, enforce our site policies, or protect ours or others' rights, property, or safety.</li>
            </ol>
            <h2>Data Security</h2>
            <p>We implement a variety of security measures to maintain the safety of your personal information.</p>
            <h2>Changes to This Policy</h2>
            <p>We reserve the right to modify this policy at any time. Changes will be posted on this page with an updated effective date.</p>
            <h2>Contact Us</h2>
            <p>For questions about this privacy policy, please contact us at contact@vertexcover.io.</p>
        </body>
    </html>
    """


@root_router.get("/", include_in_schema=False, response_class=FileResponse)
def root(logger: LoggerDep, current_user: dict = Depends(get_current_user)):
    logger.info("Root endpoint hit")
    user_details = current_user.get("sub") if current_user else "Not logged in"
    gpt_applications = current_user.get("gpt_applications", [])
    logger.info(gpt_applications)
    logger.info(user_details)
    return templates.TemplateResponse("home.html", {"request": current_user, "user_details": user_details, "gpt_applications": gpt_applications})


@root_router.get(
    "/healthcheck",
    include_in_schema=False,
)
def healthcheck(session: DbSession, logger: LoggerDep):
    try:
        session.execute(text("SELECT 1"))
        return {"api_status": "success", "db_status": "success"}
    except Exception as ex:
        logger.error(f"Error while checking connection to db: {ex}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Error while connecting with database"
        )
