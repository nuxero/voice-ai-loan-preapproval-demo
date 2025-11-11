import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

import aiohttp
from dotenv import load_dotenv
from fastapi import Body, FastAPI, Form, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, EmailStr

# Load environment variables from .env file
load_dotenv()

from bot import main
from email_service import get_email_service

# Get the base directory
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI()

# Mount static files directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/")
async def start_call(request: Request):
    logger.info("Received POST request for TwiML")
    
    # Use environment variable if set, otherwise construct from request
    ws_url = os.getenv("WEBSOCKET_URL")
    if not ws_url:
        forwarded_proto = request.headers.get("x-forwarded-proto")
        is_https = forwarded_proto == "https" or request.url.scheme == "https"
        scheme = "wss" if is_https else "ws"
        host = request.headers.get('host')
        ws_url = f"{scheme}://{host}/ws"
    logger.info(f"Generated WebSocket URL: {ws_url}")
    xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}"></Stream>
  </Connect>
  <Pause length="40"/>
</Response>'''
    return HTMLResponse(content=xml_content, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    start_data = websocket.iter_text()
    await start_data.__anext__()
    call_data = json.loads(await start_data.__anext__())
    stream_sid = call_data["start"]["streamSid"]
    call_sid = call_data["start"].get("callSid")
    logger.info(f"Starting voice AI session with stream_sid: {stream_sid}, call_sid: {call_sid}")
    company_name = os.getenv("COMPANY_NAME")
    await main(websocket, stream_sid, call_sid, company_name=company_name)


@app.get("/loan-application")
async def loan_application_form(
    legal_name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    zip_code: Optional[str] = None,
):
    """Serve the loan application form with optional pre-fill parameters
    
    Query parameters:
    - legal_name: Pre-fill the legal name field
    - email: Pre-fill the email field
    - phone: Pre-fill the phone field
    - zip_code: Pre-fill the zip code field (if added to form)
    
    Example: /loan-application?legal_name=John%20Doe&email=john@example.com&phone=5551234567
    """
    template_path = TEMPLATES_DIR / "loan_application.html"
    try:
        html_content = template_path.read_text(encoding="utf-8")
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        logger.error(f"Template file not found: {template_path}")
        return HTMLResponse(
            content="<h1>Template file not found</h1>",
            status_code=500
        )


def _extract_decision_outcome(payload: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Attempt to extract a decision outcome and optional reason from a DecisionRules response.
    This utility is defensive and works even when multiple decision objects are returned.
    Denials take priority over approvals, which take priority over manual reviews.
    """

    def _collect_decisions(node: Any) -> List[Tuple[str, Optional[str]]]:
        collected: List[Tuple[str, Optional[str]]] = []

        if node is None:
            return collected

        if isinstance(node, dict):
            for decision_key in ("decision", "result", "status", "outcome", "approved"):
                value = node.get(decision_key)
                if isinstance(value, str):
                    reason_value = (
                        node.get("reason")
                        or node.get("explanation")
                        or node.get("details")
                    )
                    if isinstance(reason_value, dict):
                        reason_value = json.dumps(reason_value)
                    elif reason_value is not None:
                        reason_value = str(reason_value)
                    collected.append((value, reason_value))

            for nested_key in ("outputs", "result", "results", "data"):
                nested = node.get(nested_key)
                if nested is not None:
                    collected.extend(_collect_decisions(nested))
            return collected

        if isinstance(node, list):
            for item in node:
                collected.extend(_collect_decisions(item))
            return collected

        if isinstance(node, str):
            collected.append((node, None))

        return collected

    def _choose_preferred(decisions: List[Tuple[str, Optional[str]]]) -> Tuple[Optional[str], Optional[str]]:
        if not decisions:
            return None, None

        def _normalize(text: str) -> str:
            return text.lower().strip()

        def _matches_any(text: str, keywords: Tuple[str, ...]) -> bool:
            normalized = _normalize(text)
            return any(keyword in normalized for keyword in keywords)

        def _merge_reasons(items: List[Tuple[str, Optional[str]]]) -> Optional[str]:
            reasons = [reason for _, reason in items if reason]
            if not reasons:
                return items[0][1]
            unique_reasons = list(dict.fromkeys(reasons))
            return "; ".join(unique_reasons)

        priority_groups = [
            ("deny", "declin", "reject"),
            ("approve", "yes", "true"),
            ("review", "manual"),
        ]

        for keywords in priority_groups:
            matches = [
                (decision, reason)
                for decision, reason in decisions
                if _matches_any(decision, keywords)
            ]
            if matches:
                return matches[0][0], _merge_reasons(matches)

        return decisions[0]

    decisions = _collect_decisions(payload)
    return _choose_preferred(decisions)


async def _fetch_mock_credit_score(legal_name: str, ssn_last4: str) -> dict:
    """
    Mock fetching a credit score from a third-party service.

    Although this is a mock, we keep the async interface and logging to mirror the real workflow.
    """
    credit_api_url = os.getenv("CREDIT_SCORE_API_URL", "https://mock-credit-bureau.local/credit-score")
    logger.info(f"Requesting credit score from {credit_api_url} for {legal_name} (SSN last4: {ssn_last4})")
    await asyncio.sleep(0.1)

    mocked_response = {
        "creditScore": 720,
        "creditHistory": "Good standing with no delinquencies in the past 24 months.",
        "source": "MockCreditBureau",
        "requestedAt": datetime.utcnow().isoformat() + "Z",
    }
    logger.debug(f"Mock credit score response: {json.dumps(mocked_response)}")
    return mocked_response


@app.post("/loan-application")
async def submit_loan_application(
    legal_name: str = Form(...),
    dob: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    ssn_last4: str = Form(...),
    monthly_income: float = Form(...),
    requested_amount: float = Form(...),
    loan_duration_years: int = Form(...),
    purpose_of_loan: str = Form(...),
    terms_consent: Optional[str] = Form(None),
):
    """Handle loan application form submission"""
    try:
        # Prepare application data
        application_data = {
            "personal_info": {
                "legal_name": legal_name,
                "dob": dob,
                "email": email,
                "phone": phone,
                "ssn_last4": ssn_last4,
            },
            "financial": {
                "monthly_income": monthly_income,
            },
            "loan_details": {
                "requested_amount": requested_amount,
                "loan_duration_years": loan_duration_years,
                "purpose_of_loan": purpose_of_loan,
            },
            "consents": {
                "terms": terms_consent is not None,
            },
        }

        total_months = max(loan_duration_years * 12, 1)
        estimated_monthly_payment = round(requested_amount / total_months, 2)
        debt_to_income_ratio = (
            round(estimated_monthly_payment / monthly_income, 2)
            if monthly_income
            else None
        )

        application_data["loan_details"]["estimated_monthly_payment"] = estimated_monthly_payment
        application_data["loan_details"]["debt_to_income_ratio"] = debt_to_income_ratio
        
        # Log the application (in production, you'd save this to a database)
        logger.info(f"Loan application submitted: {legal_name} ({email})")
        logger.debug(f"Application data: {json.dumps(application_data, indent=2)}")
        
        application_id = f"APP-{hash(legal_name + email + dob) % 1000000:06d}"

        credit_profile = await _fetch_mock_credit_score(legal_name, ssn_last4)
        credit_score = credit_profile.get("creditScore")

        application_data["financial"]["credit_score"] = credit_score

        decision_rules_api_key = os.getenv("DECISION_RULES_API_KEY") or os.getenv("DECISIONRULES_SOLVER_KEY")
        decision_rules_rule_id = os.getenv("DECISION_RULES_RULE_ID") or os.getenv("DECISIONRULES_RULE_ID")
        decision_rules_host = (
            os.getenv("DECISION_RULES_HOST")
            or os.getenv("DECISIONRULES_HOST")
            or "https://api.decisionrules.io"
        )

        decision_response_payload: Any = None
        decision_outcome: Optional[str] = None
        decision_reason: Optional[str] = None

        if not decision_rules_api_key or not decision_rules_rule_id:
            raise ValueError("DecisionRules configuration is missing. Please set DECISION_RULES_API_KEY (or DECISIONRULES_SOLVER_KEY) and DECISION_RULES_RULE_ID.")

        decision_input = {
            "ApplicationId": application_id,
            "ApplicantName": legal_name,
            "ApplicantEmail": email,
            "MonthlyIncome": monthly_income,
            "RequestedAmount": requested_amount,
            "LoanDurationYears": loan_duration_years,
            "EstimatedMonthlyPayment": estimated_monthly_payment,
            "PurposeOfLoan": purpose_of_loan,
            "ConsentGiven": terms_consent is not None,
            "DebtToIncomeRatio": debt_to_income_ratio,
            "CreditScore": credit_score,
        }

        decision_url = f"{decision_rules_host.rstrip('/')}/rule/solve/{decision_rules_rule_id}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {decision_rules_api_key}",
        }

        logger.info(f"Submitting application {application_id} to DecisionRules at {decision_url}")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.post(decision_url, headers=headers, json={"data": decision_input}) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        logger.error(f"Decision Rules API error {response.status}: {error_text}")
                        raise ValueError(f"Decision Rules API error {response.status}")
                    decision_response_payload = await response.json()
                    logger.info(f"Decision received for {application_id}: {json.dumps(decision_response_payload)}")
        except aiohttp.ClientError as exc:
            logger.error(f"Failed to reach Decision Rules API: {exc}")
            raise ValueError("Unable to reach Decision Rules API") from exc

        decision_outcome, decision_reason = _extract_decision_outcome(decision_response_payload)
        logger.info(f"Parsed decision for {application_id}: outcome={decision_outcome}, reason={decision_reason}")

        if not decision_outcome:
            raise ValueError("Decision Rules response did not include a recognizable decision outcome")

        email_service = get_email_service()
        email_sent = False
        email_error: Optional[str] = None

        decision_outcome_normalized = decision_outcome.lower()
        is_approved = "approve" in decision_outcome_normalized or "yes" in decision_outcome_normalized or decision_outcome_normalized == "true"

        if not email_service.api_key:
            email_error = "MAILERSEND_API_KEY not configured"
            logger.error("Cannot send decision email: MAILERSEND_API_KEY not configured")
        else:
            if is_approved:
                email_sent = await email_service.send_approval_notification(
                    email=email,
                    name=legal_name,
                    approval_amount=requested_amount,
                    application_id=application_id
                )
                if not email_sent:
                    email_error = "Failed to send approval email"
            else:
                email_sent = await email_service.send_denial_notification(
                    email=email,
                    name=legal_name,
                    reason=decision_reason,
                    application_id=application_id
                )
                if not email_sent:
                    email_error = "Failed to send denial email"

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Application submitted successfully",
                "application_id": application_id,
                "credit_assessment": credit_profile,
                "decision": {
                    "outcome": decision_outcome,
                    "reason": decision_reason,
                    "raw": decision_response_payload,
                },
                "email": {
                    "sent": email_sent,
                    "error": email_error,
                },
            }
        )
    
    except Exception as e:
        logger.error(f"Error processing loan application: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"success": False, "detail": str(e)}
        )


# Email service test endpoint

class SendEmailRequest(BaseModel):
    """Request model for sending test email"""
    email: EmailStr
    name: str
    link: str
    expires_in_hours: Optional[int] = 24


@app.post("/test-email")
async def test_send_email(request: SendEmailRequest = Body(...)):
    """Test endpoint to send an email with application link via MailerSend"""
    try:
        email_service = get_email_service()
        
        if not email_service.api_key:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "MAILERSEND_API_KEY not configured",
                    "message": "Please set MAILERSEND_API_KEY in your environment variables"
                }
            )
        
        success = await email_service.send_application_link(
            email=request.email,
            name=request.name,
            link=request.link,
            expires_in_hours=request.expires_in_hours
        )
        
        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Email sent successfully",
                    "recipient": {
                        "email": request.email,
                        "name": request.name
                    },
                    "link": request.link,
                    "expires_in_hours": request.expires_in_hours
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "Failed to send email"
                }
            )
        
    except Exception as e:
        logger.error(f"Error sending test email: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "message": "An error occurred while sending the email"
            }
        )