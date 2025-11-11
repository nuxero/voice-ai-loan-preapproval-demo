# API Reference

Complete API endpoint documentation for the Voice AI Loan Pre-Approval Demo.

## Base URL

The base URL varies by deployment:
- **Local**: `http://localhost:8000`
- **Cerebrium**: `https://your-deployment.cerebrium.ai`
- **ECS**: `https://your-alb-dns-name.elb.amazonaws.com`

## Authentication

Currently, the API does not require authentication. In production, consider implementing:
- API key authentication
- OAuth 2.0
- JWT tokens

## Endpoints

### 1. Twilio Webhook Endpoint

**Endpoint**: `POST /`

**Description**: Handles incoming Twilio webhook requests for voice calls. Returns TwiML that connects the call to the WebSocket endpoint.

**Request Headers**:
```
Content-Type: application/x-www-form-urlencoded
```

**Request Body** (from Twilio):
```
CallSid: CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
From: +1234567890
To: +1987654321
CallStatus: ringing
...
```

**Response**:
- **Content-Type**: `application/xml`
- **Status**: `200 OK`

**Response Body** (TwiML):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://your-domain.com/ws"></Stream>
  </Connect>
  <Pause length="40"/>
</Response>
```

**WebSocket URL Generation**:
- Uses `WEBSOCKET_URL` environment variable if set
- Otherwise constructs from request headers:
  - Scheme: `wss` if HTTPS, `ws` if HTTP
  - Host: From `Host` header or `x-forwarded-host`
  - Path: `/ws`

**Example**:
```bash
curl -X POST https://your-domain.com/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "CallSid=CA123&From=%2B1234567890&To=%2B1987654321"
```

**Implementation**: `main.py::start_call()`

---

### 2. WebSocket Endpoint

**Endpoint**: `WebSocket /ws`

**Description**: Establishes WebSocket connection for real-time bidirectional audio streaming between Twilio and the application.

**Connection Process**:
1. Client connects to `/ws`
2. Server accepts connection
3. Client sends initial text message with stream metadata
4. Server parses stream SID
5. Audio pipeline starts processing

**WebSocket Protocol**:
- **Protocol**: Twilio Media Stream Protocol
- **Format**: JSON for metadata, binary for audio
- **Direction**: Bidirectional

**Initial Message** (from Twilio):
```json
{
  "event": "start",
  "start": {
    "streamSid": "MZxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "accountSid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "callSid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "tracks": {
      "inbound": {},
      "outbound": {}
    },
    "mediaFormat": {
      "encoding": "audio/x-mulaw",
      "sampleRate": 8000
    }
  }
}
```

**Audio Format**:
- **Encoding**: μ-law (PCMU) or linear PCM
- **Sample Rate**: 8000 Hz (telephony standard)
- **Channels**: Mono

**Pipeline Flow**:
```
WebSocket Input → STT (Deepgram) → LLM (OpenAI) → TTS (OpenAI) → WebSocket Output
```

**Event Handlers**:
- `on_client_connected`: Initiates conversation
- `on_client_disconnected`: Cleans up resources

**Implementation**: `main.py::websocket_endpoint()`, `bot.py::main()`

---

### 3. Loan Application Form (GET)

**Endpoint**: `GET /loan-application`

**Description**: Serves the loan application HTML form with optional pre-fill parameters from URL query string.

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `legal_name` | string | No | Pre-fills the legal name field |
| `email` | string | No | Pre-fills the email field |
| `phone` | string | No | Pre-fills the phone field |
| `zip_code` | string | No | Pre-fills the zip code field |

**Response**:
- **Content-Type**: `text/html`
- **Status**: `200 OK`

**Example Request**:
```bash
curl "https://your-domain.com/loan-application?legal_name=John%20Doe&email=john@example.com&phone=5551234567"
```

**Example Response**:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Loan Application - Secure Pre-Approval</title>
    ...
</head>
<body>
    <!-- Form with pre-filled values -->
</body>
</html>
```

**Pre-fill Mechanism**:
- JavaScript reads URL parameters on page load
- Fields are automatically populated
- Works with URL-encoded parameters

**Implementation**: `main.py::loan_application_form()`

---

### 4. Loan Application Submission (POST)

**Endpoint**: `POST /loan-application`

**Description**: Handles loan application form submission, validates data, and processes the application.

**Request Headers**:
```
Content-Type: application/x-www-form-urlencoded
```

