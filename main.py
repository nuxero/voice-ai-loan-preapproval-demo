import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, Request, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import HTMLResponse
from loguru import logger
from typing import Optional
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
    await main(websocket, stream_sid, call_sid)


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


@app.post("/loan-application")
async def submit_loan_application(
    legal_name: str = Form(...),
    dob: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    ssn_last4: str = Form(...),
    monthly_income: float = Form(...),
    requested_amount: float = Form(...),
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
                "purpose_of_loan": purpose_of_loan,
            },
            "consents": {
                "terms": terms_consent is not None,
            },
        }
        
        # Log the application (in production, you'd save this to a database)
        logger.info(f"Loan application submitted: {legal_name} ({email})")
        logger.debug(f"Application data: {json.dumps(application_data, indent=2)}")
        
        # In a real application, you would:
        # 1. Save to database
        # 2. Run credit check
        # 3. Send confirmation email
        # 4. Trigger approval process
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Application submitted successfully",
                "application_id": f"APP-{hash(legal_name + email + dob) % 1000000:06d}",
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