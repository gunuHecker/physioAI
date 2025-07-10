from typing import Dict, List, Optional, Union, Any
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime
import json

class ConversationStage(Enum):
    """Enum for conversation stages"""
    GREETING = "greeting"
    PAIN_ANALYSIS = "pain_analysis"
    CONSENT = "consent"
    ASSESSMENT = "assessment"
    CLOSURE = "closure"

class PainType(Enum):
    """Enum for pain classification"""
    LOWER_BACK = "lower_back"
    OTHER = "other"
    UNKNOWN = "unknown"

class ExitReason(Enum):
    """Enum for session exit reasons"""
    COMPLETED = "completed"
    NON_BACK_PAIN = "non_back_pain"
    NO_CONSENT = "no_consent"
    USER_EXIT = "user_exit"
    ERROR = "error"
    TIMEOUT = "timeout"

@dataclass
class AssessmentData:
    """Structure for assessment information"""
    questions_asked: List[str]
    responses: Dict[str, str]
    pain_intensity: Optional[int]  # 1-10 scale
    movement_limitations: List[str]
    daily_impact: Dict[str, str]
    previous_treatments: List[str]
    symptoms: List[str]
    assessment_score: Optional[float]
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AssessmentData':
        return cls(**data)

@dataclass
class ALIASessionState:
    """Complete session state for ALIA physiotherapy agent"""
    
    # Flow Control
    conversation_stage: ConversationStage = ConversationStage.GREETING
    next_agent: ConversationStage = ConversationStage.GREETING
    
    # Pain Analysis Results
    pain_type: PainType = PainType.UNKNOWN
    pain_description: str = ""
    pain_confidence_score: float = 0.0  # 0.0-1.0
    
    # Consent Management
    assessment_consent: Optional[bool] = None
    consent_attempts: int = 0
    consent_explanation_given: bool = False
    
    # Assessment Data
    assessment_data: Optional[AssessmentData] = None
    assessment_progress: float = 0.0  # 0.0-1.0
    current_assessment_question: int = 0
    
    # Exit Strategy
    exit_reason: Optional[ExitReason] = None
    session_complete: bool = False
    
    # Conversation History
    interaction_count: int = 0
    last_user_message: str = ""
    last_agent_response: str = ""
    conversation_summary: str = ""
    
    # Error Handling
    error_count: int = 0
    last_error: str = ""
    recovery_attempts: int = 0
    
    # Timestamps
    session_start_time: Optional[str] = None
    last_interaction_time: Optional[str] = None
    session_end_time: Optional[str] = None
    
    # User Context
    user_preferences: Dict[str, Any] = None
    interaction_mode: str = "text"  # "text" or "audio"
    
    def __post_init__(self):
        """Initialize default values after creation"""
        if self.assessment_data is None:
            self.assessment_data = AssessmentData(
                questions_asked=[],
                responses={},
                pain_intensity=None,
                movement_limitations=[],
                daily_impact={},
                previous_treatments=[],
                symptoms=[],
                assessment_score=None,
                recommendations=[]
            )
        
        if self.user_preferences is None:
            self.user_preferences = {}
            
        if self.session_start_time is None:
            self.session_start_time = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ADK state storage"""
        result = {}
        for key, value in asdict(self).items():
            if isinstance(value, Enum):
                result[key] = value.value
            elif isinstance(value, AssessmentData):
                result[key] = value.to_dict() if value else None
            else:
                result[key] = value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ALIASessionState':
        """Create from dictionary (from ADK state)"""
        # Convert enum strings back to enums
        if 'conversation_stage' in data and isinstance(data['conversation_stage'], str):
            data['conversation_stage'] = ConversationStage(data['conversation_stage'])
        
        if 'next_agent' in data and isinstance(data['next_agent'], str):
            data['next_agent'] = ConversationStage(data['next_agent'])
            
        if 'pain_type' in data and isinstance(data['pain_type'], str):
            data['pain_type'] = PainType(data['pain_type'])
            
        if 'exit_reason' in data and isinstance(data['exit_reason'], str):
            data['exit_reason'] = ExitReason(data['exit_reason'])
        
        # Convert assessment data
        if 'assessment_data' in data and data['assessment_data']:
            data['assessment_data'] = AssessmentData.from_dict(data['assessment_data'])
        
        return cls(**data)
    
    def update_interaction(self, user_message: str = "", agent_response: str = ""):
        """Update interaction tracking"""
        self.interaction_count += 1
        self.last_interaction_time = datetime.now().isoformat()
        
        if user_message:
            self.last_user_message = user_message
        if agent_response:
            self.last_agent_response = agent_response
    
    def transition_to_stage(self, new_stage: ConversationStage, next_agent: ConversationStage = None):
        """Safely transition to new conversation stage"""
        self.conversation_stage = new_stage
        self.next_agent = next_agent or new_stage
        self.last_interaction_time = datetime.now().isoformat()
    
    def complete_session(self, exit_reason: ExitReason):
        """Mark session as complete"""
        self.session_complete = True
        self.exit_reason = exit_reason
        self.session_end_time = datetime.now().isoformat()
    
    def record_error(self, error_message: str):
        """Record an error occurrence"""
        self.error_count += 1
        self.last_error = error_message
        self.last_interaction_time = datetime.now().isoformat()
    
    def attempt_recovery(self):
        """Record a recovery attempt"""
        self.recovery_attempts += 1
        self.last_interaction_time = datetime.now().isoformat()
    
    def set_pain_analysis_result(self, pain_type: PainType, description: str, confidence: float):
        """Update pain analysis results"""
        self.pain_type = pain_type
        self.pain_description = description
        self.pain_confidence_score = confidence
    
    def set_consent_result(self, consent: bool, explanation_given: bool = False):
        """Update consent status"""
        self.assessment_consent = consent
        self.consent_attempts += 1
        self.consent_explanation_given = explanation_given
    
    def add_assessment_response(self, question: str, response: str):
        """Add an assessment question and response"""
        if self.assessment_data:
            self.assessment_data.questions_asked.append(question)
            self.assessment_data.responses[question] = response
            
            # Update progress
            total_questions = 10  # Configurable
            self.assessment_progress = len(self.assessment_data.questions_asked) / total_questions
    
    def is_valid_transition(self, target_stage: ConversationStage) -> bool:
        """Validate if transition to target stage is allowed"""
        current = self.conversation_stage
        
        # Define valid transitions
        valid_transitions = {
            ConversationStage.GREETING: [ConversationStage.PAIN_ANALYSIS, ConversationStage.CLOSURE],
            ConversationStage.PAIN_ANALYSIS: [ConversationStage.CONSENT, ConversationStage.CLOSURE],
            ConversationStage.CONSENT: [ConversationStage.ASSESSMENT, ConversationStage.CLOSURE],
            ConversationStage.ASSESSMENT: [ConversationStage.CLOSURE],
            ConversationStage.CLOSURE: []  # Terminal state
        }
        
        return target_stage in valid_transitions.get(current, [])
    
    def should_continue_session(self) -> bool:
        """Check if session should continue"""
        if self.session_complete:
            return False
        
        if self.exit_reason:
            return False
            
        if self.error_count > 5:  # Too many errors
            return False
            
        if self.conversation_stage == ConversationStage.CLOSURE:
            return False
            
        return True
    
    def get_summary(self) -> str:
        """Generate a session summary"""
        summary_parts = [
            f"Stage: {self.conversation_stage.value}",
            f"Interactions: {self.interaction_count}",
            f"Pain Type: {self.pain_type.value}",
        ]
        
        if self.assessment_consent is not None:
            summary_parts.append(f"Consent: {self.assessment_consent}")
        
        if self.assessment_progress > 0:
            summary_parts.append(f"Assessment Progress: {self.assessment_progress:.1%}")
        
        if self.exit_reason:
            summary_parts.append(f"Exit Reason: {self.exit_reason.value}")
        
        return " | ".join(summary_parts)

class StateManager:
    """Helper class for managing ALIA session state"""
    
    @staticmethod
    def create_initial_state(user_id: str, session_id: str, interaction_mode: str = "text") -> ALIASessionState:
        """Create initial session state"""
        state = ALIASessionState()
        state.interaction_mode = interaction_mode
        state.user_preferences = {
            "user_id": user_id,
            "session_id": session_id,
            "language": "en",
            "timezone": "UTC"
        }
        return state
    
    @staticmethod
    def update_state_from_adk(callback_context, updates: Dict[str, Any]) -> ALIASessionState:
        """Update state from ADK callback context"""
        # Get current state from ADK
        current_state_dict = callback_context.state.to_dict()
        
        # Convert to our state object
        if current_state_dict:
            state = ALIASessionState.from_dict(current_state_dict)
        else:
            state = ALIASessionState()
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)
        
        # Update back to ADK context
        callback_context.state.update(state.to_dict())
        
        return state
    
    @staticmethod
    def save_state_to_adk(callback_context, state: ALIASessionState):
        """Save state back to ADK context"""
        callback_context.state.update(state.to_dict())
    
    @staticmethod
    def validate_state(state: ALIASessionState) -> List[str]:
        """Validate state consistency and return list of issues"""
        issues = []
        
        # Check stage consistency
        if state.conversation_stage == ConversationStage.ASSESSMENT and state.assessment_consent is False:
            issues.append("Cannot be in assessment stage without consent")
        
        # Check exit conditions
        if state.session_complete and not state.exit_reason:
            issues.append("Session marked complete but no exit reason provided")
        
        # Check confidence scores
        if not (0.0 <= state.pain_confidence_score <= 1.0):
            issues.append("Pain confidence score must be between 0.0 and 1.0")
        
        # Check assessment progress
        if not (0.0 <= state.assessment_progress <= 1.0):
            issues.append("Assessment progress must be between 0.0 and 1.0")
        
        return issues

# Constants for easy reference
ASSESSMENT_QUESTIONS = [
    "On a scale of 1-10, how would you rate your current pain level?",
    "When did this pain first start?",
    "What activities make your pain worse?",
    "What activities make your pain better?",
    "Do you experience any numbness or tingling?",
    "How does the pain affect your sleep?",
    "How does the pain affect your work or daily activities?",
    "Have you had any previous back injuries?",
    "What treatments have you tried for this pain?",
    "Is the pain constant or does it come and go?"
]

PAIN_KEYWORDS = {
    "lower_back": [
        "lower back", "lumbar", "tailbone", "sacrum", "pelvis", 
        "lower spine", "base of spine", "hip area", "buttocks"
    ],
    "other": [
        "neck", "shoulder", "upper back", "thoracic", "cervical",
        "leg", "knee", "ankle", "arm", "wrist", "head"
    ]
}