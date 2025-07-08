import os
import json
import asyncio
import base64
import warnings

from pathlib import Path
from dotenv import load_dotenv

from google.genai.types import (
    Part,
    Content,
    Blob,
)

from google.adk.runners import InMemoryRunner
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from myAgents.agent import root_agent

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

#
# ADK Streaming
#

# Load Gemini Auth info
load_dotenv()

APP_NAME = "Physio AI"

async def start_agent_session(user_id, is_audio=False,enable_video=False):
    """Starts an agent session"""
    try:
        print(f"[DEBUG] Creating runner for user {user_id}")
        
        # Create a Runner
        runner = InMemoryRunner(
            app_name=APP_NAME,
            agent=root_agent,
        )

        print(f"[DEBUG] Creating session for user {user_id}")
        
        # Create a Session
        session = await runner.session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,  # Replace with actual user ID
        )

        print(f"[DEBUG] Session created: {session}")

        # Set response modalities based on capabilities
        modalities = []
        if is_audio:
            modalities.append("AUDIO")
        else:
            modalities.append("TEXT")
        
        # Video input doesn't require special modality config
        # as it's sent as content parts, not real-time streams
        
        run_config = RunConfig(response_modalities=modalities)
        
        print(f"[DEBUG] Using modalities: {modalities}, video enabled: {enable_video}")

        # Create a LiveRequestQueue for this session
        live_request_queue = LiveRequestQueue()

        print(f"[DEBUG] Starting live events")
        
        # Start agent session
        live_events = runner.run_live(
            session=session,
            live_request_queue=live_request_queue,
            run_config=run_config,
        )
        
        print(f"[DEBUG] Live events started successfully")
        return live_events, live_request_queue
        
    except Exception as e:
        print(f"[ERROR] Failed to start agent session: {e}")
        raise

async def agent_to_client_messaging(websocket, live_events):
    """Agent to client communication"""
    try:
        print("[DEBUG] Starting agent_to_client_messaging")
        while True:
            print("[DEBUG] Waiting for events from agent...")
            async for event in live_events:
                print(f"[DEBUG] Received event: {event}")
                
                # If the turn complete or interrupted, send it
                if event.turn_complete or event.interrupted:
                    message = {
                        "turn_complete": event.turn_complete,
                        "interrupted": event.interrupted,
                    }
                    await websocket.send_text(json.dumps(message))
                    print(f"[AGENT TO CLIENT]: {message}")
                    continue

                # Read the Content and its first Part
                part: Part = (
                    event.content and event.content.parts and event.content.parts[0]
                )
                if not part:
                    print("[DEBUG] No part found in event")
                    continue

                print(f"[DEBUG] Part content: {part}")
            
                # If it's audio, send Base64 encoded audio data
                is_audio = part.inline_data and part.inline_data.mime_type.startswith("audio/pcm")
                if is_audio:
                    audio_data = part.inline_data and part.inline_data.data
                    if audio_data:
                        message = {
                            "mime_type": "audio/pcm",
                            "data": base64.b64encode(audio_data).decode("ascii")
                        }
                        await websocket.send_text(json.dumps(message))
                        print(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.")
                        continue

                # If it's text and a parial text, send it
                if part.text and event.partial:
                    message = {
                        "mime_type": "text/plain",
                        "data": part.text
                    }
                    await websocket.send_text(json.dumps(message))
                    print(f"[AGENT TO CLIENT]: text/plain: {message}")

    except Exception as e:
        print(f"[ERROR] Failed to get agent to client messages: {e}")
        raise

async def client_to_agent_messaging(websocket, live_request_queue):
    """Client to agent communication"""
    while True:
        # Decode JSON message
        message_json = await websocket.receive_text()
        message = json.loads(message_json)
        mime_type = message["mime_type"]
        data = message["data"]

        # Send the message to the agent
        if mime_type == "text/plain":
            # Send a text message
            content = Content(role="user", parts=[Part.from_text(text=data)])
            live_request_queue.send_content(content=content)
            print(f"[CLIENT TO AGENT]: {data}")
        elif mime_type == "audio/pcm":
            # Send an audio data
            decoded_data = base64.b64decode(data)
            live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
            print(f"[CLIENT TO AGENT]: audio/pcm: {len(decoded_data)} bytes")
        elif mime_type.startswith("image/") or mime_type.startswith("video/"):
            # Send video frame or image data
            decoded_data = base64.b64decode(data)
            content = Content(
                role="user", 
                parts=[Part(inline_data=Blob(data=decoded_data, mime_type=mime_type))]
            )
            live_request_queue.send_content(content=content)
            print(f"[CLIENT TO AGENT]: {mime_type}: {len(decoded_data)} bytes")
        else:
            raise ValueError(f"Mime type not supported: {mime_type}")
        
#
# FastAPI web app
#

app = FastAPI()

STATIC_DIR = Path("static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serves the index.html"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, is_audio: str, enable_video: str = "false"):
    """Client websocket endpoint"""

    # Wait for client connection
    await websocket.accept()
    print(f"Client #{user_id} connected, audio mode: {is_audio}, video mode: {enable_video}")

    # Start agent session
    user_id_str = str(user_id)
    live_events, live_request_queue = await start_agent_session(
        user_id_str, 
        is_audio == "true", 
        enable_video == "true"
    )

    # Start tasks
    agent_to_client_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events)
    )
    client_to_agent_task = asyncio.create_task(
        client_to_agent_messaging(websocket, live_request_queue)
    )

    # Wait until the websocket is disconnected or an error occurs
    tasks = [agent_to_client_task, client_to_agent_task]
    await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    # Close LiveRequestQueue
    live_request_queue.close()

    # Disconnected
    print(f"Client #{user_id} disconnected")

