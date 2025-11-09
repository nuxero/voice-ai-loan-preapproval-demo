# High-Level Flow Documentation

This document describes the complete end-to-end flow of the Voice AI Loan Pre-Approval Demo system.

## Overview

The system enables customers to apply for loan pre-approval via voice call, with automated processing, eligibility evaluation, and secure application completion.

## Complete Flow Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                    HIGH-LEVEL APPLICATION FLOW                     │
└───────────────────────────────────────────────────────────────────┘

1. INBOUND CALL
   │
   │ Customer calls "Loan Pre-Approval" number (Twilio)
   │
   ▼
2. VOICE AGENT GREETING
   │
   │ Pipecat + STT/LLM/TTS services
   │ - Greets caller
   │ - Introduces service
   │ - Asks for consent to proceed
   │
   ▼
3. CONSENT VERIFICATION
   │
   │ - Explains soft credit inquiry (no impact on credit score)
   │ - Gets explicit consent
   │ - Proceeds only if consent given
   │
   ▼
4. DATA COLLECTION
   │
   │ Collects in order:
   │ 1. Full name (legal name)
   │ 2. Mobile number (for secure link)
   │ 3. Zip code
   │
   │ LLM extracts and validates information
   │
   ▼
5. SECURE LINK GENERATION
   │
   │ System generates secure application link with:
   │ - Pre-filled parameters (name, phone, zip_code)
   │ - Secure token/session identifier
   │
   ▼
6. EMAIL DELIVERY
   │
   │ Agent sends secure link via:
   │ - Email (MailerSend)
   │
   │ Agent offers to stay on line for assistance
   │
   ▼
7. APPLICATION FORM ACCESS
   │
   │ User clicks link → Opens loan application form
   │ Form pre-filled with:
   │ - legal_name
   │ - phone
   │ - zip_code
   │
   ▼
8. FORM COMPLETION
   │
   │ User completes additional fields:
   │ - Date of birth
   │ - Email
   │ - SSN last 4 digits
   │ - Monthly income
   │ - Requested loan amount
   │ - Purpose of loan
   │ - Terms consent
   │
   ▼
9. FORM SUBMISSION
   │
   │ POST /loan-application
   │ - Validates all fields
   │ - Structures application data
   │
   ▼
10. CREDIT SCORE PULL
    │
    │ Backend runs dummy credit score pull
    │ - Simulates credit check (no actual credit bureau call)
    │ - Returns credit score estimate
    │
    ▼
11. PROFILE ENRICHMENT
    │
    │ System enriches profile with:
    │ - Credit score data
    │ - Additional demographic data
    │ - Risk indicators
    │
    ▼
12. DECISIONRULES EVALUATION
    │
    │ DecisionRules engine evaluates:
    │ - Eligibility criteria
    │ - Loan amount limits
    │ - Interest rate ranges
    │ - Risk assessment
    │
    │ Returns:
    │ - Approved/Denied status
    │ - Provisional loan amount
    │ - Interest rate range
    │ - Terms and conditions
    │
    ▼
13. ESCALATION CHECK
    │
    │ System checks if:
    │ - Edge case detected
    │ - High exposure risk
    │ - Requires human review
    │
    │ If escalation needed:
    │ └─▶ Transfer to human agent (same call or callback)
    │
    │ If auto-approved:
    │ └─▶ Continue to result screen
    │
    ▼
14. RESULT SCREEN
    │
    │ Applicant sees:
    │ - Estimated loan amount (if approved)
    │ - Interest rate range
    │ - Next steps
    │ - Application reference number
    │
    ▼
15. COMPLETION
    │
    │ - Application data in memory (not persisted)
    │ - Confirmation sent
    │ - Follow-up scheduled (if needed)
