import os
import sys
import urllib.parse
import re
import asyncio

from loguru import logger
from pipecat.frames.frames import LLMMessagesFrame, EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

from pipecat.services.openai.llm import OpenAILLMService
from pipecat.processors.aggregators.openai_llm_context import (
    OpenAILLMContext,
)
from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
from pipecat.audio.vad.silero import SileroVADAnalyzer
from twilio.rest import Client
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer

from pipecat.services.openai.tts import OpenAITTSService
from email_service import get_email_service

DEFAULT_COMPANY_NAME = "companyABC"
WELCOME_AGENT_NAME = "Eliza"
LOAN_AGENT_NAME = "Blake"
WELCOME_VOICE = "nova"
LOAN_VOICE = "alloy"

def build_welcome_system_prompt(company_name: str) -> str:
    return f"""
You are {WELCOME_AGENT_NAME}, the concise welcome concierge for {company_name}. Keep responses under two sentences.

What to do:
- Greet the caller and state that you can answer quick FAQs about the pre-approval program or route them to our loan specialist.
- Never mention the name of the loan specialist, {LOAN_AGENT_NAME}, in your responses unless the caller indicates they want to begin the loan application pre-approval.
- Answer only lightweight questions about hours, eligibility basics, or how pre-approval works. If unsure, say you'll connect them to the specialist.
- Do NOT collect personal data or start the application yourself.
- When the caller indicates they want to begin pre-approval immediately respond once with a short confirmation: "Connecting you to Blake, our loan specialist, now. Please hold." Do not ask for permission or follow-up questions—just acknowledge and let the system transfer.
- Respond in the same language the caller uses. If you need to switch languages, ask for permission first.
""".strip()


def build_loan_system_prompt(company_name: str) -> str:
    return f"""
You are {LOAN_AGENT_NAME}, the automated loan specialist for {company_name}. The caller has already spoken with {WELCOME_AGENT_NAME} and is ready to begin the pre-approval workflow.

Follow this structure:
1. Opening: Re-introduce yourself as {LOAN_AGENT_NAME} and confirm the caller is ready to proceed.
2. Information: Explain that you will perform a soft credit inquiry with no impact on their credit score.
3. Collect the following in order, one item at a time. Do not move on until you confirm the previous answer:
   - Full legal name
   - Email address (for the secure application link)
   - Zip code
4. Link handoff: AFTER all three items are collected, confirm the secure link is being sent and offer to stay on the line.

Human agent option:
- If the caller asks for a person, acknowledge and say: "I'll connect you with one of our agents right away." Then the system will handle the transfer. Do not continue the conversation afterward.
- Introduce yourself only once after the handoff. After that, proceed with the workflow unless the caller specifically asks for a reminder.
- Keep answers focused and professional. Respond in the same language as the caller. Default to English unless the caller begins speaking in another language or explicitly requests a change.
- Do not switch languages without explicit confirmation from the caller.
- Respond with a single concise message per turn.
""".strip()

START_APPLICATION_PATTERNS = [
    r"\bstart\s+(?:the\s+)?application\b",
    r"\bready\s+to\s+apply\b",
    r"\bready\s+to\s+continue\b",
    r"\bmove\s+forward\b",
    r"\bproceed\s+with\s+(?:the\s+)?pre[-\s]?approval\b",
    r"(?:talk|speak)\s+to\s+(?:the\s+)?loan\s+specialist",
    r"(?:connect|transfer)\s+(?:me\s+)?(?:to\s+)?(?:the\s+)?loan\s+specialist",
    r"(?:apply|application)\s+for\s+(?:a\s+)?loan",
]
EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ZIP_REGEX = re.compile(r"\b\d{5}\b")
AFFIRMATIVE_PATTERN = re.compile(
    r"^\s*(yes|yeah|yep|correct|that's right|affirmative|exactly|sure|right)\b",
    re.IGNORECASE,
)
ASSISTANT_HUMAN_ACK_PATTERN = re.compile(
    r"(?:i[' ]?ll|i will|let me)\s+(?:connect|transfer|put)\s+(?:you\s+)?(?:with|to|through)\s+(?:one\s+of\s+)?(?:our\s+)?(?:live\s+)?(?:human|person|people|agent|representative|team\s+member)s?",
    re.IGNORECASE,
)
ZIP_WORD_MAP = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}

