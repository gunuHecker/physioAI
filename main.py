import asyncio
import base64
import json
import os
import warnings
import logging
from pathlib import Path
from dotenv import load_dotenv
from contextlib import suppress

from google.genai.types import (
    Part,
    Content,
    Blob,
)

from google.adk.runners import InMemoryRunner
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from myAgents.agent import root_agent
from myAgents.state_schema import StateManager, ALIASessionState

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Load environment variables FIRST
load_dotenv()

# Set Google Application Credentials BEFORE any Google imports
credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/home/rps/DeeCogs/google-adk/credentials.json")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

# Configure Google AI settings based on .env
if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE").upper() == "TRUE":
    # Vertex AI configuration
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    if os.getenv("GOOGLE_CLOUD_PROJECT"):
        os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT")
    if os.getenv("GOOGLE_CLOUD_LOCATION"):
        os.environ["GOOGLE_CLOUD_LOCATION"] = os.getenv("GOOGLE_CLOUD_LOCATION")
else:
    # Google AI Studio configuration
    if os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# Configure logging with environment variable
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - PHYSIO_AI - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('physio_ai.log')
    ]
)

logger = logging.getLogger(__name__)

APP_NAME = "Physio AI"
STATIC_DIR = Path("static")

# Global runner instance
runner = None

async def initialize_adk_system():
    """Initialize the ADK system with proper error handling"""
    global runner
    try:
        runner = InMemoryRunner(
            app_name=APP_NAME,
            agent=root_agent,
        )
        logger.info(f"ADK Runner initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize ADK system: {e}")
        raise

# FastAPI app with startup event
app = FastAPI(title="Physio AI Live Server")

@app.on_event("startup")
async def startup_event():
    """Initialize system on startup"""
    logger.info("FastAPI server starting up...")
    logger.info(f"Google AI Configuration:")
    logger.info(f"  - Use Vertex AI: {os.getenv('GOOGLE_GENAI_USE_VERTEXAI', 'FALSE')}")
    logger.info(f"  - Project: {os.getenv('GOOGLE_CLOUD_PROJECT', 'Not set')}")
    logger.info(f"  - Location: {os.getenv('GOOGLE_CLOUD_LOCATION', 'Not set')}")
    logger.info(f"  - Credentials: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'Not set')}")
    
    await initialize_adk_system()
    if not runner:
        logger.critical("ADK Runner failed to initialize during startup")
    else:
        logger.info("ADK System initialized successfully")

