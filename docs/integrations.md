# Integration Documentation

Core third-party service integrations for the Voice AI Loan Pre-Approval Demo.

## Integration Overview

This system integrates with:
1. **Twilio** - Receives call webhooks, streams audio
2. **Pipecat** - Voice pipeline (STT/LLM/TTS services)
3. **MailerSend** - Email delivery for secure application links
4. **DecisionRules** - Business rules engine for loan evaluation

---

## 1. Twilio Integration

### Purpose
- Receive incoming call webhooks
- Real-time audio streaming via WebSocket

### Service Details
- **Provider**: Twilio Inc.
- **Documentation**: https://www.twilio.com/docs
- **API**: Voice API, Media Streams

### Configuration

**Environment Variables**:
```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
```

### Webhook Endpoint

**Endpoint**: `POST /`

**Process**:
1. Twilio sends POST request when call received
2. Application returns TwiML with WebSocket URL
3. Twilio connects to WebSocket for audio streaming

**TwiML Response**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://your-domain.com/ws"></Stream>
  </Connect>
  <Pause length="40"/>
</Response>
```

**Setup**:
1. Configure webhook URL in Twilio console: `https://your-domain.com/`
2. Set for incoming calls

### WebSocket Connection
- Protocol: Twilio Media Stream Protocol
- Endpoint: `/ws`
- Format: Bidirectional audio streaming

---

## 2. Pipecat Integration

### Purpose
- Real-time voice processing pipeline
- Orchestrates STT (Deepgram) → LLM (OpenAI) → TTS (Cartesia)

### Service Details
- **Framework**: Pipecat
- **API Reference**: https://reference-server.pipecat.ai/en/latest/
- **Version**: 0.0.63

### Pipeline Architecture
```
WebSocket Input → STT → LLM → TTS → WebSocket Output
```

### Services Used
- **Deepgram STT**: Speech-to-text (`nova-2` model)
- **OpenAI GPT-4.1 Mini**: Conversational AI
- **Cartesia TTS**: Text-to-speech (`sonic` models)

### Configuration

**Environment Variables**:
```bash
DEEPGRAM_API_KEY=your_deepgram_api_key
OPENAI_API_KEY=sk-...
CARTESIA_API_KEY=your_cartesia_api_key
CARTESIA_WELCOME_VOICE_ID=cartesia_voice_id_for_welcome_agent
CARTESIA_LOAN_VOICE_ID=cartesia_voice_id_for_loan_agent  # optional; falls back to welcome voice
```

### Implementation

**Pipeline Setup** (`bot.py`):
```python
from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketTransport

# STT
stt = DeepgramSTTService(
    api_key=os.getenv("DEEPGRAM_API_KEY"),
    live_options=LiveOptions(model="nova-2", language="en-US")
)

# LLM
llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4.1-mini")

# TTS (Cartesia)
tts = CartesiaTTSService(
    api_key=os.getenv("CARTESIA_API_KEY"),
    voice_id=os.getenv("CARTESIA_WELCOME_VOICE_ID"),
    model=os.getenv("CARTESIA_MODEL", "sonic-3"),
)

# Pipeline
pipeline = Pipeline([transport.input(), stt, llm, tts, transport.output()])
```

---

## 3. MailerSend Integration

### Purpose
- Email delivery for secure application links
- Application confirmations and notifications

### Service Details
- **Provider**: MailerSend
- **Documentation**: https://www.npmjs.com/package/mailersend
- **API**: MailerSend API

### Configuration

**Environment Variables**:
```bash
MAILERSEND_API_KEY=your_mailersend_api_key
MAILERSEND_FROM_EMAIL=loans@yourcompany.com
```

### Implementation Pattern

**Python Integration** (using MailerSend API):
```python
import requests

async def send_application_link(email, name, link):
    headers = {
        "Authorization": f"Bearer {os.getenv('MAILERSEND_API_KEY')}",
        "Content-Type": "application/json"
    }
    
    data = {
        "from": {
            "email": os.getenv("MAILERSEND_FROM_EMAIL"),
            "name": "Loan Pre-Approval Service"
        },
        "to": [
            {
                "email": email,
                "name": name
            }
        ],
        "subject": "Your Secure Loan Application Link",
        "html": f"""
        <html>
        <body>
            <h2>Hi {name},</h2>
            <p>Thank you for your interest in our loan pre-approval service.</p>
            <p>Please complete your application using this secure link:</p>
            <p><a href="{link}">{link}</a></p>
            <p><strong>This link will expire in 24 hours.</strong></p>
        </body>
        </html>
        """
    }
    
    response = requests.post(
        "https://api.mailersend.com/v1/email",
        headers=headers,
        json=data
    )
    
    return response.status_code == 202
```