def _normalize_email_text(text: str) -> str:
    normalized = text.lower()
    
    combined_replacements = [
        (r"\bdotcom\b", ".com"),
        (r"\bdotnet\b", ".net"),
        (r"\bdotorg\b", ".org"),
        (r"\bdotgov\b", ".gov"),
        (r"\bdotco\b", ".co"),
    ]
    for pattern, repl in combined_replacements:
        normalized = re.sub(pattern, repl, normalized)
    
    word_replacements = [
        (r"\b(?:at|arroba)\b", "@"),
        (r"\b(?:dot|period)\b", "."),
        (r"\bunderscore\b", "_"),
        (r"\b(?:dash|hyphen|minus)\b", "-"),
        (r"\bplus\b", "+"),
        (r"\bagilityfeet\b", "agilityfeat"),
        (r"\bagilityfit\b", "agilityfeat"),
    ]
    for pattern, repl in word_replacements:
        normalized = re.sub(pattern, repl, normalized)
    
    return normalized


def extract_email_from_text(text):
    if not text:
        return None
    
    normalized = _normalize_email_text(text)
    
    match_normalized = EMAIL_REGEX.search(normalized)
    if match_normalized:
        return match_normalized.group(0)
    
    compact = re.sub(r"\s+", "", normalized)
    match_compact = EMAIL_REGEX.search(compact)
    if match_compact:
        return match_compact.group(0)
    
    return None


def extract_zip_from_text(text):
    if not text:
        return None
    
    direct_match = ZIP_REGEX.search(text)
    if direct_match:
        return direct_match.group(0)
    
    tokens = re.findall(
        r"\b(?:\d+|zero|oh|o|one|two|three|four|five|six|seven|eight|nine)\b",
        text.lower(),
    )
    if not tokens:
        return None
    
    digits = ""
    for token in tokens:
        if token.isdigit():
            digits += token
        elif token in ZIP_WORD_MAP:
            digits += ZIP_WORD_MAP[token]
        if len(digits) >= 5:
            break
    
    return digits[:5] if len(digits) >= 5 else None

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

twilio = Client(
    os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
)

def forward_call_to_agent(call_sid, support_phone_number):
    """Forward a Twilio call to a human agent using TwiML Dial verb"""
    if not call_sid:
        logger.error("Cannot forward call: call_sid is missing")
        return False
    
    if not support_phone_number:
        logger.error("Cannot forward call: SUPPORT_PHONE_NUMBER is not configured")
        return False
    
    try:
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting you to one of our agents now. Please hold.</Say>
    <Dial>{support_phone_number}</Dial>