# Updated WebSocket endpoint with better session handling
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, is_audio: str = "false", enable_video: str = "false"):
    """Client websocket endpoint with improved error handling"""
    await websocket.accept()
    logger.info(f"[{session_id}] Client connected, audio mode: {is_audio}, video mode: {enable_video}")

    if not runner:
        logger.error(f"[{session_id}] Runner not initialized. Aborting connection.")
        await websocket.close(code=1011, reason="Server not ready")
        return

    session = None
    live_request_queue = None
    
    try:
        # Create session with proper error handling
        user_id_str = f"user_{session_id}"
        
        # Create session using the working approach from your original code
        session = await runner.session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id_str,
        )

        # Initialize ALIA state
        initial_state = StateManager.create_initial_state(
            user_id=user_id_str, 
            session_id=session.id
        )
        session.state.update(initial_state.to_dict())
        logger.info(f"[{session_id}] Session created with initial state: {initial_state.get_summary()}")

        # Set response modalities
        modalities = ["AUDIO"] if is_audio == "true" else ["TEXT"]
        run_config = RunConfig(response_modalities=modalities)
        
        live_request_queue = LiveRequestQueue()
        
        # Use the working approach from your original code
        live_events = runner.run_live(
            session=session,
            live_request_queue=live_request_queue,
            run_config=run_config,
        )

        async def agent_to_client():
            """Handle agent to client communication"""
            logger.debug(f"[{session_id}] Starting agent_to_client task")
            try:
                async for event in live_events:
                    agent_author = getattr(event, 'author', 'unknown')
                    logger.debug(f"[{session_id}] 📨 Event from: {agent_author} | Turn Complete: {event.turn_complete} | Partial: {event.partial}")
                    
                    if event.turn_complete or event.interrupted:
                        message = {
                            "turn_complete": event.turn_complete,
                            "interrupted": event.interrupted,
                        }
                        await websocket.send_text(json.dumps(message))
                        logger.info(f"[{session_id}] 🏁 Turn complete from {agent_author}: {message}")
                        
                        # Send state update
                        try:
                            if session.state:
                                state = ALIASessionState.from_dict(session.state)
                                logger.info(f"[{session_id}] 📊 State summary: {state.get_summary()}")
                                
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
                            logger.debug(f"[{session_id}] Could not extract state: {e}")
                        continue

                    # Handle content
                    part = event.content and event.content.parts and event.content.parts[0]
                    if not part:
                        logger.debug(f"[{session_id}] No part found in event")
                        continue

                    logger.debug(f"[{session_id}] Part content: {part}")

                    # Audio content
                    if part.inline_data and part.inline_data.mime_type.startswith("audio/pcm"):
                        audio_data = part.inline_data.data
                        if audio_data:
                            message = {
                                "mime_type": "audio/pcm",
                                "data": base64.b64encode(audio_data).decode("ascii")
                            }
                            await websocket.send_text(json.dumps(message))
                            logger.info(f"[{session_id}] Agent to client - audio/pcm: {len(audio_data)} bytes")

                    # Text content
                    elif part.text and event.partial:
                        message = {
                            "mime_type": "text/plain",
                            "data": part.text
                        }
                        await websocket.send_text(json.dumps(message))
                        logger.info(f"[{session_id}] Agent to client - text/plain: {part.text}")

            except WebSocketDisconnect:
                logger.info(f"[{session_id}] WebSocket disconnected during agent processing")
            except asyncio.CancelledError:
                logger.info(f"[{session_id}] Agent to client task cancelled")
            except Exception as e:
                logger.error(f"[{session_id}] Error in agent_to_client: {e}")

        async def client_to_agent():
            """Handle client to agent communication"""
            logger.debug(f"[{session_id}] Starting client_to_agent task")
            try:
                while True:
                    message_json = await websocket.receive_text()
                    message = json.loads(message_json)
                    mime_type = message["mime_type"]
                    data = message["data"]

                    logger.info(f"[{session_id}] Client to agent - received: {mime_type}")

                    # Update session state with user message if it's text
                    if mime_type == "text/plain":
                        try:
                            if session.state:
                                state = ALIASessionState.from_dict(session.state)
                                state.update_interaction(user_message=data)
                                session.state.update(state.to_dict())
                                logger.info(f"[{session_id}] Updated state with user message: '{data}' | Stage: {state.conversation_stage.value}")
                        except Exception as e:
                            logger.warning(f"[{session_id}] Could not update state with user message: {e}")

                    # Send the message to the agent
                    if mime_type == "text/plain":
                        content = Content(role="user", parts=[Part.from_text(text=data)])
                        live_request_queue.send_content(content=content)
                        logger.info(f"[{session_id}] Client to agent - text: {data}")
                        
                    elif mime_type == "audio/pcm":
                        decoded_data = base64.b64decode(data)
                        live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
                        logger.debug(f"[{session_id}] Client to agent - audio/pcm: {len(decoded_data)} bytes")
                        
                    elif mime_type == "image/jpeg":
                        decoded_data = base64.b64decode(data)
                        live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
                        logger.info(f"[{session_id}] Client to agent - image/jpeg: {len(decoded_data)} bytes")

                    elif mime_type.startswith("image/") or mime_type.startswith("video/"):
                        decoded_data = base64.b64decode(data)
                        live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
                        logger.info(f"[{session_id}] Client to agent - {mime_type}: {len(decoded_data)} bytes")

                    else:
                        logger.warning(f"[{session_id}] Unsupported mime type: {mime_type}")

            except WebSocketDisconnect:
                logger.info(f"[{session_id}] Client disconnected")
                if live_request_queue:
                    live_request_queue.close()
            except asyncio.CancelledError:
                logger.info(f"[{session_id}] Client to agent task cancelled")
            except Exception as e:
                logger.error(f"[{session_id}] Error in client_to_agent: {e}")

        # Start communication tasks
        logger.info(f"[{session_id}] Starting communication bridge tasks")
        agent_task = asyncio.create_task(agent_to_client())
        client_task = asyncio.create_task(client_to_agent())
        
        done, pending = await asyncio.wait(
            [agent_task, client_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel remaining tasks
        for task in pending:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] WebSocket disconnected gracefully")
    except Exception as e:
        logger.error(f"[{session_id}] WebSocket error: {e}")
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
        logger.info(f"[{session_id}] Performing cleanup")
        if live_request_queue:
            try:
                live_request_queue.close()
            except Exception as e:
                logger.warning(f"[{session_id}] Error closing queue: {e}")
        
        if session:
            try:
                if session.state:
                    final_state = ALIASessionState.from_dict(session.state)
                    logger.info(f"[{session_id}] Session end - final state: {final_state.get_summary()}")
            except Exception as e:
                logger.warning(f"[{session_id}] Could not finalize session state: {e}")
        
        logger.info(f"[{session_id}] Client fully disconnected")

# Static files and routes
if not STATIC_DIR.is_dir():
    logger.error(f"Static directory not found at {STATIC_DIR}")
else:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def root():
    """Serves the index.html"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "app": APP_NAME,
        "runner_ready": runner is not None
    }

@app.get("/debug/session/{session_id}")
async def debug_session(session_id: str):
    """Debug endpoint to check session state"""
    return {
        "session_id": session_id,
        "message": "Debug endpoint - session state would be shown here",
        "note": "Implement session storage for debug access"
    }

if __name__ == "__main__":
    logger.info(f"Starting {APP_NAME} server...")
    logger.info("ALIA Simplified Agent System:")
    logger.info("  - Root LLM Agent (ALIA)")
    logger.info("  - Greeting Agent Tool")
    logger.info("  - Pain Analysis Agent Tool")
    logger.info("")
    
    # Environment-based configuration
    host = os.getenv("PHYSIO_AI_HOST", "0.0.0.0")
    port = int(os.getenv("PHYSIO_AI_PORT", "8000"))
    
    uvicorn.run(app, host=host, port=port)