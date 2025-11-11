"""
MailerSend Email Service

Handles email delivery for the loan pre-approval application via MailerSend API.

Usage:
    from email_service import get_email_service
    
    email_service = get_email_service()
    success = await email_service.send_application_link(
        email="user@example.com",
        name="John Doe",
        link="https://example.com/loan-application?token=abc123"
    )

Environment Variables:
    MAILERSEND_API_KEY: MailerSend API key
    MAILERSEND_FROM_EMAIL: Sender email address (defaults to "loans@yourcompany.com")
"""

import os
from typing import Optional
from loguru import logger
import aiohttp


class MailerSendService:
    """Service for sending emails via MailerSend API"""
    
    def __init__(self):
        self.api_key = os.getenv("MAILERSEND_API_KEY")
        self.from_email = os.getenv("MAILERSEND_FROM_EMAIL", "loans@yourcompany.com")
        self.from_name = "Loan Pre-Approval Service"
        self.api_url = "https://api.mailersend.com/v1/email"
        
        if not self.api_key:
            logger.warning("MAILERSEND_API_KEY not set. Email service will not work.")
    
    async def send_application_link(
        self,
        email: str,
        name: str,
        link: str,
        expires_in_hours: int = 24
    ) -> bool:
        """
        Send a secure application link via email.
        
        Args:
            email: Recipient email address
            name: Recipient name
            link: Secure application link URL
            expires_in_hours: Link expiration time in hours (default: 24)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.api_key:
            logger.error("Cannot send email: MAILERSEND_API_KEY not configured")
            return False
        
        subject = "Your Secure Loan Application Link"
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 24px;
                    background-color: #007bff;
                    color: #ffffff;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Hi {name},</h2>
                <p>Thank you for your interest in our loan pre-approval service.</p>
                <p>Please complete your application using this secure link:</p>
                <p>
                    <a href="{link}" class="button">Complete Your Application</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #007bff;">{link}</p>
                <p><strong>This link will expire in {expires_in_hours} hours.</strong></p>
                <div class="footer">
                    <p>If you did not request this link, please ignore this email.</p>
                    <p>This is an automated message from the Loan Pre-Approval Service.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_text_content = f"""
Hi {name},

Thank you for your interest in our loan pre-approval service.

Please complete your application using this secure link:
{link}

This link will expire in {expires_in_hours} hours.

If you did not request this link, please ignore this email.

