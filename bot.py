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

async def main(websocket_client, stream_sid):
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
            language="multi"
        )
    )

    email_sent = False
    
    async def check_and_send_email():
        nonlocal email_sent
        if email_sent:
            return
        
        messages = context.get_messages()
        all_text = " ".join([m.get("content", "") for m in messages])
        user_text = " ".join([m["content"] for m in messages if m.get("role") == "user"])
        
        # Extract email
        email_match = re.search(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', all_text)
        # Extract zip code (5 digits)
        zip_match = re.search(r'\b\d{5}\b', all_text)
        # Extract name
        name_match = None
        name_patterns = [
            r"(?:my name is|i'm|i am|this is|it's|it is)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})",
            r"(?:name is|called)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})",
        ]
        for pattern in name_patterns:
            name_match = re.search(pattern, user_text, re.IGNORECASE)
            if name_match:
                break
        if not name_match:
            words = re.findall(r'\b[A-Z][a-z]+\b', user_text)
            if len(words) >= 2:
                name_match = type('obj', (object,), {'group': lambda x: ' '.join(words[:2])})()
        
        if email_match and zip_match and name_match:
            name = name_match.group(1).strip() if hasattr(name_match, 'group') else name_match
            email = email_match.group(0)
            zip_code = zip_match.group(0)
            
            link = f"{base_url}/loan-application?legal_name={urllib.parse.quote(name)}&email={urllib.parse.quote(email)}&zip_code={urllib.parse.quote(zip_code)}"
            success = await email_service.send_application_link(email, name, link)
            email_sent = True
            logger.info(f"Email sent to {email} for {name}, zip {zip_code}, Success: {success}")

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
    
    # Start background task to check and send email periodically
    async def email_check_task():
        while True:
            await asyncio.sleep(2)  # Check every 2 seconds
            await check_and_send_email()
    
    email_task = asyncio.create_task(email_check_task())

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Kick off the conversation with the opening message
        opening_message = {
            "role": "system", 
            "content": "Say: 'Hi, you have reached the quick pre-approval line. We can estimate your eligible amount in a under 3 minutes. May I proceed?'"
        }
        messages.append(opening_message)
        await task.queue_frames([LLMMessagesFrame(messages)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        email_task.cancel()
        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)