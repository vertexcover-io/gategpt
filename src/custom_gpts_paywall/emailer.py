import requests
from custom_gpts_paywall.config import EnvConfig
from custom_gpts_paywall.models import User
import boto3

VERIFICATION_EMAIL_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Verification OTP</title>
</head>
<body>
    <table align="center" border="0" cellpadding="0" cellspacing="0" width="600">
        <tr>
            <td align="center" bgcolor="#3498db" style="padding: 40px 0 30px 0;">
                <h1 style="color: #ffffff;">Email Verification OTP</h1>
            </td>
        </tr>
        <tr>
            <td bgcolor="#ffffff" style="padding: 40px 30px 40px 30px;">
                <p>Hello,</p>
                <p>Your one-time password (OTP) to start using Custom GPT: {custom_gpt} is:</p>
                <p style="font-size: 24px; font-weight: bold; color: #3498db;">{otp}</p>
                <p>Please enter this OTP when prompted inside the custom gpt. 
                 This code will expire in a short time, so make sure to use it promptly.</p>
                <p>If you did not request this verification, you can safely ignore this email.</p>
                <p>Thank you for using our service!</p>
            </td>
        </tr>
        <tr>
            <td bgcolor="#3498db" style="padding: 30px 30px 30px 30px;">
                <p align="center" style="color: #ffffff;">&copy; 2023 Vertexcover Labs</p>
            </td>
        </tr>
    </table>
</body>
</html>
"""

VERIFICATION_EMAIL_TEXT_CONTENT = """
Your one-time password (OTP) to start using Custom GPT: {custom_gpt} is: {otp}. Please enter this OTP when prompted inside the custom gpt. 
This code will expire in a short time, so make sure to use it promptly. If you did not request this verification, you can safely ignore this email. Thank you for using our service!
"""

VERIFICATION_EMAIL_SUBJECT = "OTP Verification for Custom GPT: {custom_gpt}"


def send_verification_email(env_config: EnvConfig, user: User, otp: str):
    subject = VERIFICATION_EMAIL_SUBJECT.format(custom_gpt=user.name)
    html_content = VERIFICATION_EMAIL_HTML_TEMPLATE.format(
        custom_gpt=user.name, otp=otp
    )
    text_content = VERIFICATION_EMAIL_TEXT_CONTENT.format(custom_gpt=user.name, otp=otp)
    to_email = [{"email": user.email}]
    from_email = [{"email": env_config.email_from}]

    client = boto3.client(
        "ses", region_name=env_config.aws_region
    )  # Replace 'your_region' with your desired AWS region

    response = client.send_email(
        Source=from_email[0]["email"],
        Destination={"ToAddresses": [to_email[0]["email"]]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": text_content}, "Html": {"Data": html_content}},
        },
    )
    print("Sending Email Response", response["MessageId"])