```

## Detailed Flow Steps

### Step 1: Inbound Call (Twilio)

**Trigger**: Customer dials configured Twilio phone number

**Process**:
- Twilio receives call
- Twilio sends POST request to `/` webhook endpoint
- FastAPI generates TwiML response with WebSocket URL
- Twilio establishes WebSocket connection to `/ws`

**Key Components**:
- `main.py::start_call()` - Webhook handler
- Twilio Voice API
- WebSocket URL generation

---

### Step 2-4: Voice Agent Interaction (Pipecat Pipeline)

**Process**:
1. **Greeting**: AI introduces service and asks if caller wants to proceed
2. **Consent**: Explains soft credit inquiry and gets consent
3. **Data Collection**: Systematically collects:
   - Full legal name
   - Mobile phone number
   - Zip code

**Key Components**:
- `bot.py::main()` - Pipeline initialization
- Deepgram STT - Speech-to-text conversion
- OpenAI GPT - Conversation management
- OpenAI TTS - Text-to-speech synthesis
- Silero VAD - Voice activity detection

**LLM System Prompt**:
The AI follows a structured workflow to collect information in the correct order, ensuring all required data is gathered before proceeding.

---

### Step 5-6: Secure Link Generation and Delivery

**Process**:
1. System generates secure application URL:
   ```
   https://your-domain.com/loan-application?legal_name={name}&phone={phone}&zip_code={zip}
   ```
2. Link sent via Email (MailerSend)
3. AI confirms link delivery and offers assistance

**Key Components**:
- MailerSend API (for email delivery)
- URL generation with secure parameters

**Implementation Notes**:
- Email delivery uses MailerSend API
- Links include pre-filled query parameters for form population

---

### Step 7-8: Application Form Access and Completion

**Process**:
1. User clicks secure link
2. Form loads with pre-filled data from URL parameters
3. User completes remaining fields
4. Form validation occurs client-side and server-side

**Key Components**:
- `main.py::loan_application_form()` - Form serving endpoint
- `templates/loan_application.html` - Form template
- `static/js/loan_application.js` - Form handling logic
- `static/css/loan_application.css` - Styling

**Form Fields**:
- **Pre-filled**: legal_name, phone, zip_code
- **User-entered**: dob, email, ssn_last4, monthly_income, requested_amount, purpose_of_loan, terms_consent

---

### Step 9: Form Submission

**Process**:
1. User submits form via POST request
2. Backend validates all fields
3. Application data structured and logged
4. Processing begins

**Key Components**:
- `main.py::submit_loan_application()` - Submission handler
- Data validation and structuring
- Application ID generation

---

### Step 10-11: Credit Score Pull and Profile Enrichment

**Process**:
1. Backend calls credit score service (dummy implementation)
2. Credit score retrieved and stored
3. Profile enriched with additional data points
4. Risk indicators calculated

**Key Components**:
- Credit score service integration (currently dummy)
- Profile enrichment logic
- Risk assessment calculations

**Implementation Notes**:
- Currently uses dummy credit score service
- In production, integrate with actual credit bureau APIs
- Enrichment may include demographic data, financial history, etc.

---

### Step 12: DecisionRules Evaluation

**Process**:
1. Application data prepared for DecisionRules
2. API call to DecisionRules engine
3. Rules evaluated against applicant profile
4. Decision returned with:
   - Approval status
   - Provisional loan amount
   - Interest rate
   - Terms

**Key Components**:
- DecisionRules API integration
- Business rules configuration
- Decision processing logic

**DecisionRules API**:
- Endpoint: `https://api.decisionrules.io`
- Solver key required
- Rule alias for loan evaluation
- Input: Applicant data structure
- Output: Decision result with loan terms

**Example DecisionRules Call**:
```python
from decisionrules import DecisionRules

solver = DecisionRules(solver_key="your-key")
result = solver.solve(
    rule_alias="loan-approval",
    data={
        "credit_score": 720,
        "monthly_income": 5000,
        "requested_amount": 10000,
        "zip_code": "90210"
    },
    version="latest"
)
```

---

### Step 13: Escalation Check

**Process**:
1. System evaluates DecisionRules output
2. Checks for edge cases:
   - Credit score in borderline range
   - High loan amount relative to income
   - Unusual patterns
   - Regulatory flags
3. If escalation needed:
   - Transfer to human agent
   - Can be same-call transfer or callback
4. If auto-approved:
   - Continue to result screen

**Key Components**:
- Escalation logic
- Human agent transfer mechanism
- Edge case detection

**Escalation Triggers**:
- Credit score below threshold
- Loan amount exceeds income ratio limits
- Unusual application patterns
- Regulatory compliance flags
- Manual review required by business rules

---

### Step 14-15: Result Screen and Completion

**Process**:
1. Result screen displays:
   - Approval status (Approved/Denied/Under Review)
   - Provisional loan amount (if approved)
   - Interest rate range
   - Next steps
   - Application reference number
2. Application data stored in memory (not persisted)
3. Confirmation email sent (if implemented)
4. Follow-up scheduled if needed

**Key Components**:
- Result screen rendering
- In-memory data storage
- Notification system
- Follow-up scheduling

**Note**: Data is stored in memory only and is lost on server restart.

---

## Edge Cases and Error Handling

### Voice Call Interruptions
- If call drops, system can resume with callback
- Partial data collected is stored in memory (not persisted)

### Form Submission Errors
- Validation errors displayed clearly
- Retry mechanism for failed submissions

### Service Failures
- Credit score service failure → Use default scoring
- DecisionRules failure → Escalate to human review
- Email failure → Retry with exponential backoff

### Human Escalation
- Can occur at any point in the flow
- Same-call transfer or scheduled callback
- All collected data preserved for agent review

---

## Integration Points

1. **Twilio** → Voice calls (webhooks and audio streaming)
2. **Deepgram** → Speech-to-text
3. **OpenAI** → Conversation AI
4. **OpenAI TTS** → Text-to-speech
5. **DecisionRules** → Business rules evaluation
6. **MailerSend** → Email delivery for application links
7. **Credit Score Service** → Credit check (dummy)

---

## Security and Privacy

- **Consent**: Explicit consent obtained before credit check
- **Soft Inquiry**: No impact on credit score
- **Secure Links**: Tokens and encrypted parameters
- **Data Protection**: PII handling per compliance requirements
- **Secure Transmission**: HTTPS/WSS for all communications

