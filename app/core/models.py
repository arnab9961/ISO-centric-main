from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ISOStandard(str, Enum):
    ISO_9001_2015 = "ISO 9001:2015"
    ISO_27001_2022 = "ISO 27001:2022"
    ISO_14001_2015 = "ISO 14001:2015"
    ISO_45001_2018 = "ISO 45001:2018"
    ISO_22301_2019 = "ISO 22301:2019"
    ISO_50001_2018 = "ISO 50001:2018"


class AuditMaterialType(str, Enum):
    AUDIT_CHARTER = "Audit Charter"
    CHECKLIST = "Audit Checklist"
    QUESTIONNAIRE = "Pre-audit Questionnaire"
    FINDINGS_REPORT = "Non-Conformance Report"
    CORRECTIVE_ACTION = "Corrective Action Plan"


class NavigatorOutputType(str, Enum):
    POLICY = "Policy Document"
    SOP = "Standard Operating Procedure"
    RISK_REGISTER = "Risk Register"
    TRAINING_QUIZ = "Training Quiz"
    PROCEDURE = "Work Procedure"
    MANUAL = "Quality Manual"


class ComplianceStatus(str, Enum):
    CONFORMING = "Conforming"
    MINOR_GAP = "Minor Gap"
    MAJOR_GAP = "Major Gap"
    NON_CONFORMING = "Non-Conforming"


class PriorityLevel(str, Enum):
    HIGH = "High Priority"
    MEDIUM = "Medium Priority"
    LOW = "Low Priority"


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class NavigatorRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    organization_context: Optional[str] = Field(
        None,
        description="Organization description (e.g., 'Acme Corp, specializing in digital solutions with 50+ employees...')",
        max_length=5000,
    )
    output_type: Optional[str] = Field(
        None,
        description="Type of document to generate (e.g., Policy Document, SOP, Risk Register, or any custom value)",
    )
    specific_requirements: Optional[str] = Field(None, max_length=2000)
    tone: Optional[str] = Field("professional", description="Document tone (professional, formal, technical)")
    language: Optional[str] = Field("English", description="Output language")


class AuditLensRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    stage: Optional[str] = None
    material_type: Optional[AuditMaterialType] = None
    previous_audit_findings: Optional[Dict[str, Any]] = Field(None)
    scope_description: Optional[str] = Field(None, max_length=2000)


class BenchmarkRequest(BaseModel):
    document_text: Optional[str] = Field(
        None,
        description="Text content from document. Optional if binary content is processed.",
        max_length=50000,
    )
    improvement_goal: Optional[str] = Field(None, max_length=1000)
    target_standard: Optional[str] = Field("ISO 9001:2015", description="Target ISO standard to evaluate against")
    document_type: Optional[str] = Field("Unknown", description="Type of document (Policy, Procedure, Record, etc.)")
    department: Optional[str] = None


class ChatMessage(BaseModel):
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    context: Optional[Dict[str, Any]] = None
    iso_standard: Optional[ISOStandard] = Field(
        None,
        description="Optional ISO standard to focus the conversation on (e.g. ISO 9001:2015).",
    )
    session_id: Optional[str] = Field(
        None,
        description="Session ID for multi-turn memory. Returned on first call; pass it back to continue the conversation.",
    )


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class GeneratedDocument(BaseModel):
    title: str
    content: str
    metadata: Dict[str, Any]
    iso_clauses_referenced: List[str]
    generation_timestamp: str
    word_count: int
    confidence_score: float = Field(ge=0, le=1)


class AuditMaterial(BaseModel):
    stage: str
    material_type: str
    content: str
    iso_clauses_covered: List[str]
    next_steps: List[str]
    estimated_duration: str
    required_resources: List[str]
    generation_timestamp: str


class ClauseCompliance(BaseModel):
    clause_number: str
    clause_title: str
    status: ComplianceStatus
    compliance_percentage: int = Field(ge=0, le=100)
    evidence_found: str
    gap_description: Optional[str] = None
    recommendation: Optional[str] = None


