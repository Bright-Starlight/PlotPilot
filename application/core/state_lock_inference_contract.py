"""Structured contract for LLM-assisted state lock inference."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class AliasMappingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(default="", max_length=80)
    canonical_name: str = Field(default="", max_length=80)


class StateLockInferencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ending_target: str = Field(default="", max_length=120)
    alias_mappings: List[AliasMappingPayload] = Field(default_factory=list, max_length=20)
    inferred_items: List[str] = Field(default_factory=list, max_length=20)
    inferred_events: List[str] = Field(default_factory=list, max_length=20)
    notes: List[str] = Field(default_factory=list, max_length=8)
