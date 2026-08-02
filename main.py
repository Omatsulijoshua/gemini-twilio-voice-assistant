import os
import json
import uvicorn
from google import genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from twilio.rest import Client as TwilioClient

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
PORT = int(os.getenv("PORT", "8080"))
DOMAIN = os.getenv("NGROK_URL") or os.getenv("RENDER_EXTERNAL_HOSTNAME")
if not DOMAIN:
    DOMAIN = f"localhost:{PORT}"
WS_URL = f"wss://{DOMAIN}/ws"
BASE_URL = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or f"https://{DOMAIN}"

# Updated greeting to reflect the new model
WELCOME_GREETING = "Hi! I am a voice assistant powered by Twilio and Google Gemini. Ask me anything!"

# System prompt for Gemini
# Gemini works well with a direct instruction like this.
SYSTEM_PROMPT = """You are a helpful and friendly voice assistant. This conversation is happening over a phone call, so your responses will be spoken aloud. 
Please adhere to the following rules:
1. Provide clear, concise, and direct answers.
2. Spell out all numbers (e.g., say 'one thousand two hundred' instead of 1200).
3. Do not use any special characters like asterisks, bullet points, or emojis.
4. Keep the conversation natural and engaging."""

# --- Gemini API Initialization ---
# Get your Google API key from https://aistudio.google.com/app/apikey
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Initialize the Gemini client with the new SDK
client = genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = (
    TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
    else None
)

# Store active chat sessions
# We will now store Gemini's chat session objects
sessions = {}

# Create FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Small public status response for browsers and hosting checks."""
    return {
        "service": "Voxora Voice API",
        "status": "online",
        "gemini_configured": client is not None,
        "model": "gemini-2.5-flash",
    }


@app.get("/health")
async def health():
    """Render health-check endpoint."""
    return {"status": "healthy"}


class CallRequest(BaseModel):
    phone_number: str


@app.post("/call")
async def start_outbound_call(request: CallRequest):
    """Ask Twilio to call a visitor and connect them to Voxora."""
    phone_number = request.phone_number.strip()
    if not phone_number.startswith("+") or not phone_number[1:].isdigit() or not 8 <= len(phone_number[1:]) <= 15:
        raise HTTPException(status_code=400, detail="Enter a valid phone number in international format, for example +2348012345678.")
    if not twilio_client or not TWILIO_PHONE_NUMBER:
        raise HTTPException(status_code=503, detail="Outbound calling is not configured yet. Add the Twilio environment variables in Render.")
    try:
        call = twilio_client.calls.create(
            to=phone_number,
            from_=TWILIO_PHONE_NUMBER,
            url=f"{BASE_URL}/twiml",
        )
        return {"status": "queued", "message": "Your phone should ring shortly.", "call_sid": call.sid}
    except Exception as error:
        print(f"Twilio call failed: {error}")
        raise HTTPException(status_code=502, detail="Twilio could not start the call. Check the number and account settings.")

def gemini_response(chat_session, user_prompt):
    """Get a response from the Gemini API."""
    response = chat_session.send_message(user_prompt)
    return response.text

@app.post("/twiml")
async def twiml_endpoint():
    """Endpoint that returns TwiML for Twilio to connect to the WebSocket"""
    # Note: Twilio ConversationRelay has built-in TTS. We specify a provider and voice.
    # You can change 'ElevenLabs' to 'Amazon' or 'Google' if you prefer their TTS.
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
    <Connect>
    <ConversationRelay url="{WS_URL}" welcomeGreeting="{WELCOME_GREETING}" ttsProvider="ElevenLabs" voice="FGY2WhTYpPnrIDTdsKH5" />
    </Connect>
    </Response>"""
    
    return Response(content=xml_response, media_type="text/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    call_sid = None
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "setup":
                call_sid = message["callSid"]
                print(f"Setup for call: {call_sid}")
                # Start a new chat session for this call using the new SDK
                sessions[call_sid] = (
                    client.chats.create(
                        model="gemini-2.5-flash",
                        config={"system_instruction": SYSTEM_PROMPT}
                    )
                    if client
                    else None
                )
                
            elif message["type"] == "prompt":
                if not call_sid or call_sid not in sessions:
                    print(f"Error: Received prompt for unknown call_sid {call_sid}")
                    continue

                user_prompt = message["voicePrompt"]
                print(f"Processing prompt: {user_prompt}")
                
                chat_session = sessions[call_sid]
                if chat_session is None:
                    response_text = (
                        "The voice assistant is online but still needs its "
                        "Google Gemini API key configured."
                    )
                else:
                    response_text = gemini_response(chat_session, user_prompt)
                
                # The chat_session object automatically maintains history.
                
                # Send the complete response back to Twilio.
                # Twilio's ConversationRelay will handle the text-to-speech conversion.
                await websocket.send_text(
                    json.dumps({
                        "type": "text",
                        "token": response_text,
                        "last": True  # Indicate this is the full and final message
                    })
                )
                print(f"Sent response: {response_text}")
                
            elif message["type"] == "interrupt":
                print(f"Handling interruption for call {call_sid}.")
                
            else:
                print(f"Unknown message type received: {message['type']}")
                
    except WebSocketDisconnect:
        print(f"WebSocket connection closed for call {call_sid}")
        if call_sid in sessions:
            sessions.pop(call_sid)
            print(f"Cleared session for call {call_sid}")

if __name__ == "__main__":
    print(f"Starting server on port {PORT}")
    print(f"WebSocket URL for Twilio: {WS_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
