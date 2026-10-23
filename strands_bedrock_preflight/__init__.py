"""strands-bedrock-preflight: Resilient pre-flight guard and multi-provider fallback for Strands Agents SDK."""

from strands_bedrock_preflight.guard import (
    BedrockPreflightGuard,
    PreflightStatus,
    check_bedrock_availability,
)

__version__ = "0.1.0"
__all__ = [
    "BedrockPreflightGuard",
    "PreflightStatus",
    "check_bedrock_availability",
]
