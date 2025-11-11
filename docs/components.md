# Component Documentation

Detailed documentation of all components in the Voice AI Loan Pre-Approval Demo system.

## Core Components

### 1. FastAPI Application (`main.py`)

**Purpose**: Main web application server and API endpoint handler

**Key Responsibilities**:
- Webhook handling for Twilio calls
- WebSocket connection management
- Form serving and submission processing
- Static file serving
- CORS middleware configuration

**Key Functions**:
- `start_call()`: Handles Twilio webhook, generates TwiML with WebSocket URL
- `websocket_endpoint()`: Accepts WebSocket connections and initiates voice pipeline
- `loan_application_form()`: Serves HTML form with pre-fill support
- `submit_loan_application()`: Processes form submissions

**Dependencies**:
- FastAPI
- Uvicorn
- Python-dotenv
- Loguru

**Configuration**:
- Port: 8000 (default, configurable)
- Static files: `/static` directory
- Templates: `/templates` directory

---

### 2. Voice Bot Pipeline (`bot.py`)

**Purpose**: Real-time voice processing pipeline using Pipecat framework

**Pipecat Documentation**: https://reference-server.pipecat.ai/en/latest/

**Key Responsibilities**:
- Audio stream processing
- Speech-to-text conversion
- AI conversation management
- Text-to-speech synthesis
- Conversation state tracking

**Pipeline Architecture**:
```
WebSocket Input → STT → Context Aggregator (User) → LLM → TTS → WebSocket Output
                                                                    ↓
                                              Context Aggregator (Assistant) ←
```

**Key Components**:
- **FastAPIWebsocketTransport**: WebSocket transport layer for Twilio
- **DeepgramSTTService**: Speech-to-text service
- **OpenAILLMService**: Language model for conversation
- **OpenAILLMContext**: Conversation context management
- **CartesiaTTSService**: Text-to-speech service
- **SileroVADAnalyzer**: Voice activity detection

**Configuration**:
- **STT Model**: `nova-2` (Deepgram)
- **STT Language**: `en-US` (English)
- **LLM Model**: `gpt-4.1-mini` (OpenAI)
- **TTS Voices**: Cartesia voice IDs configured via `CARTESIA_WELCOME_VOICE_ID` and `CARTESIA_LOAN_VOICE_ID`

**System Prompt**:
The LLM follows a structured workflow:
1. Opening: Greet and introduce service
2. Consent: Explain soft credit inquiry
3. Data Collection: Gather name, phone, zip code (in order)
4. Link Handoff: Send secure link after all data collected

**Event Handlers**:
- `on_client_connected`: Initiates conversation with opening message
- `on_client_disconnected`: Cleans up and ends pipeline

