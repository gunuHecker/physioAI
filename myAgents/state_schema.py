from typing import Dict, Any
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

class ConversationStage(Enum):
    """Enum for the complete conversation flow"""
    GREETING = "greeting"
    PAIN_ANALYSIS = "pain_analysis"
    CONSENT_QUIZ = "consent_quiz"
    ASSESSMENT_QUIZ = "assessment_quiz"
    CONSENT_EXERCISE = "consent_exercise"
    EXERCISE_GUIDANCE = "exercise_guidance"
    CLOSURE = "closure"

@dataclass
class ALIASessionState:
    """Simplified session state for ALIA physiotherapy agent"""
    
    # Core flow control
    conversation_stage: ConversationStage = ConversationStage.GREETING
    
    # Context for closure agent
    closure_reason: str = "Session completed successfully."
    
    # Basic tracking
    interaction_count: int = 0
    last_user_message: str = ""
    session_start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ADK state storage"""
        return {
            "conversation_stage": self.conversation_stage.value,
            "closure_reason": self.closure_reason,
            "interaction_count": self.interaction_count,
            "last_user_message": self.last_user_message,
            "session_start_time": self.session_start_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ALIASessionState':
        """Create from dictionary (from ADK state)"""
        valid_keys = {
            'conversation_stage', 'closure_reason', 'interaction_count', 
            'last_user_message', 'session_start_time'
        }
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        
        if 'conversation_stage' in filtered_data and isinstance(filtered_data['conversation_stage'], str):
            filtered_data['conversation_stage'] = ConversationStage(filtered_data['conversation_stage'])
        
        return cls(**filtered_data)
    
    def update_interaction(self, user_message: str = ""):
        """Update interaction tracking"""
        self.interaction_count += 1
        if user_message:
            self.last_user_message = user_message
    
    def transition_to_stage(self, new_stage: ConversationStage, reason: str = ""):
        """Transition to new conversation stage"""
        self.conversation_stage = new_stage
        if reason:
            self.closure_reason = reason
            
    # ADD THIS METHOD
    def get_summary(self) -> str:
        """Generate a simple session summary for logging."""
        return f"Stage: {self.conversation_stage.value} | Interactions: {self.interaction_count}"

class StateManager:
    """Simple helper class for managing ALIA session state"""
    
    @staticmethod
    def create_initial_state(user_id: str, session_id: str) -> ALIASessionState:
        """Create initial session state"""
        # The user_id and session_id are passed but not used in this simple state,
        # but the method signature matches what main.py expects.
        return ALIASessionState()
    
    @staticmethod
    def save_state_to_adk(callback_context, state: ALIASessionState):
        """Save state back to ADK context"""
        callback_context.state.update(state.to_dict())