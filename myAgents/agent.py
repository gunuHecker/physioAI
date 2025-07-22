from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from typing import Optional

from .state_schema import (
    ALIASessionState, ConversationStage
)


# ============================================================================
# Callback functions to update state 
# ============================================================================


def _transition_state(callback_context: CallbackContext, new_stage: ConversationStage, reason: str = ""):
    """Helper function to update the state."""
    current_state = ALIASessionState.from_dict(callback_context.state.to_dict())
    current_state.transition_to_stage(new_stage, reason)
    callback_context.state.update(current_state.to_dict())
    print(f"[CALLBACK] Stage updated to: {current_state.conversation_stage.value}")


def after_greeting_model_callback(callback_context: CallbackContext, llm_response: LlmResponse) -> None:
    _transition_state(callback_context, ConversationStage.PAIN_ANALYSIS)

def after_pain_analysis_model_callback(callback_context: CallbackContext, llm_response: LlmResponse) -> None:
    # CORRECT: We now have direct access to llm_response
    agent_output = llm_response.content.parts[0].text.lower()
    if "category: other" in agent_output:
        reason = "User's pain is not related to the lower back."
        _transition_state(callback_context, ConversationStage.CLOSURE, reason)
    else:
        _transition_state(callback_context, ConversationStage.CONSENT_QUIZ)

def after_consent_quiz_model_callback(callback_context: CallbackContext, llm_response: LlmResponse) -> None:
    agent_output = llm_response.content.parts[0].text.lower()
    if "consent: no" in agent_output:
        reason = "User declined the assessment quiz."
        _transition_state(callback_context, ConversationStage.CLOSURE, reason)
    else:
        _transition_state(callback_context, ConversationStage.ASSESSMENT_QUIZ)

def after_assessment_quiz_model_callback(callback_context: CallbackContext, llm_response: LlmResponse) -> None:
    agent_output = llm_response.content.parts[0].text.lower()
    if "severity: extreme" in agent_output:
        reason = "User reported extreme pain and was advised to see a doctor."
        _transition_state(callback_context, ConversationStage.CLOSURE, reason)
    else:
        _transition_state(callback_context, ConversationStage.CONSENT_EXERCISE)

def after_consent_exercise_model_callback(callback_context: CallbackContext, llm_response: LlmResponse) -> None:
    agent_output = llm_response.content.parts[0].text.lower()
    if "consent: no" in agent_output:
        reason = "User declined the exercise session."
        _transition_state(callback_context, ConversationStage.CLOSURE, reason)
    else:
        _transition_state(callback_context, ConversationStage.EXERCISE_GUIDANCE)

# Exercise guidance does not need to parse output, so after_agent is fine
def after_exercise_guidance_callback(callback_context: CallbackContext) -> None:
    reason = "User successfully completed the exercise session."
    _transition_state(callback_context, ConversationStage.CLOSURE, reason)


# =============================================================================
# SPECIALIST AGENTS
# =============================================================================

# --- Stage 1: Greeting ---
greeting_agent = LlmAgent(
    name="greeting_agent", model="gemini-2.0-flash-exp",
    description="Greets the user and introduces the AI assistant.",
    instruction="Greet the user warmly, introduce yourself as ALIA, a physiotherapy assistant for lower back pain, and ask how you can help.",
    after_model_callback=after_greeting_model_callback
)

# --- Stage 2: Pain Analysis ---
pain_analysis_agent = LlmAgent(
    name="pain_analysis_agent", model="gemini-2.0-flash-exp",
    description="Analyzes the user's pain to determine if it is lower back pain.",
    instruction="""Your goal is to determine if the user's pain is in their LOWER BACK. Ask clarifying questions if needed.
- If it IS lower back pain, acknowledge it empathetically and end your response with 'CATEGORY: LBP'.
- If it is NOT lower back pain, politely explain you only specialize in lower back issues and end your response with 'CATEGORY: OTHER'.""",
    after_model_callback=after_pain_analysis_model_callback
)

# --- Stage 3: Consent for Quiz ---
consent_quiz_agent = LlmAgent(
    name="consent_quiz_agent", model="gemini-2.0-flash-exp",
    description="Asks the user for consent to begin an assessment quiz.",
    instruction="""Ask the user if they are ready to take a short assessment quiz to better understand their condition.
- If they agree, respond positively.
- If they decline, acknowledge their choice politely.
- End your response with 'CONSENT: YES' or 'CONSENT: NO' based on their answer.""",
    after_model_callback=after_consent_quiz_model_callback
)

# --- Stage 4: Assessment Quiz ---
assessment_quiz_agent = LlmAgent(
    name="assessment_quiz_agent", model="gemini-2.0-flash-exp",
    description="Conducts a short quiz to assess the user's pain symptoms.",
    instruction="""Ask the user a few questions: 1. Is the pain mild or extreme? 2. When did it start? 3. Does it radiate to other areas?
- If they say the pain is EXTREME, advise them to consult a doctor immediately and end your response with 'SEVERITY: EXTREME'.
- If the pain is mild, acknowledge their answers and end your response with 'SEVERITY: MILD'.""",
    after_model_callback=after_assessment_quiz_model_callback
)