</Response>"""
        
        call = twilio.calls(call_sid).update(twiml=twiml)
        logger.info(f"Call {call_sid} forwarded to {support_phone_number}")
        return True
    except Exception as e:
        logger.error(f"Error forwarding call {call_sid} to {support_phone_number}: {e}")
        return False

async def main(websocket_client, stream_sid, call_sid=None, company_name=None):
    company_name = company_name or os.getenv("COMPANY_NAME") or DEFAULT_COMPANY_NAME
    welcome_system_prompt = build_welcome_system_prompt(company_name)
    loan_system_prompt = build_loan_system_prompt(company_name)

    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
            serializer=TwilioFrameSerializer(stream_sid),
        ),
    )
    
    deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    
    email_service = get_email_service()

    stt = DeepgramSTTService(
        api_key=deepgram_api_key,
        live_options=LiveOptions(
            model="nova-2",
            language="en-US",
            keywords=["agilityfeat", "google", "microsoft", "aws"],
        ),
    )

    llm = OpenAILLMService(
        name="LLM",
        api_key=openai_api_key,
        model="gpt-4.1-mini",
    )
    

    tts = OpenAITTSService(
        api_key=openai_api_key,
        voice=WELCOME_VOICE,
    )

    messages = [
        {
            "role": "system",
            "content": welcome_system_prompt,
        }
    ]
    print("here", flush=True)
    context = OpenAILLMContext(messages=messages)
    context_aggregator = llm.create_context_aggregator(context)
    
    current_agent = "welcome"
    
    # Store collected data
    collected_data = {"name": None, "email": None, "zip_code": None}
    
    # Monitor messages and send email when all data is collected
    email_sent_flag = False
    loan_flow_stage = None
    nudged_stages = set()
    pending_email_candidate = None
    loan_intro_noted = False
    last_invalid_email_attempt = None
    
    # Track if call has been forwarded to human agent
    call_forwarded_flag = False
    support_phone_number = os.getenv("SUPPORT_PHONE_NUMBER")
    
    async def check_and_send_email():
        nonlocal email_sent_flag, loan_flow_stage
        if email_sent_flag:
            return
        
        if collected_data["name"] and collected_data["email"] and collected_data["zip_code"]:
            logger.info(f"All data collected! Name: {collected_data['name']}, Email: {collected_data['email']}, Zip: {collected_data['zip_code']}")
            link = f"{base_url}/loan-application?legal_name={urllib.parse.quote(collected_data['name'])}&email={urllib.parse.quote(collected_data['email'])}&zip_code={urllib.parse.quote(collected_data['zip_code'])}"
            success = await email_service.send_application_link(
                collected_data["email"], 
                collected_data["name"], 
                link
            )
            logger.info(f"Email sent to {collected_data['email']} for {collected_data['name']}, zip {collected_data['zip_code']}, Success: {success}")
            email_sent_flag = True
            loan_flow_stage = "completed"

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            context_aggregator.user(),
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            context_aggregator.assistant(),
        ]
    )
    
    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))
    
    def set_tts_voice(voice_name: str):
        if not voice_name:
            return
        try:
            if hasattr(tts, "set_voice"):
                tts.set_voice(voice_name)
            else:
                tts.voice = voice_name  # type: ignore[attr-defined]
        except Exception:
            logger.warning("Unable to set TTS voice dynamically")

    set_tts_voice(WELCOME_VOICE)

    NUDGE_MESSAGES = {
        "awaiting_name": "Reminder: Confirm the caller's full legal name before proceeding.",
        "awaiting_email": "Reminder: Confirm the caller's email address so you can send the secure application link.",
        "awaiting_zip": "Reminder: Ask the caller for their current zip code before moving on.",
        "ready_to_send": "All details collected. Confirm you're sending the secure application link and offer to stay on the line.",
    }

    async def nudge_stage(stage: str):
        nonlocal nudged_stages
        if stage in nudged_stages:
            return
        reminder = NUDGE_MESSAGES.get(stage)
        if not reminder:
            return
        nudged_stages.add(stage)
        logger.debug(f"Nudge stage triggered for {stage}: {reminder}")

    def is_valid_email_address(value: str) -> bool:
        if not value or len(value) > 254:
            return False
        if not EMAIL_REGEX.fullmatch(value):
            return False
        local, _, domain = value.partition("@")
        if not local or not domain:
            return False
        if len(local) > 64 or "." not in domain:
            return False
        return True

    def sync_context():
        try:
            context.set_messages(messages)
        except AttributeError:
            # Some versions of OpenAILLMContext may not expose set_messages;
            # in that case we rely on in-place list mutation of `messages`.
            pass
    
    async def switch_to_loan_agent():
        nonlocal current_agent, collected_data, email_sent_flag, loan_flow_stage, last_invalid_email_attempt, pending_email_candidate, loan_intro_noted
        if current_agent == "loan":
            return
        
        logger.info("Switching from welcome agent to loan specialist agent")
        current_agent = "loan"
        collected_data = {"name": None, "email": None, "zip_code": None}
        email_sent_flag = False
        loan_flow_stage = "awaiting_name"
        last_invalid_email_attempt = None
        pending_email_candidate = None
        loan_intro_noted = False
        set_tts_voice(LOAN_VOICE)
        
        messages[:] = [
            {
                "role": "system",
                "content": loan_system_prompt,
            }
        ]
        sync_context()

        kickoff_prompt = (
            "The caller has just been transferred to you from the welcome concierge and is ready to begin. "
            "Immediately respond with one concise message that (1) confirms this is a soft credit inquiry with no impact on their score, "
            "and (2) asks for their full legal name. Do not wait for additional user input before answering."
        )
        messages.append({"role": "system", "content": kickoff_prompt})
        sync_context()
        await task.queue_frames([LLMMessagesFrame(list(messages))])
        messages.pop()
        sync_context()
        await nudge_stage("awaiting_name")
        if not loan_intro_noted:
            messages.append(
                {
                    "role": "system",
                    "content": "Note: You have already introduced yourself. Continue with consent and data collection without repeating the introduction unless the caller asks.",
                }
            )
            sync_context()
            loan_intro_noted = True
    
    # Background task to check for collected data and human agent requests
    async def monitor_messages():
        nonlocal call_forwarded_flag, current_agent, loan_flow_stage, last_invalid_email_attempt, pending_email_candidate
        logger.info("Email monitor task started")
        while True:
            try:
                await asyncio.sleep(2)
                aggregated_messages = context.get_messages()
                if not aggregated_messages:
                    continue
                    
                all_messages_text = " ".join([m.get("content", "") for m in aggregated_messages])
                user_messages = [m["content"] for m in aggregated_messages if m.get("role") == "user"]
                assistant_messages = [m["content"] for m in aggregated_messages if m.get("role") == "assistant"]
                user_text = " ".join(user_messages)
                assistant_text = " ".join(assistant_messages)
                latest_user_text = user_messages[-1] if user_messages else ""
                latest_assistant_text = assistant_messages[-1] if assistant_messages else ""
                
                # Check for human agent requests
                if not call_forwarded_flag and call_sid and support_phone_number:
                    # Check if user requested human agent
                    human_request_patterns = [
                        r"(?:i\s+)?(?:want|need|would like|can i|may i)\s+(?:to\s+)?(?:speak|talk)\s+(?:with|to)\s+(?:a\s+)?(?:human|person|agent|representative|real\s+person)",
                        r"(?:can|may)\s+(?:you\s+)?(?:connect|transfer|put)\s+(?:me\s+)?(?:through|to)\s+(?:a\s+)?(?:human|person|agent|representative)",
                        r"(?:let\s+me\s+)?(?:speak|talk)\s+(?:with|to)\s+(?:a\s+)?(?:human|person|agent|representative)",
                        r"(?:i\s+)?(?:want|need)\s+(?:a\s+)?(?:human|person|agent|representative)",
                        r"(?:get|put)\s+(?:me\s+)?(?:a\s+)?(?:human|person|agent|representative)",
                    ]
                    
                    user_requested_human = False
                    for pattern in human_request_patterns:
                        if re.search(pattern, user_text, re.IGNORECASE):
                            user_requested_human = True
                            logger.info("User requested to speak with a human agent")
                            break
                    
                    # Check if assistant acknowledged the request (indicates LLM detected it)
                    assistant_acknowledged = ASSISTANT_HUMAN_ACK_PATTERN.search(assistant_text)
                    if assistant_acknowledged:
                        ack_text = assistant_acknowledged.group(0).lower()
                        if "loan specialist" in ack_text or LOAN_AGENT_NAME.lower() in ack_text:
                            assistant_acknowledged = None
                    
                    if user_requested_human or assistant_acknowledged:
                        logger.info(f"Human agent request detected. Forwarding call {call_sid} to {support_phone_number}")
                        call_forwarded_flag = True
                        # Forward the call to human agent
                        forward_call_to_agent(call_sid, support_phone_number)
                        # Continue monitoring (call forwarding happens via Twilio, stream may continue briefly)
                        continue
                
                if current_agent == "welcome":
                    start_requested = any(
                        re.search(pattern, user_text, re.IGNORECASE)
                        for pattern in START_APPLICATION_PATTERNS
                    )
                    assistant_handoff = False
                    if LOAN_AGENT_NAME.lower() in latest_assistant_text.lower():
                        assistant_handoff = True
                    
                    if start_requested or assistant_handoff:
                        await switch_to_loan_agent()
                        # After switching, continue loop to allow the new intro to play
                        continue
                    
                    # No data to collect in welcome mode
                    continue
                
                # Only the loan specialist agent should collect borrower data
                if loan_flow_stage == "awaiting_name" and not collected_data["name"]:
                    name_match = None
                    name_patterns = [
                        r"(?:my\s+)?full\s+name\s+is\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})",
                        r"(?:my name is|i'm|i am|this is|it's|it is)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})",
                        r"([A-Z][a-z]+\s+[A-Z][a-z]+)",  # Simple First Last pattern
                    ]
                    for pattern in name_patterns:
                        name_match = re.search(pattern, latest_user_text, re.IGNORECASE)
                        if name_match:
                            break
                    if name_match:
                        if name_match.lastindex:
                            collected_data["name"] = name_match.group(1).strip()
                        else:
                            collected_data["name"] = name_match.group(0).strip()
                        logger.info(f"Extracted name: {collected_data['name']}")
                        loan_flow_stage = "awaiting_email"
                        continue
                    await nudge_stage("awaiting_name")
                    continue
                
                if loan_flow_stage == "awaiting_email" and not collected_data["email"]:
                    email_candidate_user = extract_email_from_text(latest_user_text)
                    assistant_email_candidate = extract_email_from_text(latest_assistant_text)

                    if email_candidate_user:
                        if is_valid_email_address(email_candidate_user):
                            collected_data["email"] = email_candidate_user
                            pending_email_candidate = None
                            last_invalid_email_attempt = None
                            loan_flow_stage = "awaiting_zip"
                            logger.info(f"Extracted email from user input: {collected_data['email']}")
                            continue
                        if last_invalid_email_attempt != email_candidate_user:
                            last_invalid_email_attempt = email_candidate_user
                            await nudge_stage("awaiting_email")
                            continue

                    if assistant_email_candidate and is_valid_email_address(assistant_email_candidate):
                        pending_email_candidate = assistant_email_candidate

                    if (
                        pending_email_candidate
                        and AFFIRMATIVE_PATTERN.search(latest_user_text)
                        and not extract_email_from_text(latest_user_text)
                    ):
                        collected_data["email"] = pending_email_candidate
                        pending_email_candidate = None
                        last_invalid_email_attempt = None
                        loan_flow_stage = "awaiting_zip"
                        logger.info(f"Extracted email from assistant confirmation: {collected_data['email']}")
                        continue

                    if re.search(r"\bsent\b.*email", assistant_text, re.IGNORECASE):
                        await nudge_stage("awaiting_email")
                        continue
                    continue
                
                if loan_flow_stage == "awaiting_zip" and not collected_data["zip_code"]:
                    zip_value = extract_zip_from_text(latest_user_text)
                    if not zip_value:
                        zip_value = extract_zip_from_text(latest_assistant_text)
                    if not zip_value:
                        alt_zip_user = re.search(r"(?:that's|is|zip code is|zip is)\s+(\d{5})", latest_user_text, re.IGNORECASE)
                        if alt_zip_user:
                            zip_value = alt_zip_user.group(1)
                    if not zip_value:
                        alt_zip_assistant = re.search(r"(?:that's|is|zip code is|zip is)\s+(\d{5})", latest_assistant_text, re.IGNORECASE)
                        if alt_zip_assistant:
                            zip_value = alt_zip_assistant.group(1)
                    if zip_value:
                        collected_data["zip_code"] = zip_value
                        logger.info(f"Extracted zip code: {collected_data['zip_code']}")
                        loan_flow_stage = "ready_to_send"
                        await check_and_send_email()
                        continue
                    await nudge_stage("awaiting_zip")
                    continue
                
                if loan_flow_stage == "ready_to_send":
                    await check_and_send_email()
                    continue
                
                if loan_flow_stage == "completed":
                    continue
                
                await check_and_send_email()
            except Exception as e:
                logger.error(f"Error in monitor_messages: {e}", exc_info=True)
                await asyncio.sleep(2)
    
    monitor_task = None

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal monitor_task
        # Start monitoring task when client connects
        monitor_task = asyncio.create_task(monitor_messages())
        logger.info("Email monitoring task created")
        
        # Kick off the conversation with the welcome agent
        opening_message = {
            "role": "system", 
            "content": (
                f"Say: 'Hello! This is {WELCOME_AGENT_NAME}, your {company_name} welcome concierge. "
                "I can answer questions or get you to the right teammate. How can I help today?'"
            ),
        }
        messages.append(opening_message)
        sync_context()
        await task.queue_frames([LLMMessagesFrame(list(messages))])
        messages.pop()
        sync_context()

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        nonlocal monitor_task
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)