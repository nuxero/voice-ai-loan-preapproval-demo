# Architecture Overview

## System Architecture

Voice-enabled loan pre-approval system: FastAPI + Pipecat processes voice calls, collects applicant info, evaluates eligibility via DecisionRules.

## Architecture Flow

```
Twilio Call → FastAPI (POST /) → WebSocket (/ws) → Pipecat Pipeline
                                                          ↓
                                    STT (Deepgram) → LLM (OpenAI) → TTS (OpenAI)
                                                          ↓
                                    Data Collection → Email Link (MailerSend) → Form Submission
                                                          ↓
                                    Credit Check → DecisionRules → Result Display
```

## Components

### `main.py` - FastAPI Server
- `POST /` - Twilio webhook (returns TwiML with WebSocket URL)
- `WebSocket /ws` - Audio streaming endpoint
- `GET /loan-application` - Form serving
- `POST /loan-application` - Form submission

### `bot.py` - Voice Pipeline
- Pipecat pipeline: STT → LLM → TTS
- Conversation management and data extraction
- Real-time audio processing

### Frontend
- `templates/loan_application.html` - Form with pre-fill support
- `static/js/loan_application.js` - Form handling
- `static/css/loan_application.css` - Styling

## Data Flow

**Voice Call:**
1. Twilio webhook → TwiML response
2. WebSocket connection → Audio streaming
3. STT → LLM → TTS pipeline
4. Collect: name, phone, zip_code
5. Generate secure link → Send via MailerSend
6. User completes form

**Application Processing:**
1. Form submission → Validation
2. Credit check (dummy) → DecisionRules evaluation
3. Escalation check → Result display

## Technology Stack

- **FastAPI** - Web framework, WebSocket support
- **Pipecat** - Audio pipeline ([API Reference](https://reference-server.pipecat.ai/en/latest/))
- **Twilio** - Call webhooks, audio streaming
- **Deepgram** - Speech-to-Text
- **OpenAI GPT** - Conversational AI
- **OpenAI TTS** - Text-to-Speech
- **MailerSend** - Email delivery
- **DecisionRules** - Business rules engine ([Documentation](https://docs.decisionrules.io/doc))

## Deployment

- **Local**: `uvicorn main:app --host 0.0.0.0 --port 8000` (ngrok for webhooks)
- **Cerebrium**: Serverless with auto-scaling
- **ECS**: Containerized with Terraform

## Data Storage

- **In-memory storage only** - No database
- Application data stored in memory during request lifecycle
- Data lost on server restart or instance termination
- Stateless design - each request is independent

## Security & Operations

- Environment variables for API keys
- HTTPS/WSS required in production
- Input validation on all endpoints
- Stateless design for horizontal scaling
- Async processing for high concurrency
- Structured logging (Loguru)