# --- Stage 5: Consent for Exercise ---
consent_exercise_agent = LlmAgent(
    name="consent_exercise_agent", model="gemini-2.0-flash-exp",
    description="Asks the user for consent to start a guided exercise session via camera.",
    instruction="""Ask the user if they are ready to perform a simple guided exercise. Tell them they will need to turn on their camera for this.
- If they agree, respond positively.
- If they decline, acknowledge their choice politely.
- End your response with 'CONSENT: YES' or 'CONSENT: NO' based on their answer.""",
    after_model_callback=after_consent_exercise_model_callback
)

# --- Stage 6: Exercise Guidance ---
exercise_guidance_agent = LlmAgent(
    name="exercise_guidance_agent", model="gemini-2.0-flash-exp",
    description="Guides the user through a physiotherapy exercise using their camera feed.",
    instruction="""You are a physiotherapy coach. Guide the user through a lower back flexion exercise based on the incoming video frames.
Provide clear, step-by-step instructions. Be encouraging. Once the exercise seems complete, provide a concluding message.""",
    after_agent_callback=after_exercise_guidance_callback
)

# --- Stage 7: Closure ---
closure_agent = LlmAgent(
    name="closure_agent", model="gemini-2.0-flash-exp",
    description="Provides a concluding message to end the session gracefully.",
    instruction="""Provide a polite and empathetic closing message. The reason for the session ending is: {closure_reason}.
End the conversation gracefully. For example: 'Based on our chat, it seems your pain is not in your lower back. As I specialize in that area, I'm unable to proceed further. I wish you the best in finding the right care. Goodbye.'""",
)

# =============================================================================
# CONVERT AGENTS TO TOOLS
# =============================================================================

greeting_tool = AgentTool(agent=greeting_agent)
pain_analysis_tool = AgentTool(agent=pain_analysis_agent)
consent_quiz_tool = AgentTool(agent=consent_quiz_agent)
assessment_quiz_tool = AgentTool(agent=assessment_quiz_agent)
consent_exercise_tool = AgentTool(agent=consent_exercise_agent)
exercise_guidance_tool = AgentTool(agent=exercise_guidance_agent)
closure_tool = AgentTool(agent=closure_agent)

# =============================================================================
# ROOT LLM ORCHESTRATOR AGENT
# =============================================================================

root_agent = LlmAgent(
    name="ALIA_Orchestrator",
    model="gemini-2.0-flash-exp",
    description="ALIA - AI Lower-back Intelligence Assistant for physiotherapy assessment",
    instruction="""
    You are the master orchestrator for ALIA, a physiotherapy AI.
    Your ONLY job is to check the current conversation stage and call the correct specialist tool.
    You MUST NOT respond directly to the user. You MUST call one of the provided tools.

    Current conversation stage: {conversation_stage}

    - If stage is 'greeting', you MUST call the `greeting_agent` tool.
    - If stage is 'pain_analysis', you MUST call the `pain_analysis_agent` tool.
    - If stage is 'consent_quiz', you MUST call the `consent_quiz_agent` tool.
    - If stage is 'assessment_quiz', you MUST call the `assessment_quiz_agent` tool.
    - If stage is 'consent_exercise', you MUST call the `consent_exercise_agent` tool.
    - If stage is 'exercise_guidance', you MUST call the `exercise_guidance_agent` tool.
    - If stage is 'closure', you MUST call the `closure_agent` tool.
    """,
    tools=[
        greeting_tool,
        pain_analysis_tool,
        consent_quiz_tool,
        assessment_quiz_tool,
        consent_exercise_tool,
        exercise_guidance_tool,
        closure_tool
    ]
)

# root_agent = LlmAgent(
#     name="ALIA",
#     model="gemini-2.0-flash-exp",
#     description="ALIA - AI Lower-back Intelligence Assistant for physiotherapy assessment",
#     instruction="""
# You are ALIA (AI Lower-back Intelligence Assistant), a specialized physiotherapy agent.

# Your mission:
# 1. Help users with lower back pain through structured assessment
# 2. Provide professional, empathetic care
# 3. Guide users through a logical conversation flow
# 4. Respect user boundaries and choices

# Current conversation stage: {conversation_stage}
# Interaction count: {interaction_count}

# Based on the current stage, respond appropriately:
# - If GREETING stage: Use the greeting tool to properly introduce yourself
# - If PAIN_ANALYSIS stage: Use the pain analysis tool to determine if they have lower back pain
# - Otherwise: Provide helpful guidance about lower back pain

# You have access to specialized tools:
# - greeting_tool: For initial greetings and introductions
# - pain_analysis_tool: For analyzing pain location and type

# Always maintain a professional, caring, and knowledgeable demeanor.
# """,
#     tools=[greeting_tool, pain_analysis_tool],
#     output_key="alia_response"
# )