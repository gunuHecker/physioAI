from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.agents.callback_context import CallbackContext
from typing import Optional

from .state_schema import (
    ALIASessionState, StateManager, ConversationStage
)


# ============================================================================
# Callback functions to update state 
# ============================================================================

def update_stage_after_greeting(callback_context: CallbackContext) -> Optional[object]:
    """After agent callback to update stage after greeting"""
    current_state = ALIASessionState.from_dict(callback_context.state.to_dict())
    
    print(f"[CALLBACK] Greeting agent completed. Current stage: {current_state.conversation_stage}")
    
    if current_state.conversation_stage == ConversationStage.GREETING:
        current_state.transition_to_stage(ConversationStage.PAIN_ANALYSIS)
        current_state.update_interaction()
        
        # Update the callback context state
        callback_context.state.update(current_state.to_dict())
        
        print(f"[CALLBACK] Stage updated to: {current_state.conversation_stage}")
    
    return None  # Don't override the agent's output

def update_stage_after_pain_analysis(callback_context: CallbackContext) -> Optional[object]:
    """After agent callback to update stage after pain analysis"""
    current_state = ALIASessionState.from_dict(callback_context.state.to_dict())
    
    print(f"[CALLBACK] Pain analysis agent completed. Current stage: {current_state.conversation_stage}")
    
    if current_state.conversation_stage == ConversationStage.PAIN_ANALYSIS:
        current_state.transition_to_stage(ConversationStage.CONSENT)
        current_state.update_interaction()
        
        # Update the callback context state
        callback_context.state.update(current_state.to_dict())
        
        print(f"[CALLBACK] Stage updated to: {current_state.conversation_stage}")
    
    return None # Don't override the agent's output


# =============================================================================
# INDIVIDUAL AGENTS
# =============================================================================

greeting_agent = LlmAgent(
    name="greeting_agent",
    model="gemini-2.0-flash-exp",
    description="ALIA's greeting and introduction agent",
    instruction="""
You are ALIA, a specialized physiotherapy assistant focused on lower back pain assessment and guidance.

Your role in this conversation:
1. Greet the user warmly and professionally
2. Introduce yourself as a physiotherapy assistant specializing in lower back pain
3. Ask how you can help them today
4. Keep your response concise and welcoming

Example response:
"Hi! I'm ALIA, your physiotherapy assistant specializing in lower back pain. I'm here to help assess your condition and provide guidance. How can I help you today?"

Important:
- Be empathetic and professional
- Keep the greeting brief but warm
- Focus on lower back pain specialty
- Ask an open-ended question about their needs
""",
    output_key="greeting_complete",
    after_agent_callback=update_stage_after_greeting
)

pain_analysis_agent = LlmAgent(
    name="pain_analysis_agent",
    model="gemini-2.0-flash-exp", 
    description="Analyzes user's pain description to determine if it's lower back related",
    instruction="""
You are ALIA's pain analysis specialist. Your task is to determine if the user has lower back pain.

Your responsibilities:
1. Carefully listen to the user's pain description
2. Ask clarifying questions about pain location if needed
3. Determine if this is specifically LOWER BACK pain
4. Be empathetic while gathering information

Lower back pain indicators:
- Lumbar region, lower spine, base of spine
- Between ribs and pelvis area
- Tailbone, sacrum, hip area, buttocks pain
- Pain when bending, lifting, sitting

NOT lower back pain:
- Neck, shoulder, upper back pain
- Leg, knee, ankle pain  
- Arm, wrist pain
- Headaches

If unclear, ask ONE specific question about pain location or characteristics.
If it's clearly NOT lower back pain, explain that you specialize in lower back issues.
If it IS lower back pain, acknowledge their condition empathetically.

Be concise and focused on pain location assessment.
""",
    output_key="pain_analysis_complete",
    after_agent_callback=update_stage_after_pain_analysis
)

# =============================================================================
# CONVERT AGENTS TO TOOLS
# =============================================================================

greeting_tool = AgentTool(
    agent=greeting_agent
)

pain_analysis_tool = AgentTool(
    agent=pain_analysis_agent
)

# =============================================================================
# ROOT LLM AGENT
# =============================================================================

root_agent = LlmAgent(
    name="ALIA",
    model="gemini-2.0-flash-exp",
    description="ALIA - AI Lower-back Intelligence Assistant for physiotherapy assessment",
    instruction="""
You are ALIA (AI Lower-back Intelligence Assistant), a specialized physiotherapy agent.

Your mission:
1. Help users with lower back pain through structured assessment
2. Provide professional, empathetic care
3. Guide users through a logical conversation flow
4. Respect user boundaries and choices

Current conversation stage: {conversation_stage}
Interaction count: {interaction_count}

Based on the current stage, respond appropriately:
- If GREETING stage: Use the greeting tool to properly introduce yourself
- If PAIN_ANALYSIS stage: Use the pain analysis tool to determine if they have lower back pain
- Otherwise: Provide helpful guidance about lower back pain

You have access to specialized tools:
- greeting_tool: For initial greetings and introductions
- pain_analysis_tool: For analyzing pain location and type

Always maintain a professional, caring, and knowledgeable demeanor.
""",
    tools=[greeting_tool, pain_analysis_tool],
    output_key="alia_response"
)