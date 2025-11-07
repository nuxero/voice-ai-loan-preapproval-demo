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

from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from email_service import get_email_service

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

async def main(websocket_client, stream_sid, call_sid=None):
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
    elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    
    email_service = get_email_service()

    stt = DeepgramSTTService(
        api_key=deepgram_api_key,
        live_options=LiveOptions(
            model="nova-2-general",
            language="multi",
            keywords=["agilityfeat", "google", "microsoft", "aws"]
        )
    )

    llm = OpenAILLMService(
        name="LLM",
        api_key=openai_api_key,
        model="gpt-4o",
    )
    

    tts = ElevenLabsTTSService(
        api_key=elevenlabs_api_key,
        model="eleven_multilingual_v2",
        voice_id="Xb7hH8MSUJpSbSDYk0k2"
    )

    messages = [
        {
            "role": "system",
            "content": """
You are a professional and friendly loan pre-approval assistant for a fintech company. Your role is to help customers get a quick loan pre-approval estimate.

Your workflow:
1. Opening: Greet the caller warmly and introduce the quick pre-approval service. Ask if you can proceed to help them get an estimate.
2. Consent checkpoint: Explain that you'll use a soft credit inquiry that does not impact their credit score. Get their explicit consent before proceeding.
3. Collect basics: Gather the following information IN THIS ORDER:
   - Full name (legal name)
   - Email address (where you will send the secure link)
   - Zip code
4. Link handoff: AFTER collecting all three pieces of information (full name, email, and zip code), confirm that you've sent the secure link to their email and offer to stay on the line if they need help.

IMPORTANT: Only mention sending the link AFTER you have collected the full name, email, and zip code. Do not mention the link during the opening or consent phases.

Human Agent Option:
- If the caller requests to speak with a human agent, representative, or person, acknowledge their request and say: "I'll connect you with one of our agents right away."
- After saying this, the system will automatically forward the call. Do not try to continue the conversation after acknowledging the request.

Guidelines:
- Be professional, warm, and helpful
- Speak clearly and at a moderate pace
- Confirm information as you collect it
- If the caller seems hesitant, address their concerns
- Keep the conversation focused on the pre-approval process
- Be concise but thorough
- Use natural, conversational language
- After collecting all three pieces of information, confirm that the link has been sent to their email""",
        },
    ]
    print('here', flush=True)
    context = OpenAILLMContext(messages=messages)
    context_aggregator = llm.create_context_aggregator(context)
    
    # Store collected data
    collected_data = {"name": None, "email": None, "zip_code": None}
    
    # Monitor messages and send email when all data is collected
    email_sent_flag = False
    
    # Track if call has been forwarded to human agent
    call_forwarded_flag = False
    support_phone_number = os.getenv("SUPPORT_PHONE_NUMBER")
    
    async def check_and_send_email():
        nonlocal email_sent_flag
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
    
    # Background task to check for collected data and human agent requests
    async def monitor_messages():
        nonlocal call_forwarded_flag
        logger.info("Email monitor task started")
        while True:
            try:
                await asyncio.sleep(2)
                messages = context.get_messages()
                if not messages:
                    continue
                    
                all_messages_text = " ".join([m.get("content", "") for m in messages])
                user_messages = [m["content"] for m in messages if m.get("role") == "user"]
                assistant_messages = [m["content"] for m in messages if m.get("role") == "assistant"]
                user_text = " ".join(user_messages)
                assistant_text = " ".join(assistant_messages)
                
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
                    assistant_acknowledged = re.search(
                        r"(?:i'll|i will|let me)\s+(?:connect|transfer|put)\s+(?:you\s+)?(?:with|to|through)\s+(?:one\s+of\s+)?(?:our\s+)?(?:agents?|representatives?)",
                        assistant_text,
                        re.IGNORECASE
                    )
                    
                    if user_requested_human or assistant_acknowledged:
                        logger.info(f"Human agent request detected. Forwarding call {call_sid} to {support_phone_number}")
                        call_forwarded_flag = True
                        # Forward the call to human agent
                        forward_call_to_agent(call_sid, support_phone_number)
                        # Continue monitoring (call forwarding happens via Twilio, stream may continue briefly)
                        continue
                
                # Extract email from all messages (might be in assistant confirmation)
                email_match = re.search(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', all_messages_text)
                
                # Extract zip code - look for 5 digits (LLM might have normalized it)
                zip_match = re.search(r'\b\d{5}\b', all_messages_text)
                # Also look for zip code in assistant confirmations like "that's 33141"
                if not zip_match:
                    zip_match = re.search(r"(?:that's|is|zip code is|zip is)\s+(\d{5})", all_messages_text, re.IGNORECASE)
                    if zip_match:
                        zip_match = type('obj', (object,), {'group': lambda x: zip_match.group(1)})()
                
                # Extract name - look in user messages for "full name is" pattern
                name_match = None
                name_patterns = [
                    r"(?:my\s+)?full\s+name\s+is\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})",
                    r"(?:my name is|i'm|i am|this is|it's|it is)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})",
                    r"([A-Z][a-z]+\s+[A-Z][a-z]+)",  # Simple First Last pattern
                ]
                for pattern in name_patterns:
                    name_match = re.search(pattern, user_text, re.IGNORECASE)
                    if name_match:
                        break
                
                # Update collected data
                if email_match and not collected_data["email"]:
                    collected_data["email"] = email_match.group(0)
                    logger.info(f"Extracted email: {collected_data['email']}")
                
                if zip_match and not collected_data["zip_code"]:
                    collected_data["zip_code"] = zip_match.group(0)
                    logger.info(f"Extracted zip code: {collected_data['zip_code']}")
                
                if name_match and not collected_data["name"]:
                    if name_match.lastindex:
                        collected_data["name"] = name_match.group(1).strip()
                    else:
                        collected_data["name"] = name_match.group(0).strip()
                    logger.info(f"Extracted name: {collected_data['name']}")
                
                logger.debug(f"Current collected data: {collected_data}")
                await check_and_send_email()
            except Exception as e:
                logger.error(f"Error in monitor_messages: {e}", exc_info=True)
                await asyncio.sleep(2)
    
    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))
    
    monitor_task = None

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal monitor_task
        # Start monitoring task when client connects
        monitor_task = asyncio.create_task(monitor_messages())
        logger.info("Email monitoring task created")
        
        # Kick off the conversation with the opening message
        opening_message = {
            "role": "system", 
            "content": "Say: 'Hi, you have reached the quick pre-approval line. We can estimate your eligible amount in a under 3 minutes. May I proceed?'"
        }
        messages.append(opening_message)
        await task.queue_frames([LLMMessagesFrame(messages)])

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