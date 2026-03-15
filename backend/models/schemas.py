"""Pydantic v2 schemas mirroring the original TypeScript types."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- Browser action types ---
ActionType = Literal[
    "click", "type", "scroll", "navigate", "wait", "screenshot", "hover", "press"
]


class BrowserAction(BaseModel):
    type: ActionType
    selector: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    amount: Optional[int] = None
    delay: Optional[int] = None
    key: Optional[str] = None


class AgentDecision(BaseModel):
    action: BrowserAction
    reasoning: str
    confidence: float = 0.9


class Suggestion(BaseModel):
    text: str
    description: Optional[str] = None
    target: Optional[str] = None
    actionType: Optional[Literal["click", "scroll", "type", "navigate"]] = None


class ExecutionStep(BaseModel):
    stepNumber: int
    description: str
    action: BrowserAction
    screenshot: str = ""
    beforeScreenshot: str = ""
    reasoning: str
    result: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


TaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class TaskExecution(BaseModel):
    id: str
    taskDescription: str
    status: TaskStatus
    steps: list[ExecutionStep] = Field(default_factory=list)
    currentScreenshot: str = ""
    error: Optional[str] = None
    finalAnswer: Optional[str] = None  # agent's final answer/summary when task completes
    suggestions: Optional[list[Suggestion]] = None
    startUrl: Optional[str] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)


class GeminiResponse(BaseModel):
    decisions: list[AgentDecision]
    summary: str
    taskComplete: bool
    nextSteps: Optional[list[str]] = None


class WebsiteAnalysis(BaseModel):
    url: str
    screenshot: str
    analysis: str
    interactiveElements: list[str] = Field(default_factory=list)
    detectedText: str = ""


# --- API request/response DTOs ---
class ExecuteRequest(BaseModel):
    taskDescription: str
    startUrl: str = ""


class ContinueRequest(BaseModel):
    instruction: str
    inputs: Optional[dict] = None  # e.g. {"email": "...", "password": "..."}
