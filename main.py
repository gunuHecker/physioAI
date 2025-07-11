import asyncio
import base64
import json
import os
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
import uvicorn

from myAgents.agent import root_agent
from myAgents.state_schema import StateManager, ALIASessionState

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

#
# ADK Streaming
#

# Load Gemini Auth info
load_dotenv()

# Set Google Application Credentials from .env or hardcoded path
credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/home/rps/DeeCogs/google-adk/credentials.json")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

APP_NAME = "Physio AI"

async def start_agent_session(user_id, is_audio=False, enable_video=False):
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
            user_id=user_id,
        )

        print(f"[DEBUG] Session created: {session.id}")

        # Initialize ALIA state for this session
        initial_state = StateManager.create_initial_state(
            user_id=user_id, 
            session_id=session.id
        )
        
        # Store initial state in session
        session.state.update(initial_state.to_dict())
        print(f"[DEBUG] Initialized ALIA state for session {session.id}")
        print(f"[STATE] Initial state: {initial_state.get_summary()}")

        # Set response modalities based on capabilities
        modalities = []
        if is_audio:
            modalities.append("AUDIO")
        else:
            modalities.append("TEXT")
        
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
        return live_events, live_request_queue, session
        
    except Exception as e:
        print(f"[ERROR] Failed to start agent session: {e}")
        raise

async def agent_to_client_messaging(websocket, live_events, session):
    """Agent to client communication"""
    try:
        print("[DEBUG] Starting agent_to_client_messaging")
        while True:
            print("[DEBUG] Waiting for events from agent...")
            async for event in live_events:
                # Add agent identification to the debug
                agent_author = getattr(event, 'author', 'unknown')
                print(f"[DEBUG] 📨 Event from: {agent_author} | Turn Complete: {event.turn_complete} | Partial: {event.partial}")
                
                # If the turn complete or interrupted, send it
                if event.turn_complete or event.interrupted:
                    message = {
                        "turn_complete": event.turn_complete,
                        "interrupted": event.interrupted,
                    }
                    await websocket.send_text(json.dumps(message))
                    print(f"[AGENT TO CLIENT] 🏁 Turn complete from {agent_author}: {message}")
                    
                    # Optional: Send state summary for debugging
                    try:
                        # session.state is already a dict
                        current_state_dict = session.state
                        if current_state_dict:
                            state = ALIASessionState.from_dict(current_state_dict)
                            print(f"[STATE SUMMARY] 📊 {state.get_summary()}")
                            
                            # Send state info to client for debugging (optional)
                            state_message = {
                                "mime_type": "application/json",
                                "data": {
                                    "type": "state_update",
                                    "stage": state.conversation_stage.value,
                                    "summary": state.get_summary()
                                }
                            }
                            await websocket.send_text(json.dumps(state_message))
                    except Exception as e:
                        print(f"[DEBUG] Could not extract state: {e}")
                    
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

                # If it's text and a partial text, send it
                if part.text and event.partial:
                    message = {
                        "mime_type": "text/plain",
                        "data": part.text
                    }
                    await websocket.send_text(json.dumps(message))
                    print(f"[AGENT TO CLIENT]: text/plain: {part.text}")

    except Exception as e:
        print(f"[ERROR] Failed to get agent to client messages: {e}")
        raise

async def client_to_agent_messaging(websocket, live_request_queue, session):
    """Client to agent communication"""
    try:
        while True:
            # Decode JSON message
            message_json = await websocket.receive_text()
            message = json.loads(message_json)
            mime_type = message["mime_type"]
            data = message["data"]

            print(f"[CLIENT TO AGENT] Received: {mime_type}")

            # Update session state with user message if it's text
            if mime_type == "text/plain":
                try:
                    # session.state is already a dict
                    current_state_dict = session.state
                    if current_state_dict:
                        state = ALIASessionState.from_dict(current_state_dict)
                        state.update_interaction(user_message=data)
                        session.state.update(state.to_dict())
                        print(f"[STATE] Updated with user message: '{data}' | Stage: {state.conversation_stage.value}")
                except Exception as e:
                    print(f"[WARNING] Could not update state with user message: {e}")

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
                # print(f"[CLIENT TO AGENT]: audio/pcm: {len(decoded_data)} bytes")
                
            # Send video/images to the Agent
            elif mime_type == "image/jpeg":
                # Send an image data
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
                print(f"[CLIENT TO AGENT]: image/jpeg: {len(decoded_data)} bytes")

            elif mime_type.startswith("image/") or mime_type.startswith("video/"):
                # Send video frame or image data
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
                print(f"[CLIENT TO AGENT]: {mime_type}: {len(decoded_data)} bytes")

            else:
                print(f"[WARNING] Unsupported mime type: {mime_type}")
                
    except Exception as e:
        print(f"[ERROR] Client to agent messaging error: {e}")
        raise

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

    session = None
    live_request_queue = None
    
    try:
        # Start agent session
        user_id_str = str(user_id)
        live_events, live_request_queue, session = await start_agent_session(
            user_id_str, 
            is_audio == "true", 
            enable_video == "true"
        )

        print(f"[DEBUG] Session {session.id} ready for user {user_id}")

        # Start tasks
        agent_to_client_task = asyncio.create_task(
            agent_to_client_messaging(websocket, live_events, session)
        )
        client_to_agent_task = asyncio.create_task(
            client_to_agent_messaging(websocket, live_request_queue, session)
        )

        # Wait until the websocket is disconnected or an error occurs
        tasks = [agent_to_client_task, client_to_agent_task]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        
        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        print(f"[ERROR] WebSocket error for user {user_id}: {e}")
        
        # Send error message to client if possible
        try:
            error_message = {
                "mime_type": "text/plain",
                "data": f"Sorry, there was an error: {str(e)}"
            }
            await websocket.send_text(json.dumps(error_message))
        except:
            pass
            
    finally:
        # Cleanup
        try:
            if live_request_queue:
                live_request_queue.close()
            
            if session:
                # Final state summary (simplified)
                try:
                    if hasattr(session, 'state') and session.state is not None:
                        current_state_dict = session.state.to_dict()
                        if current_state_dict:
                            final_state = ALIASessionState.from_dict(current_state_dict)
                            print(f"[SESSION END] Final state for user {user_id}: {final_state.get_summary()}")
                    else:
                        print("[DEBUG] No session state available for cleanup")
                except Exception as e:
                    print(f"[WARNING] Could not finalize session state: {e}")
                    
            print(f"Client #{user_id} session cleaned up")
            
        except Exception as cleanup_error:
            print(f"[ERROR] Cleanup error: {cleanup_error}")

        # Disconnected
        print(f"Client #{user_id} disconnected")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "app": APP_NAME}


@app.get("/debug/session/{user_id}")
async def debug_session(user_id: str):
    """Debug endpoint to check session state (for development)"""
    try:
        # This is a simplified debug endpoint
        # In a real implementation, you'd need to store session references
        return {
            "user_id": user_id,
            "message": "Debug endpoint - session state would be shown here",
            "note": "Implement session storage for debug access"
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    print(f"Starting {APP_NAME} server...")
    print("ALIA Simplified Agent System:")
    print("  - Root LLM Agent (ALIA)")
    print("  - Greeting Agent Tool")
    print("  - Pain Analysis Agent Tool")
    print()
    uvicorn.run(app, host="0.0.0.0", port=8000)