### Email Templates
- Application link email (with secure link)
- Application confirmation
- Approval notification
- Denial notification

---

## 4. DecisionRules Integration

### Purpose
- Business rules evaluation for loan eligibility
- Risk assessment and compliance checking
- Provisional loan amount calculation

### Service Details
- **Provider**: DecisionRules
- **Website**: https://www.decisionrules.io/
- **API**: https://api.decisionrules.io
- **Documentation**: https://docs.decisionrules.io/doc

### Configuration

**Environment Variables**:
```bash
DECISIONRULES_SOLVER_KEY=your_solver_key
DECISIONRULES_HOST=https://api.decisionrules.io
DECISIONRULES_RULE_ALIAS=loan-approval
```

### Integration Pattern

**Python SDK**:
```python
from decisionrules import DecisionRules

solver = DecisionRules(
    solver_key=os.getenv("DECISIONRULES_SOLVER_KEY"),
    host=os.getenv("DECISIONRULES_HOST", "https://api.decisionrules.io")
)

result = await solver.solve(
    rule_alias=os.getenv("DECISIONRULES_RULE_ALIAS", "loan-approval"),
    data={
        "credit_score": credit_score,
        "monthly_income": monthly_income,
        "requested_amount": requested_amount,
        "zip_code": zip_code,
        "ssn_last4": ssn_last4,
        "dob": dob,
        "purpose_of_loan": purpose_of_loan
    },
    version="latest"
)
```

### Input Data Structure
```json
{
  "credit_score": 720,
  "monthly_income": 5000,
  "requested_amount": 10000,
  "zip_code": "90210",
  "ssn_last4": "1234",
  "dob": "1990-01-15",
  "purpose_of_loan": "debt_consolidation"
}
```

### Expected Output
```json
{
  "approved": true,
  "provisional_amount": 15000,
  "interest_rate_range": {
    "min": 5.5,
    "max": 8.5
  },
  "terms": {
    "min_months": 12,
    "max_months": 60
  },
  "risk_level": "low",
  "requires_review": false,
  "reason": "Meets all eligibility criteria"
}
```

### Business Rules
- Credit score thresholds
- Debt-to-income ratio limits
- Loan amount maximums
- Geographic risk factors
- Regulatory compliance checks

### Setup Steps
1. Create DecisionRules account
2. Create workspace
3. Define loan approval rules (Decision Tables, Flows, or Scripts)
4. Publish rules
5. Get solver key from API Keys section
6. Configure rule alias

---

## Environment Variables Summary

```bash
# Twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...

# Pipecat Services
DEEPGRAM_API_KEY=...
OPENAI_API_KEY=sk-...

# MailerSend
MAILERSEND_API_KEY=...
MAILERSEND_FROM_EMAIL=loans@yourcompany.com

# DecisionRules
DECISIONRULES_SOLVER_KEY=...
DECISIONRULES_HOST=https://api.decisionrules.io
DECISIONRULES_RULE_ALIAS=loan-approval

# Optional
WEBSOCKET_URL=wss://your-domain.com/ws
```

---

## Error Handling

### General Patterns
- **API Errors**: Log with full context, retry with exponential backoff
- **Rate Limits**: Queue requests, respect rate limit headers
- **Timeouts**: Configurable timeout values, graceful degradation
- **Connection Failures**: Automatic reconnection where supported

### Service-Specific
- **Twilio**: Webhook failures logged, Twilio retries automatically
- **Pipecat**: Pipeline errors handled gracefully, connection cleanup
- **MailerSend**: Retry failed sends, validate email addresses
- **DecisionRules**: Escalate to human review on evaluation errors

---

## Security Considerations

- **API Keys**: Store in environment variables, never commit
- **HTTPS/WSS**: All production communications must be secure
- **Data Validation**: Validate all inputs before API calls
- **Error Messages**: Don't expose sensitive information in errors
