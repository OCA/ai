# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActionStep(BaseModel):
    step_id: int = Field(
        ..., description="Sequential unique identifier for the action step (e.g. 1, 2)"
    )
    objective: str = Field(
        ..., description="Clear and concise objective statement for this step"
    )
    target_type: Literal["tool", "agent"] = Field(
        ...,
        description="Indicates if the target is a direct tool or a delegated sub-agent",
    )
    target_name: str = Field(
        ..., description="Name of the tool (ai.tool) or sub-agent (ai.agent) target"
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Input execution parameters for the tool or sub-agent",
    )
    depends_on: list[int] = Field(
        default_factory=list,
        description="List of step_ids required before executing this step",
    )


class ActionPlanPayload(BaseModel):
    plan_version: str = Field(
        default="1.0", description="Specification version of the action plan schema"
    )
    summary: str = Field(
        ..., description="Global summary of the proposed multi-step action plan"
    )
    steps: list[ActionStep] = Field(
        ..., description="Ordered list of action steps to execute"
    )