class IdentifiedGap(BaseModel):
    priority: PriorityLevel
    clause_reference: str
    gap_title: str
    gap_description: str
    risk_level: str
    iso_requirement: str


class Recommendation(BaseModel):
    priority: PriorityLevel
    clause_reference: str
    title: str
    description: str
    benefit_statement: str
    effort_level: str
    estimated_timeline: str


class BenchmarkAnalysisResponse(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    grade: str
    compliance_percentage: int = Field(ge=0, le=100)
    effectiveness_percentage: int = Field(ge=0, le=100)
    document_type_detected: str
    standard_analyzed: str
    clause_compliance: List[ClauseCompliance]
    strengths: List[str]
    identified_gaps: List[IdentifiedGap]
    recommendations: List[Recommendation]
    analysis_timestamp: str
    analysis_id: str
    word_count_analyzed: int
    conversation_id: str


class ChatResponse(BaseModel):
    response: str
    sources: List[str]
    suggested_followups: List[str]
    session_id: str = Field(
        ...,
        description="Pass this back in subsequent requests to continue the conversation.",
    )


# ---------------------------------------------------------------------------
# RAG Models
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    text_content: Optional[str] = Field(None, max_length=100000)
    metadata: Optional[Dict[str, Any]] = None


class IngestResponse(BaseModel):
    success: bool
    document_id: Optional[str] = None
    chunks_created: int
    filename: str
    error: Optional[str] = None


class DocumentChunk(BaseModel):
    text: str
    metadata: Dict[str, Any]
    similarity_score: float = Field(ge=0, le=1)


# ---------------------------------------------------------------------------
# Quiz Models
# ---------------------------------------------------------------------------

class QuizRequest(BaseModel):
    context: Dict[str, Any] = Field(
        ...,
        description="JSON object containing the topic, subject matter, or any structured content to generate quiz questions from.",
    )
    num_questions: Optional[int] = Field(5, ge=1, le=20, description="Number of questions to generate (1–20).")
    difficulty: Optional[str] = Field(
        "intermediate",
        description="Difficulty level: 'easy', 'intermediate', or 'hard'.",
    )


class QuizQuestion(BaseModel):
    question: str = Field(..., description="The quiz question text.")
    options: Dict[str, str] = Field(
        ...,
        description="Answer options keyed A–D, e.g. {'A': '...', 'B': '...', 'C': '...', 'D': '...'}.",
    )
    correct_answer: str = Field(..., description="The key of the correct option ('A', 'B', 'C', or 'D').")
    hint: str = Field(..., description="A cryptic, high-level hint that points to an obscure clause nuance.")
    explanation: Optional[str] = Field(None, description="Brief explanation of why the answer is correct.")


class QuizResponse(BaseModel):
    quiz_title: str
    iso_standard: Optional[str]
    total_questions: int
    difficulty: str
    questions: List[QuizQuestion]
    generated_at: str


class FlashcardRequest(BaseModel):
    context: Dict[str, Any] = Field(
        ...,
        description="JSON object containing the topic, subject matter, or any structured content to generate flashcards from.",
    )
    num_cards: Optional[int] = Field(8, ge=1, le=30, description="Number of flashcards to generate (1–30).")
    difficulty: Optional[str] = Field(
        "intermediate",
        description="Difficulty level: 'easy', 'intermediate', or 'hard'.",
    )


class FlashcardFace(BaseModel):
    title: str = Field(..., description="Short label for the card face.")
    body: str = Field(..., description="Primary content for the card face.")


class Flashcard(BaseModel):
    front: FlashcardFace
    back: FlashcardFace


class FlashcardResponse(BaseModel):
    deck_title: str
    iso_standard: Optional[str]
    total_cards: int
    difficulty: str
    cards: List[Flashcard]
    generated_at: str


class QuizFeedbackRequest(BaseModel):
    context: Dict[str, Any] = Field(..., description="Context of the quiz.")
    results: List[Dict[str, Any]] = Field(
        ...,
        description="List of results, each containing 'question', 'selected_answer', and 'correct_answer'.",
    )


class CompetencyLevel(BaseModel):
    code: str
    title: str
    summary: str


class AnalyticalFeedback(BaseModel):
    strengths: List[str]
    weaknesses: List[str]
    critical_focus_clauses: List[str]


class RiskAssessment(BaseModel):
    risk_level: str
    impact_description: str
    mitigation_recommendation: str


class LearningRoadmapItem(BaseModel):
    area: str
    priority: str
    resources: List[str]
    action_item: str


class QuizFeedbackResponse(BaseModel):
    overall_score: str
    competency_level: CompetencyLevel
    analytical_feedback: AnalyticalFeedback
    risk_assessment: RiskAssessment
    learning_roadmap: List[LearningRoadmapItem]
    mentor_closing_note: str


# ---------------------------------------------------------------------------
# Discovery Models (Steps 1 & 2)
# ---------------------------------------------------------------------------

class OrgContextRequest(BaseModel):
    text: Optional[str] = Field(None, description="Raw text describing the organization.")
    url: Optional[str] = Field(None, description="URL of the organization's website to scrape.")


class OrgDescriptionOption(BaseModel):
    what: str = Field(..., description="What the organization does")
    where: str = Field(..., description="Where it operates")
    why: str = Field(..., description="Why it exists (mission/vision)")
    when: str = Field(..., description="When it was established or timeline context")
    whom: str = Field(..., description="Whom it serves (target audience/customers)")


class OrgContextResponse(BaseModel):
    options: List[OrgDescriptionOption]


class IsoSuggestionRequest(BaseModel):
    category: Optional[str] = Field(
        None,
        description="Category or industry (e.g., 'security', 'quality', 'automotive')",
    )


class AdvancedIsoSuggestionRequest(BaseModel):
    industry: str = Field(..., description="Industry of the organization")
    management_level: str = Field(..., description="Management level (e.g., 'C-level', 'Middle Management')")
    department: str = Field(..., description="Department of the user (e.g., 'IT', 'HR', 'Operations')")


class IsoSuggestionOption(BaseModel):
    standard: str = Field(..., description="ISO standard code (e.g., 'ISO 27001:2022')")
    title: str = Field(..., description="Full title of the standard")
    relevance: str = Field(..., description="Why this standard is relevant to the requested category")
    documents: List[dict] = Field(default_factory=list, description="List of recommended documents with title, clause, and type='document'")
    records: List[dict] = Field(default_factory=list, description="List of recommended records with title, clause, and type='record'")
    improvements: List[str] = Field(default_factory=list, description="5 suggestions on what can be done to improve based on context to align with the standard")


class IsoSuggestionResponse(BaseModel):
    suggestions: List[IsoSuggestionOption]


# ---------------------------------------------------------------------------
# Audit Lens Models (Phase 1 & 2)
# ---------------------------------------------------------------------------

class AuditContextOption(BaseModel):
    scope: str = Field(..., description="The physical and virtual boundaries of the audit.")
    criteria: str = Field(..., description="The specific ISO Standard required (e.g., ISO 9001, 27001).")
    objective: str = Field(..., description="What the audit aims to achieve.")


class AuditContextResponse(BaseModel):
    options: List[AuditContextOption]


class AuditLensStepRequest(BaseModel):
    locked_context: AuditContextOption
    step_number: int = Field(..., ge=1, le=13)


class AuditLensStepResponse(BaseModel):
    step_number: int
    title: str
    stage: str  # Plan, Do, Check, Act
    guidance: str = Field(..., description="Educational instructions (AI Guidance).")
    template_preview: str = Field(..., description="Customized, realistic example of the work paper.")
    next_step_available: bool


# ---------------------------------------------------------------------------
# Followup Question Models
# ---------------------------------------------------------------------------

class FollowupQuestionRequest(BaseModel):
    context: Dict[str, Any] = Field(
        ...,
        description="JSON object containing the context for which a followup question is needed.",
    )
    num_questions: int = Field(1, ge=1, le=20, description="Number of followup questions to generate.")


class FollowupQuestionResponse(BaseModel):
    questions: List[str]
    generated_at: str
