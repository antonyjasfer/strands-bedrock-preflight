import sys
from pathlib import Path
PKG_ROOT = Path(__file__).resolve().parent.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

"""Unit tests for strands-bedrock-preflight package."""

from unittest.mock import MagicMock
import pytest
from strands_bedrock_preflight import (
    BedrockPreflightGuard,
    PreflightStatus,
    check_bedrock_availability,
)


def test_preflight_authorized_response():
    """Test preflight check when foundation model is fully AUTHORIZED."""
    mock_session = MagicMock()
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {
        "Arn": "arn:aws:iam::123456789012:user/test-dev",
        "Account": "123456789012",
    }
    mock_bedrock = MagicMock()
    mock_bedrock.get_foundation_model_availability.return_value = {
        "modelId": "amazon.nova-lite-v1:0",
        "authorizationStatus": "AUTHORIZED",
        "agreementAvailability": {"status": "AVAILABLE"},
        "quotas": {"tokensPerMinute": 100000, "requestsPerMinute": 1000},
    }

    def client_factory(service):
        if service == "sts":
            return mock_sts
        elif service == "bedrock":
            return mock_bedrock
        raise ValueError(service)

    mock_session.client.side_effect = client_factory

    guard = BedrockPreflightGuard(session=mock_session)
    status = guard.check_availability("amazon.nova-lite-v1:0")

    assert isinstance(status, PreflightStatus)
    assert status.is_authorized is True
    assert status.authorization_status == "AUTHORIZED"
    assert status.identity_arn == "arn:aws:iam::123456789012:user/test-dev"
    assert status.account_id == "123456789012"
    assert status.quota_tpm == 100000


def test_preflight_not_authorized_response():
    """Test preflight check when foundation model is NOT_AUTHORIZED (e.g. Case 178842133900178)."""
    mock_session = MagicMock()
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {
        "Arn": "arn:aws:iam::280769660832:user/ledgerguard-dev",
        "Account": "280769660832",
    }
    mock_bedrock = MagicMock()
    mock_bedrock.get_foundation_model_availability.return_value = {
        "modelId": "amazon.nova-lite-v1:0",
        "authorizationStatus": "NOT_AUTHORIZED",
        "agreementAvailability": {"status": "AVAILABLE"},
    }

    mock_session.client.side_effect = lambda s: mock_sts if s == "sts" else mock_bedrock

    guard = BedrockPreflightGuard(session=mock_session)
    status = guard.check_availability("amazon.nova-lite-v1:0")

    assert status.is_authorized is False
    assert status.authorization_status == "NOT_AUTHORIZED"
    assert "ledgerguard-dev" in status.identity_arn


def test_preflight_zero_quota_blocked():
    """Test preflight check detects 0 TPM / 0 RPM quota restrictions before runtime crash."""
    mock_session = MagicMock()
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {
        "Arn": "arn:aws:iam::280769660832:user/ledgerguard-dev",
        "Account": "280769660832",
    }
    mock_bedrock = MagicMock()
    mock_bedrock.get_foundation_model_availability.return_value = {
        "modelId": "amazon.nova-lite-v1:0",
        "authorizationStatus": "AUTHORIZED",
        "quotas": {"tokensPerMinute": 0, "requestsPerMinute": 0},
    }
    mock_session.client.side_effect = lambda s: mock_sts if s == "sts" else mock_bedrock

    guard = BedrockPreflightGuard(session=mock_session)
    status = guard.check_availability("amazon.nova-lite-v1:0")

    assert status.is_authorized is False
    assert status.authorization_status == "ZERO_QUOTA_RESTRICTED"
    assert status.quota_tpm == 0
    assert status.quota_rpm == 0


def test_execute_resilient_triggers_fallback_on_unauthorized():
    """Test that execute_resilient automatically routes to fallback when unauthorized."""
    mock_session = MagicMock()
    mock_bedrock = MagicMock()
    mock_bedrock.get_foundation_model_availability.return_value = {
        "authorizationStatus": "NOT_AUTHORIZED",
    }
    mock_session.client.return_value = mock_bedrock

    guard = BedrockPreflightGuard(session=mock_session)

    mock_primary_agent = MagicMock()
    fallback_called = []

    def mock_fallback(prompt: str):
        fallback_called.append(prompt)
        return {"active_engine": "deterministic_fallback", "output": "Fallback succeeded."}

    result = guard.execute_resilient(
        prompt="Verify invoice INV-001",
        primary_agent=mock_primary_agent,
        fallback_handler=mock_fallback,
    )

    # Primary agent should NOT be called to avoid runtime crash
    mock_primary_agent.assert_not_called()
    assert len(fallback_called) == 1
    assert result["active_engine"] == "deterministic_fallback"


def test_execute_resilient_triggers_fallback_on_zero_quota():
    """Test that execute_resilient routes to fallback when 0 TPM quota is detected."""
    mock_session = MagicMock()
    mock_bedrock = MagicMock()
    mock_bedrock.get_foundation_model_availability.return_value = {
        "authorizationStatus": "AUTHORIZED",
        "quotas": {"tokensPerMinute": 0, "requestsPerMinute": 0},
    }
    mock_session.client.return_value = mock_bedrock

    guard = BedrockPreflightGuard(session=mock_session)

    mock_primary_agent = MagicMock()
    fallback_called = []

    def mock_fallback(prompt: str):
        fallback_called.append(prompt)
        return {"active_engine": "gemini_fallback", "output": "Verified via Gemini."}

    result = guard.execute_resilient(
        prompt="Verify invoice INV-002",
        primary_agent=mock_primary_agent,
        fallback_handler=mock_fallback,
    )

    mock_primary_agent.assert_not_called()
    assert len(fallback_called) == 1
    assert result["active_engine"] == "gemini_fallback"
