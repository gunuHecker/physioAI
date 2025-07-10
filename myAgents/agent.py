from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse, LlmRequest
from google.genai import types
from typing import Optional
import re

from .state_schema import (
    ALIASessionState, StateManager, ConversationStage, 
    PainType, ExitReason, PAIN_KEYWORDS, ASSESSMENT_QUESTIONS
)

# =============================================================================
# CALLBACK FUNCTIONS
# =============================================================================
def route_to_appropriate_agent(callback_context: CallbackContext) -> Optional[types.Content]:
    """Route to the correct agent based on conversation state"""
    try:
        # Get current state
        state_dict = callback_context.state.to_dict()
        if state_dict:
            state = ALIASessionState.from_dict(state_dict)
        else:
            # Initialize new state
            user_id = callback_context.invocation_context.user_id
            session_id = callback_context.invocation_context.session_id
            state = StateManager.create_initial_state(user_id, session_id)
            StateManager.save_state_to_adk(callback_context, state)
        
        agent_name = callback_context.agent_name
        current_stage = state.conversation_stage
        next_agent_stage = state.next_agent
        
        print(f"\n🔀 [ROUTER] ===== AGENT ROUTING =====")
        print(f"🔀 [ROUTER] Current Agent: {agent_name}")
        print(f"🔀 [ROUTER] Current Stage: {current_stage.value}")
        print(f"🔀 [ROUTER] Next Agent Should Be: {next_agent_stage.value}_agent")
        print(f"🔀 [ROUTER] Session Complete: {state.session_complete}")
        print(f"🔀 [ROUTER] ================================\n")
        
        # Check if session should continue
        if not state.should_continue_session():
            print(f"❌ [ROUTER] Session should not continue: {state.exit_reason}")
            return types.Content(
                role="model",
                parts=[types.Part(text="Session completed.")]
            )
        
        # Route based on agent name and expected stage
        expected_agent = f"{next_agent_stage.value}_agent"
        
        if agent_name != expected_agent:
            print(f"⏭️  [ROUTER] SKIPPING {agent_name}, expected {expected_agent}")
            return types.Content(
                role="model",
                parts=[types.Part(text=f"Routing to {expected_agent}")]
            )
        
        print(f"✅ [ROUTER] ALLOWING {agent_name} to proceed")
        return None  # Allow agent to run
        
    except Exception as e:
        print(f"❌ [ROUTER ERROR] {str(e)}")
        return None

def update_state_after_agent(callback_context: CallbackContext) -> Optional[types.Content]:
    """Update state after agent execution"""
    try:
        agent_name = callback_context.agent_name
        
        # Get current state
        state_dict = callback_context.state.to_dict()
        state = ALIASessionState.from_dict(state_dict) if state_dict else ALIASessionState()
        
        # Update interaction count
        state.update_interaction()
        
        print(f"[STATE UPDATE] After {agent_name}: Stage={state.conversation_stage.value}")
        
        # Save updated state
        StateManager.save_state_to_adk(callback_context, state)
        
        return None
        
    except Exception as e:
        print(f"[STATE UPDATE ERROR] {str(e)}")
        return None

# =============================================================================
# SPECIALIZED CALLBACK FUNCTIONS
# =============================================================================

def greeting_completion_handler(callback_context: CallbackContext) -> Optional[types.Content]:
    """Handle completion of greeting stage"""
    print(f"\n🎉 [GREETING COMPLETE] ===== GREETING FINISHED =====")
    
    state_dict = callback_context.state.to_dict()
    state = ALIASessionState.from_dict(state_dict) if state_dict else ALIASessionState()
    
    # Transition to pain analysis
    state.transition_to_stage(ConversationStage.PAIN_ANALYSIS)
    
    StateManager.save_state_to_adk(callback_context, state)
    print(f"🎉 [GREETING COMPLETE] Transitioning to PAIN_ANALYSIS stage")
    print(f"🎉 [GREETING COMPLETE] ==============================\n")
    
    return None

