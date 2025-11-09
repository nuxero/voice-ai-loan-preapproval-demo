# Voice AI Loan Pre-Approval Demo

A Voice AI Twilio demo for automated loan pre-approval. This application captures basic applicant information over a phone call, simulates credit scoring, applies decision rules, and can escalate to a human for review.

## 📚 Documentation

For comprehensive architecture, API reference, and integration documentation, see the [`docs/`](./docs/) folder:
- [Architecture Overview](./docs/architecture.md)
- [API Reference](./docs/api-reference.md)
- [High-Level Flow](./docs/high-level-flow.md)
- [Components](./docs/components.md)
- [Integrations](./docs/integrations.md)
- [AI Context Guide](./docs/AI_CONTEXT.md) - Essential context for AI-assisted development tools

## Features

- **Real-time voice conversations** via WebSocket with Twilio
- **Automated loan pre-approval workflow**:
  - Collects applicant information (name, phone, zip code)
  - Explains soft credit inquiry (no impact on credit score)
  - Sends secure link to complete application
- **Web-based loan application form** with pre-filled data from voice call
- **Speech-to-Text** using Deepgram for accurate transcription
- **AI-powered conversation** with OpenAI GPT for natural dialogue
- **Text-to-Speech** using OpenAI TTS voices for natural dialogue
- **Dynamic WebSocket URL generation** for different deployment environments

## Architecture

- **FastAPI**: Web framework with WebSocket support and form handling
- **Pipecat**: Audio processing pipeline for real-time voice interactions
- **Twilio**: Phone call integration and media streaming
- **Deepgram**: Speech recognition for converting voice to text
- **OpenAI GPT-4.1-mini**: Language model for conversational loan pre-approval assistant
- **OpenAI TTS**: Text-to-speech synthesis for natural voice responses

## Workflow

### Voice Call Flow

1. **Opening**: AI greets caller and introduces the quick pre-approval service
2. **Consent Checkpoint**: Explains soft credit inquiry that doesn't impact credit score
3. **Data Collection**: Gathers:
   - Full name (legal name)
   - Mobile number (to send secure link)
   - Zip code
4. **Link Handoff**: Sends secure link to complete application and offers to stay on the line

## Prerequisites

- Python 3.12+
- API keys for:
  - OpenAI (gpt-4.1-mini + Text-to-Speech)
  - Deepgram (Speech-to-Text)
  - Twilio Account SID and Auth Token
- **For local development with Twilio**: ngrok or similar tunneling service (to expose your local server to receive webhook requests)

## Local Development

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

   Required environment variables:
   - `OPENAI_API_KEY`
   - `DEEPGRAM_API_KEY`
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `WEBSOCKET_URL` (optional, auto-generated if not set)

3. **Run the application**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

4. **Set up tunneling for Twilio webhooks** (required for testing with phone calls):
   
   Twilio needs a publicly accessible URL to send webhook requests to your local server. Use a tunneling service like ngrok:
   
   ```bash
   # Install ngrok (if not already installed)
   # Visit https://ngrok.com/download or use: brew install ngrok / snap install ngrok
   
   # Start ngrok tunnel to your local server
   ngrok http 8000
   ```
   
   Copy the HTTPS URL from ngrok (e.g., `https://abc123.ngrok.io`) and configure it in your Twilio console:
   - Go to your Twilio Phone Number settings
   - Set the webhook URL for incoming calls to: `https://your-ngrok-url.ngrok.io/`
   
   **Note**: For WebSocket support, ensure ngrok is configured for WebSocket connections (ngrok's free tier supports this by default when using `http` protocol).

## Deployment

### Cerebrium Deployment

1. **Install Cerebrium CLI**:
   ```bash
   pip install cerebrium
   ```

2. **Configure secrets in Cerebrium dashboard**:
   - `OPENAI_API_KEY`
   - `DEEPGRAM_API_KEY`
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `WEBSOCKET_URL` (optional)

3. **Deploy**:
   ```bash
   cerebrium deploy
   ```

### Amazon ECS Deployment

1. **Configure AWS credentials**:
   ```bash
   aws configure
   ```

2. **Deploy infrastructure**:
   ```bash
   cd infrastructure
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your API keys
   ./deploy-infra.sh
   ```

3. **Deploy application**:
   ```bash
   cd ..
   ./deploy.sh
   ```

4. **Application URL**:
   The application URL will be displayed at the end of the deployment process.
   Use the ALB DNS name for accessing the application.

## API Endpoints

- `POST /` - Returns TwiML with WebSocket URL for Twilio voice calls
- `WebSocket /ws` - Real-time audio streaming endpoint for voice conversations
- `GET /loan-application` - Serves the loan application form (supports query parameters: `legal_name`, `email`, `phone`, `zip_code` for pre-filling)
- `POST /loan-application` - Handles loan application form submission, evaluates the application via DecisionRules, and emails the applicant with an approval or denial notification

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for GPT-4o |
| `DEEPGRAM_API_KEY` | Deepgram API key for speech recognition |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token |
| `MAILERSEND_API_KEY` | MailerSend API key for decision notification emails |
| `MAILERSEND_FROM_EMAIL` | Sender email address for MailerSend (defaults to `loans@yourcompany.com`) |
| `DECISION_RULES_API_KEY` | DecisionRules solver/API key used to call the rules engine |
| `DECISION_RULES_RULE_ID` | DecisionRules rule ID to evaluate loan applications |
| `DECISION_RULES_HOST` | (Optional) DecisionRules API host, defaults to `https://api.decisionrules.io` |
| `CREDIT_SCORE_API_URL` | (Optional) Mock credit bureau endpoint used for logging credit score lookups |
| `WEBSOCKET_URL` | (Optional) WebSocket URL for Twilio connections. If not set, auto-generated from request headers |
| `COMPANY_NAME` | (Optional) Overrides the default company branding used in prompts |

> **Note:** The application also accepts the legacy environment variable names (`DECISIONRULES_SOLVER_KEY`, `DECISIONRULES_RULE_ID`, etc.) for backward compatibility.

## How It Works

1. External service (Twilio) makes POST request to `/`
2. Application returns TwiML with dynamically generated WebSocket URL
3. WebSocket connection established at `/ws`
4. Audio pipeline processes:
   - Incoming audio → Speech-to-Text
   - Text → AI processing
   - AI response → Text-to-Speech
   - Audio response sent back

## Cleanup

### Cerebrium
```bash
cerebrium delete cerebrium-demo
```

### Amazon ECS
```bash
cd infrastructure
tofu destroy
```

## License

MIT License