**Dependencies**:
- pipecat-ai (API Reference: https://reference-server.pipecat.ai/en/latest/)
- twilio
- openai
- deepgram

---

### 3. Loan Application Form (`templates/loan_application.html`)

**Purpose**: Web-based loan application form with pre-fill support

**Features**:
- Pre-fillable fields from URL parameters
- Client-side validation
- Responsive design
- Security messaging

**Form Sections**:
1. **Personal Information**:
   - Legal name (pre-fillable)
   - Date of birth
   - Email (pre-fillable)
   - Phone (pre-fillable)
   - SSN last 4 digits

2. **Loan Details**:
   - Monthly income
   - Requested loan amount
   - Purpose of loan (dropdown)

3. **Consent & Agreement**:
   - Terms and conditions checkbox

**Pre-fill Mechanism**:
- JavaScript reads URL query parameters
- Automatically populates matching form fields
- Parameters: `legal_name`, `email`, `phone`, `zip_code`

**Dependencies**:
- `/static/css/loan_application.css` - Styling
- `/static/js/loan_application.js` - Form handling

---

### 4. Form JavaScript (`static/js/loan_application.js`)

**Purpose**: Client-side form handling and pre-fill logic

**Key Functions**:
- `getUrlParameter(name)`: Extracts URL query parameters
- `prefillForm()`: Pre-fills form fields from URL parameters
- `initializeForm()`: Sets up form event handlers

**Form Submission**:
- Prevents default form submission
- Validates form data
- Sends POST request to `/loan-application`
- Handles success/error responses
- Shows success message on completion

**Error Handling**:
- Displays validation errors
- Shows user-friendly error messages
- Handles network errors gracefully

---

### 5. Form Styling (`static/css/loan_application.css`)

**Purpose**: Visual styling for loan application form

**Features**:
- Modern, clean design
- Responsive layout
- Form section organization
- Success message styling
- Security indicators

---

## Integration Components

### 6. Twilio Integration

**Purpose**: Phone call handling and audio streaming

**Services Used**:
- **Twilio Voice API**: Receives calls and streams audio
- **Twilio Media Streams**: Real-time audio streaming via WebSocket

**Configuration**:
- Account SID: `TWILIO_ACCOUNT_SID` environment variable
- Auth Token: `TWILIO_AUTH_TOKEN` environment variable
- Phone Number: Configured in Twilio console

**Webhook Setup**:
- Incoming call webhook: `POST /`
- Returns TwiML with WebSocket connection URL


---

### 7. Deepgram STT Integration

**Purpose**: Speech-to-text conversion for voice input

**Service**: Deepgram Speech Recognition API

**Configuration**:
- API Key: `DEEPGRAM_API_KEY` environment variable
- Model: `nova-2`
- Language: `en-US` (english only for now)

**Integration**: Via Pipecat `DeepgramSTTService`

**Processing**:
- Receives audio stream from WebSocket
- Converts to text in real-time
- Feeds transcription to LLM context

---

### 8. OpenAI LLM Integration

**Purpose**: Conversational AI for loan pre-approval assistant

**Service**: OpenAI GPT-4o API

**Configuration**:
- API Key: `OPENAI_API_KEY` environment variable
- Model: `gpt-4.1-mini`

**Integration**: Via Pipecat `OpenAILLMService`

**Conversation Management**:
- **Context**: Maintained via `OpenAILLMContext`
- **System Prompt**: Defines assistant behavior and workflow
- **Message History**: Tracks conversation for context

**Key Behaviors**:
- Professional and friendly tone
- Structured data collection
- Consent verification
- Link delivery confirmation

---

### 9. Cartesia TTS Integration

**Purpose**: Text-to-speech synthesis for voice responses (primary)

**Service**: Cartesia Sonic TTS (via Pipecat)

**Configuration**:
- API Key: `CARTESIA_API_KEY` environment variable
- Voices: `CARTESIA_WELCOME_VOICE_ID`, `CARTESIA_LOAN_VOICE_ID`

**Integration**: Via Pipecat `CartesiaTTSService`

**Processing**:
- Receives text from LLM
- Converts to natural-sounding speech with the configured voice via Cartesia streaming WebSocket
- Streams audio to WebSocket for Twilio

---

### 10. DecisionRules Integration (Planned)

**Purpose**: Business rules engine for loan eligibility evaluation

**Service**: DecisionRules API (https://api.decisionrules.io)

**Configuration**:
- Solver Key: `DECISIONRULES_SOLVER_KEY` environment variable
- Rule Alias: `loan-approval` (configurable)
- Host: `https://api.decisionrules.io`

**Integration Pattern**:
```python
from decisionrules import DecisionRules

solver = DecisionRules(
    solver_key=os.getenv("DECISIONRULES_SOLVER_KEY"),
    host="https://api.decisionrules.io"
)

result = await solver.solve(
    rule_alias="loan-approval",
    data={
        "credit_score": credit_score,
        "monthly_income": monthly_income,
        "requested_amount": requested_amount,
        "zip_code": zip_code,
        "ssn_last4": ssn_last4,
        "dob": dob
    },
    version="latest"
)
```

**Expected Output**:
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
  "requires_review": false
}
```

**Decision Rules**:
- Credit score thresholds
- Debt-to-income ratios
- Loan amount limits
- Geographic risk factors
- Regulatory compliance checks

---

### 11. Credit Score Service (Planned)

**Purpose**: Credit score retrieval and profile enrichment

**Current Implementation**: Dummy service (simulated)

**Future Integration Options**:
- Experian API
- Equifax API
- TransUnion API
- Credit Karma API
- Alternative credit scoring services

**Integration Pattern**:
```python
async def get_credit_score(ssn_last4, dob, name, zip_code):
    # Dummy implementation
    # In production, call actual credit bureau API
    return {
        "score": 720,
        "range": "good",
        "factors": ["payment_history", "credit_utilization"],
        "inquiry_type": "soft"
    }
```

**Data Enrichment**:
- Credit score
- Credit history length
- Payment history
- Credit utilization
- Recent inquiries
- Public records

---

### 12. Email Service (Planned)

**Purpose**: Secure application link delivery via email

**Service**: MailerSend
- **Documentation**: https://www.npmjs.com/package/mailersend
- **API**: https://api.mailersend.com/v1/email

**Integration Pattern** (Python):
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
        "to": [{"email": email, "name": name}],
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

**Email Content**:
- Personalized greeting
- Secure application link
- Expiration notice
- Security information

---

## Infrastructure Components

### 13. Docker Configuration (`Dockerfile`)

**Purpose**: Containerization for deployment

**Base Image**: Python 3.12

**Key Steps**:
- Install system dependencies
- Copy application files
- Install Python dependencies
- Expose port 8000
- Set entrypoint

---

### 14. Deployment Configurations

#### Cerebrium (`cerebrium.toml`)
- Serverless deployment configuration
- Auto-scaling settings
- Resource allocation
- Environment variables

#### ECS (`ecs-task-definition.json`)
- Container task definition
- Resource requirements
- Environment variables
- Network configuration

#### Terraform (`infrastructure/`)
- Infrastructure as Code
- AWS resource provisioning
- Load balancer configuration
- Auto-scaling groups

---

## Data Structures

### Application Data Structure

```python
{
    "personal_info": {
        "legal_name": str,
        "dob": str,  # YYYY-MM-DD
        "email": str,
        "phone": str,
        "zip_code": str,
        "ssn_last4": str
    },
    "financial": {
        "monthly_income": float,
        "credit_score": int,  # From credit service
        "debt_to_income_ratio": float
    },
    "loan_details": {
        "requested_amount": float,
        "purpose_of_loan": str,
        "provisional_amount": float,  # From DecisionRules
        "interest_rate_range": {
            "min": float,
            "max": float
        }
    },
    "consents": {
        "terms": bool,
        "credit_check": bool
    },
    "status": {
        "application_id": str,
        "status": str,  # "pending", "approved", "denied", "under_review"
        "requires_review": bool,
        "escalation_reason": str  # If escalated
    }
}
```

---

## Error Handling

### Component-Level Error Handling

1. **FastAPI**: HTTP exception handling
2. **Pipecat**: Pipeline error handlers
3. **WebSocket**: Connection error recovery
4. **Form**: Client-side and server-side validation

### Logging

- **Loguru**: Structured logging throughout
- **Log Levels**: DEBUG, INFO, WARNING, ERROR
- **Request Logging**: All API endpoints
- **Error Tracking**: Comprehensive error logging

---

## Testing Considerations

### Unit Tests
- Component isolation
- Mock external services
- Validation logic

### Integration Tests
- End-to-end workflows
- External service integration
- WebSocket connections

### Load Tests
- Concurrent call handling
- WebSocket connection limits
- API endpoint performance

