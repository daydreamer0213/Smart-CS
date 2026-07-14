"""Validated request and response types for the CRM sales assistant."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class LeadCreatePayload(BaseModel):
    company: str = Field(..., min_length=2, max_length=200)
    contact_name: str = Field(..., min_length=2, max_length=100)
    contact_email: EmailStr
    source: Literal["website", "referral", "event", "manual"]
    owner_user_id: str | None = Field(None, max_length=36)


class LeadUpdatePayload(BaseModel):
    lead_id: str = Field(..., min_length=1, max_length=36)
    stage: Literal["new", "qualified", "contacted", "disqualified"] | None = None
    owner_user_id: str | None = Field(None, max_length=36)

    @model_validator(mode="after")
    def has_change(self):
        if self.stage is None and self.owner_user_id is None:
            raise ValueError("stage or owner_user_id is required")
        return self


class TaskCreatePayload(BaseModel):
    related_type: Literal["customer", "lead", "opportunity"]
    related_id: str = Field(..., min_length=1, max_length=36)
    title: str = Field(..., min_length=2, max_length=200)
    due_date: date
    assignee_user_id: str | None = Field(None, max_length=36)


class CreateLeadCommand(BaseModel):
    action: Literal["create_lead"]
    payload: LeadCreatePayload


class UpdateLeadCommand(BaseModel):
    action: Literal["update_lead"]
    payload: LeadUpdatePayload


class CreateTaskCommand(BaseModel):
    action: Literal["create_follow_up_task"]
    payload: TaskCreatePayload


BusinessCommand = Annotated[
    CreateLeadCommand | UpdateLeadCommand | CreateTaskCommand,
    Field(discriminator="action"),
]


class BusinessChatRequest(BaseModel):
    session_id: str = Field("", max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)
    customer_id: str | None = Field(None, max_length=36)
    command: BusinessCommand | None = None


class DraftResponse(BaseModel):
    id: str
    action: str
    summary: str
    status: str
    expires_at: datetime


class BusinessChatResponse(BaseModel):
    reply: str
    customers: list[dict] = []
    customer_overview: dict | None = None
    pending_action: DraftResponse | None = None


class ConfirmResponse(BaseModel):
    status: Literal["success"]
    replayed: bool = False
    action: str
    result: dict
    audit_id: str
