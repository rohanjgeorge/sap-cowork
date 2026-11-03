"""Versioned task behavior; application templates remain current editable files."""

import json
from pathlib import Path
from .models import Contract, ArtifactType


class ArtifactTaskProfile(Contract):
    artifact_type: ArtifactType
    version: str
    template_ref: str
    generation_instructions: str
    context_requirement_profile: str
    expected_output_contract: str
    validation_profile: str
    revision_behavior: str


def load_profile(artifact_type):
    profiles = json.loads((Path(__file__).resolve().parents[2] / "artifact_profiles/v1.json").read_text())
    return ArtifactTaskProfile.model_validate(profiles[str(artifact_type)])