def pain_analysis_completion_handler(callback_context: CallbackContext) -> Optional[types.Content]:
    """Handle completion of pain analysis stage"""
    print(f"\n🔍 [PAIN ANALYSIS COMPLETE] ===== PAIN ANALYSIS FINISHED =====")
    
    state_dict = callback_context.state.to_dict()
    state = ALIASessionState.from_dict(state_dict) if state_dict else ALIASessionState()
    
    # Analyze the last response for pain type
    last_message = state.last_user_message.lower()
    print(f"🔍 [PAIN ANALYSIS] Analyzing message: '{last_message}'")
    
    # Simple keyword-based classification
    lower_back_score = sum(1 for keyword in PAIN_KEYWORDS["lower_back"] if keyword in last_message)
    other_score = sum(1 for keyword in PAIN_KEYWORDS["other"] if keyword in last_message)
    
    print(f"🔍 [PAIN ANALYSIS] Lower back keywords found: {lower_back_score}")
    print(f"🔍 [PAIN ANALYSIS] Other keywords found: {other_score}")
    
    if lower_back_score > 0 and lower_back_score >= other_score:
        pain_type = PainType.LOWER_BACK
        confidence = min(0.8, 0.5 + (lower_back_score * 0.1))
        next_stage = ConversationStage.CONSENT
        print(f"✅ [PAIN ANALYSIS] DETECTED: Lower back pain (confidence: {confidence})")
        print(f"✅ [PAIN ANALYSIS] NEXT: Moving to CONSENT stage")
    elif other_score > 0:
        pain_type = PainType.OTHER
        confidence = 0.9
        next_stage = ConversationStage.CLOSURE
        state.exit_reason = ExitReason.NON_BACK_PAIN
        print(f"❌ [PAIN ANALYSIS] DETECTED: Other pain type (confidence: {confidence})")
        print(f"❌ [PAIN ANALYSIS] NEXT: Moving to CLOSURE stage")
    else:
        pain_type = PainType.UNKNOWN
        confidence = 0.0
        next_stage = ConversationStage.PAIN_ANALYSIS  # Ask for clarification
        print(f"❓ [PAIN ANALYSIS] DETECTED: Unknown pain type")
        print(f"❓ [PAIN ANALYSIS] NEXT: Staying in PAIN_ANALYSIS for clarification")
    
    state.set_pain_analysis_result(pain_type, last_message, confidence)
    state.transition_to_stage(state.conversation_stage, next_stage)
    
    StateManager.save_state_to_adk(callback_context, state)
    print(f"🔍 [PAIN ANALYSIS COMPLETE] ================================\n")
    
    return None

def consent_completion_handler(callback_context: CallbackContext) -> Optional[types.Content]:
    """Handle completion of consent stage"""
    state_dict = callback_context.state.to_dict()
    state = ALIASessionState.from_dict(state_dict) if state_dict else ALIASessionState()
    
    # Analyze consent response
    last_message = state.last_user_message.lower()
    
    # Simple consent detection
    positive_indicators = ["yes", "okay", "ok", "sure", "fine", "go ahead", "proceed"]
    negative_indicators = ["no", "not", "don't", "skip", "decline", "refuse"]
    
    positive_score = sum(1 for indicator in positive_indicators if indicator in last_message)
    negative_score = sum(1 for indicator in negative_indicators if indicator in last_message)
    
    if positive_score > negative_score:
        consent = True
        next_stage = ConversationStage.ASSESSMENT
    elif negative_score > 0:
        consent = False
        next_stage = ConversationStage.CLOSURE
        state.exit_reason = ExitReason.NO_CONSENT
    else:
        # Ambiguous response, try again
        consent = None
        next_stage = ConversationStage.CONSENT
    
    if consent is not None:
        state.set_consent_result(consent, True)
    
    state.transition_to_stage(state.conversation_stage, next_stage)
    
    StateManager.save_state_to_adk(callback_context, state)
    print(f"[CONSENT] Result: {consent}")
    
    return None

def assessment_progress_handler(callback_context: CallbackContext) -> Optional[types.Content]:
    """Handle assessment progress"""
    state_dict = callback_context.state.to_dict()
    state = ALIASessionState.from_dict(state_dict) if state_dict else ALIASessionState()
    
    # Track assessment progress
    if state.assessment_data and len(state.assessment_data.questions_asked) >= len(ASSESSMENT_QUESTIONS):
        # Assessment complete
        state.transition_to_stage(state.conversation_stage, ConversationStage.CLOSURE)
        state.exit_reason = ExitReason.COMPLETED
        print("[ASSESSMENT] Assessment completed")
    
    StateManager.save_state_to_adk(callback_context, state)
    return None

def inject_assessment_context(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
    """Inject assessment context into model request"""
    state_dict = callback_context.state.to_dict()
    state = ALIASessionState.from_dict(state_dict) if state_dict else ALIASessionState()
    
    if state.assessment_data:
        questions_asked = len(state.assessment_data.questions_asked)
        total_questions = len(ASSESSMENT_QUESTIONS)
        
        if questions_asked < total_questions:
            next_question = ASSESSMENT_QUESTIONS[questions_asked]
            
            context = f"""
ASSESSMENT PROGRESS: {questions_asked}/{total_questions} questions completed
NEXT QUESTION TO ASK: "{next_question}"

Previous responses: {state.assessment_data.responses}
"""
            
            # Append context to system instruction
            current_instruction = llm_request.config.system_instruction
            if current_instruction:
                enhanced_instruction = f"{current_instruction}\n\nASSESSMENT CONTEXT:\n{context}"
            else:
                enhanced_instruction = f"ASSESSMENT CONTEXT:\n{context}"
            
            llm_request.config.system_instruction = enhanced_instruction
    
    return None

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
    after_agent_callback=greeting_completion_handler
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
    after_agent_callback=pain_analysis_completion_handler
)

