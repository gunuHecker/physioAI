from typing import Dict, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

class ConversationStage(Enum):
    """Enum for conversation stages"""
    GREETING = "greeting"
    PAIN_ANALYSIS = "pain_analysis"
    CONSENT = "consent"
    ASSESSMENT = "assessment"
    CLOSURE = "closure"

@dataclass
class ALIASessionState:
    """Simplified session state for ALIA physiotherapy agent"""
    
    # Core flow control
    conversation_stage: ConversationStage = ConversationStage.GREETING
    next_agent: ConversationStage = ConversationStage.GREETING
    
    # Basic tracking
    interaction_count: int = 0
    last_user_message: str = ""
    session_start_time: str = None
    
    def __post_init__(self):
        """Initialize default values after creation"""
        if self.session_start_time is None:
            self.session_start_time = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ADK state storage"""
        return {
            "conversation_stage": self.conversation_stage.value,
            "next_agent": self.next_agent.value,
            "interaction_count": self.interaction_count,
            "last_user_message": self.last_user_message,
            "session_start_time": self.session_start_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ALIASessionState':
        """Create from dictionary (from ADK state)"""
        # Filter out keys that aren't part of our dataclass
        valid_keys = {
            'conversation_stage', 'next_agent', 'interaction_count', 
            'last_user_message', 'session_start_time'
        }
        
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        
        # Convert enum strings back to enums
        if 'conversation_stage' in filtered_data and isinstance(filtered_data['conversation_stage'], str):
            filtered_data['conversation_stage'] = ConversationStage(filtered_data['conversation_stage'])
        
        if 'next_agent' in filtered_data and isinstance(filtered_data['next_agent'], str):
            filtered_data['next_agent'] = ConversationStage(filtered_data['next_agent'])
        
        return cls(**filtered_data)
    
    def update_interaction(self, user_message: str = ""):
        """Update interaction tracking"""
        self.interaction_count += 1
        if user_message:
            self.last_user_message = user_message
    
    def transition_to_stage(self, new_stage: ConversationStage):
        """Transition to new conversation stage"""
        self.conversation_stage = new_stage
        self.next_agent = new_stage
    
    def get_summary(self) -> str:
        """Generate a simple session summary"""
        return f"Stage: {self.conversation_stage.value} | Interactions: {self.interaction_count}"

class StateManager:
    """Simple helper class for managing ALIA session state"""
    
    @staticmethod
    def create_initial_state(user_id: str, session_id: str) -> ALIASessionState:
        """Create initial session state"""
        return ALIASessionState()
    
    @staticmethod
    def save_state_to_adk(callback_context, state: ALIASessionState):
        """Save state back to ADK context"""
        callback_context.state.update(state.to_dict())