**Request Body** (Form Data):
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `legal_name` | string | Yes | Applicant's legal name |
| `dob` | string (YYYY-MM-DD) | Yes | Date of birth |
| `email` | string | Yes | Email address |
| `phone` | string | Yes | Phone number |
| `ssn_last4` | string (4 digits) | Yes | Last 4 digits of SSN |
| `monthly_income` | float | Yes | Monthly income amount |
| `requested_amount` | float | Yes | Requested loan amount |
| `purpose_of_loan` | string | Yes | Purpose of loan (enum) |
| `terms_consent` | string | No | Terms consent checkbox |

**Purpose of Loan Options**:
- `debt_consolidation`
- `home_improvement`
- `major_purchase`
- `business`
- `medical`
- `education`
- `vacation`
- `other`

**Request Example**:
```bash
curl -X POST https://your-domain.com/loan-application \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "legal_name=John+Doe&dob=1990-01-15&email=john@example.com&phone=5551234567&ssn_last4=1234&monthly_income=5000&requested_amount=10000&purpose_of_loan=debt_consolidation&terms_consent=on"
```

**Success Response**:
- **Status**: `200 OK`
- **Content-Type**: `application/json`

```json
{
  "success": true,
  "message": "Application submitted successfully",
  "application_id": "APP-123456"
}
```

**Error Response**:
- **Status**: `400 Bad Request`
- **Content-Type**: `application/json`

```json
{
  "success": false,
  "detail": "Validation error message"
}
```

**Application Data Structure**:
```json
{
  "personal_info": {
    "legal_name": "John Doe",
    "dob": "1990-01-15",
    "email": "john@example.com",
    "phone": "5551234567",
    "ssn_last4": "1234"
  },
  "financial": {
    "monthly_income": 5000.0
  },
  "loan_details": {
    "requested_amount": 10000.0,
    "purpose_of_loan": "debt_consolidation"
  },
  "consents": {
    "terms": true
  }
}
```

**Post-Submission Processing**:
1. Application data stored in memory
2. Run credit check (dummy)
3. Send confirmation email (if implemented)
4. Trigger approval process via DecisionRules
5. Return result to user

**Note**: This system uses in-memory storage only. Data is not persisted to a database.

**Implementation**: `main.py::submit_loan_application()`

---

## WebSocket Message Format

### Incoming Audio Messages

**Format**: Binary audio data (μ-law PCM)

**Frequency**: Continuous stream during call

**Processing**: 
- Received by WebSocket transport
- Converted by Deepgram STT service
- Transcribed to text
- Fed to LLM for processing

### Outgoing Audio Messages

**Format**: Binary audio data (PCM)

**Generation**:
- LLM generates text response
- Cartesia TTS converts to speech
- Audio sent via WebSocket to Twilio

---

## Error Responses

All endpoints follow standard HTTP status codes:

| Status Code | Description |
|-------------|-------------|
| `200` | Success |
| `400` | Bad Request (validation errors) |
| `404` | Not Found |
| `500` | Internal Server Error |
| `503` | Service Unavailable |

**Error Response Format**:
```json
{
  "success": false,
  "detail": "Error message description"
}
```

---

## Rate Limiting

Currently, no rate limiting is implemented. In production, consider:
- Per-IP rate limiting
- Per-API-key rate limiting
- WebSocket connection limits

---

## CORS Configuration

Current CORS configuration (development):
- **Allow Origins**: `*` (all origins)
- **Allow Credentials**: `true`
- **Allow Methods**: `*` (all methods)
- **Allow Headers**: `*` (all headers)

**Production Recommendation**: Restrict to specific origins.

**Implementation**: `main.py` CORS middleware

---

## Environment Variables

Required environment variables for API functionality:

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for GPT-4o | Yes |
| `DEEPGRAM_API_KEY` | Deepgram API key for STT | Yes |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | Yes |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | Yes |
| `WEBSOCKET_URL` | WebSocket URL override | No |

---

## Static Files

### CSS
- **Path**: `/static/css/loan_application.css`
- **Description**: Styling for loan application form

### JavaScript
- **Path**: `/static/js/loan_application.js`
- **Description**: Form handling and URL parameter parsing

### Mount Point
- **Path**: `/static/*`
- **Implementation**: FastAPI StaticFiles mount

---

## Future API Endpoints (Planned)

### Credit Score Check
- `POST /api/credit-check`
- Trigger credit score pull

### DecisionRules Evaluation
- `POST /api/evaluate`
- Submit application for rules evaluation

### Application Status
- `GET /api/application/{application_id}`
- Check application status

### Escalation
- `POST /api/escalate`
- Request human review