consent_agent = LlmAgent(
    name="consent_agent",
    model="gemini-2.0-flash-exp",
    description="Obtains user consent for physiotherapy assessment",
    instruction="""
You are ALIA's consent specialist. The user has lower back pain, and you need their consent for assessment.

Your task:
1. Explain what a physiotherapy assessment involves
2. Clarify the benefits of the assessment
3. Ask for their consent clearly and respectfully
4. Respect their decision completely

Assessment explanation:
"I'd like to conduct a quick physiotherapy assessment to better understand your lower back pain. This involves asking about:
- Your pain levels and characteristics
- Movement limitations and triggers
- How it affects your daily activities
- Previous treatments you've tried
- Current symptoms you're experiencing

This assessment helps me provide more targeted guidance for your condition."

Then ask: "Would you be comfortable proceeding with this assessment?"

Important:
- Be clear about what's involved
- Emphasize it's their choice
- Don't pressure them
- If they decline, respect their decision gracefully
""",
    after_agent_callback=consent_completion_handler
)

assessment_agent = LlmAgent(
    name="assessment_agent", 
    model="gemini-2.0-flash-exp",
    description="Conducts structured physiotherapy assessment for lower back pain",
    instruction="""
You are ALIA's assessment specialist. Conduct a thorough but comfortable physiotherapy assessment.

Assessment areas to cover:
1. Pain characteristics (intensity 1-10, location, duration, onset)
2. Pain triggers (activities that worsen pain)
3. Pain relief factors (what helps)
4. Movement limitations (bending, lifting, sitting, walking)
5. Daily activity impact (work, sleep, exercise)
6. Associated symptoms (numbness, tingling, weakness, radiating pain)
7. Previous injuries or treatments
8. Current medications or therapies
9. Sleep quality and pain patterns
10. Exercise and activity levels

Guidelines:
- Ask ONE question at a time
- Wait for their response before proceeding
- Be empathetic and understanding
- Use simple, non-medical language
- Show genuine interest in their answers
- Build rapport throughout the assessment

Example questions:
- "On a scale of 1-10, how would you rate your current pain level?"
- "When did this pain first start?"
- "What activities tend to make your pain worse?"

Keep questions conversational and supportive.
""",
    before_model_callback=inject_assessment_context,
    after_agent_callback=assessment_progress_handler
)

closure_agent = LlmAgent(
    name="closure_agent",
    model="gemini-2.0-flash-exp", 
    description="Provides appropriate session closure based on outcome",
    instruction="""
You are ALIA's closure specialist. Provide appropriate endings based on the session outcome.

Closure scenarios:

1. SUCCESSFUL COMPLETION (after full assessment):
   - Summarize key findings from the assessment
   - Provide initial recommendations
   - Suggest next steps (seeing a physiotherapist, exercises, etc.)
   - Offer encouragement and support

2. NON-LOWER BACK PAIN:
   - Acknowledge their pain condition empathetically
   - Explain your specialization in lower back issues
   - Suggest they consult appropriate healthcare professionals
   - Provide general wellness advice if appropriate

3. DECLINED ASSESSMENT:
   - Respect their decision completely
   - Offer alternative resources (general back pain info, exercises)
   - Encourage them to seek professional help if pain persists
   - Leave the door open for future assistance

4. USER EXIT:
   - Professional and understanding farewell
   - Brief summary of what was discussed
   - Encouragement to seek help when ready

Always:
- Be empathetic and supportive
- Provide value even in incomplete sessions
- Maintain professional boundaries
- End on a positive, encouraging note
- Thank them for their time
""",
    after_agent_callback=update_state_after_agent
)

# =============================================================================
# ROOT SEQUENTIAL AGENT
# =============================================================================

root_agent = SequentialAgent(
    name="ALIA",
    description="ALIA - AI Lower-back Intelligence Assistant for physiotherapy assessment",
    sub_agents=[
        greeting_agent,
        pain_analysis_agent, 
        consent_agent,
        assessment_agent,
        closure_agent
    ],
    before_agent_callback=route_to_appropriate_agent,
    after_agent_callback=update_state_after_agent
)