This is an automated message from the Loan Pre-Approval Service.
        """
        
        return await self._send_email(
            email=email,
            name=name,
            subject=subject,
            html_content=html_content,
            plain_text_content=plain_text_content
        )
    
    async def send_application_confirmation(
        self,
        email: str,
        name: str,
        application_id: str
    ) -> bool:
        """
        Send application confirmation email.
        
        Args:
            email: Recipient email address
            name: Recipient name
            application_id: Application ID/reference number
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.api_key:
            logger.error("Cannot send email: MAILERSEND_API_KEY not configured")
            return False
        
        subject = "Loan Application Received"
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .application-id {{
                    background-color: #f5f5f5;
                    padding: 10px;
                    border-radius: 5px;
                    font-family: monospace;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Hi {name},</h2>
                <p>Thank you for submitting your loan application.</p>
                <p>We have received your application and it is currently being processed.</p>
                <p><strong>Application ID:</strong></p>
                <div class="application-id">{application_id}</div>
                <p>We will review your application and contact you soon with a decision.</p>
                <p>If you have any questions, please contact our support team.</p>
            </div>
        </body>
        </html>
        """
        
        plain_text_content = f"""
Hi {name},

Thank you for submitting your loan application.

We have received your application and it is currently being processed.

Application ID: {application_id}

We will review your application and contact you soon with a decision.

If you have any questions, please contact our support team.
        """
        
        return await self._send_email(
            email=email,
            name=name,
            subject=subject,
            html_content=html_content,
            plain_text_content=plain_text_content
        )
    
    async def send_approval_notification(
        self,
        email: str,
        name: str,
        approval_amount: float,
        application_id: Optional[str] = None
    ) -> bool:
        """
        Send loan approval notification email.
        
        Args:
            email: Recipient email address
            name: Recipient name
            approval_amount: Approved loan amount
            application_id: Optional application ID
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.api_key:
            logger.error("Cannot send email: MAILERSEND_API_KEY not configured")
            return False
        
        subject = "Loan Pre-Approval Update"
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .amount {{
                    font-size: 32px;
                    font-weight: bold;
                    color: #28a745;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Hi {name},</h2>
                <p>We reviewed your loan application and completed the initial assessment.</p>
                <p><strong>Approved Amount:</strong></p>
                <div class="amount">${approval_amount:,.2f}</div>
                {f'<p><strong>Application ID:</strong> {application_id}</p>' if application_id else ''}
                <p>Our lending team will reach out to confirm a few details and guide you through final approval.</p>
                <p>If you have questions in the meantime, reply to this email or call us at (555) 010-0000.</p>
                <p>Thank you for working with us.</p>
            </div>
        </body>
        </html>
        """
        
        plain_text_content = f"""
Hi {name},

We reviewed your loan application and completed the initial assessment.

Pre-Approved Amount: ${approval_amount:,.2f}
{f'Application ID: {application_id}' if application_id else ''}

Our lending team will reach out to confirm a few details and guide you through final approval.
If you have questions in the meantime, reply to this email or call us at (555) 010-0000.

Thank you for working with us.
        """
        
        return await self._send_email(
            email=email,
            name=name,
            subject=subject,
            html_content=html_content,
            plain_text_content=plain_text_content
        )
    
    async def send_denial_notification(
        self,
        email: str,
        name: str,
        reason: Optional[str] = None,
        application_id: Optional[str] = None
    ) -> bool:
        """
        Send loan denial notification email.
        
        Args:
            email: Recipient email address
            name: Recipient name
            reason: Optional reason for denial
            application_id: Optional application ID
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.api_key:
            logger.error("Cannot send email: MAILERSEND_API_KEY not configured")
            return False
        
        subject = "Loan Application Update"
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Hi {name},</h2>
                <p>Thank you for your loan application.</p>
                <p>Unfortunately, we are unable to approve your application at this time.</p>
                {f'<p><strong>Reason:</strong> {reason}</p>' if reason else ''}
                {f'<p><strong>Application ID:</strong> {application_id}</p>' if application_id else ''}
                <p>We encourage you to apply again in the future as your financial situation may change.</p>
                <p>If you have any questions, please contact our support team.</p>
            </div>
        </body>
        </html>
        """
        
        plain_text_content = f"""
Hi {name},

Thank you for your loan application.

Unfortunately, we are unable to approve your application at this time.

{f'Reason: {reason}' if reason else ''}
{f'Application ID: {application_id}' if application_id else ''}

We encourage you to apply again in the future as your financial situation may change.

If you have any questions, please contact our support team.
        """
        
        return await self._send_email(
            email=email,
            name=name,
            subject=subject,
            html_content=html_content,
            plain_text_content=plain_text_content
        )
    
    async def _send_email(
        self,
        email: str,
        name: str,
        subject: str,
        html_content: str,
        plain_text_content: str
    ) -> bool:
        """
        Internal method to send email via MailerSend API.
        
        Args:
            email: Recipient email address
            name: Recipient name
            subject: Email subject
            html_content: HTML email content
            plain_text_content: Plain text email content
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.api_key:
            return False
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        # MailerSend API structure based on project documentation
        # API endpoint: https://api.mailersend.com/v1/email
        # Expected status code: 202 (Accepted)
        data = {
            "from": {
                "email": self.from_email,
                "name": self.from_name
            },
            "to": [
                {
                    "email": email,
                    "name": name
                }
            ],
            "subject": subject,
            "html": html_content,
            "text": plain_text_content  # Plain text fallback for email clients
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 202:
                        logger.info(f"Email sent successfully to {email}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to send email to {email}. Status: {response.status}, Response: {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Error sending email to {email}: {str(e)}")
            return False


# Global service instance
_email_service: Optional[MailerSendService] = None


def get_email_service() -> MailerSendService:
    """Get or create the global email service instance"""
    global _email_service
    if _email_service is None:
        _email_service = MailerSendService()
    return _email_service