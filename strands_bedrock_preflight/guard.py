"""Core Preflight Guard and Resilient Multi-Provider Orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import boto3
from botocore.exceptions import ClientError
from strands import Agent
from strands.models.bedrock import BedrockModel

logger = logging.getLogger("strands_bedrock_preflight")


@dataclass
class PreflightStatus:
    """Pre-flight foundation model availability and identity verification status."""
    model_id: str
    region: str
    is_authorized: bool
    authorization_status: str
    identity_arn: str
    account_id: str
    agreement_status: str
    quota_tpm: int | None = None
    quota_rpm: int | None = None
    raw_response: dict[str, Any] = None


class BedrockPreflightGuard:
    """Detects Bedrock foundation model authorization and quota restrictions before runtime execution."""

    def __init__(
        self,
        session: boto3.Session | None = None,
        profile_name: str | None = None,
        region_name: str = "us-east-1",
    ) -> None:
        self.region_name = region_name
        self.profile_name = profile_name
        self._session = session

    def get_session(self) -> boto3.Session:
        """Resolve or construct boto3 Session."""
        if self._session is None:
            if self.profile_name:
                self._session = boto3.Session(
                    profile_name=self.profile_name,
                    region_name=self.region_name,
                )
            else:
                self._session = boto3.Session(region_name=self.region_name)
        return self._session

    def check_availability(self, model_id: str = "amazon.nova-lite-v1:0") -> PreflightStatus:
        """Call bedrock.get_foundation_model_availability to verify model authorization status and quotas."""
        session = self.get_session()
        identity_arn = "unknown"
        account_id = "unknown"

        # Check STS caller identity
        try:
            sts = session.client("sts")
            caller = sts.get_caller_identity()
            identity_arn = caller.get("Arn", "unknown")
            account_id = caller.get("Account", "unknown")
        except Exception as exc:
            logger.warning("STS identity check failed during preflight: %s", exc)

        # Check Bedrock foundation model availability
        bedrock = session.client("bedrock")
        try:
            resp = bedrock.get_foundation_model_availability(modelId=model_id)
            status = resp.get("authorizationStatus", "UNKNOWN")
            agreements = resp.get("agreementAvailability", {}).get("status", "UNKNOWN")
            
            # Quota inspection (detect 0 TPM / 0 RPM)
            quotas = resp.get("quotas", {}) or {}
            tpm = quotas.get("tokensPerMinute", None)
            rpm = quotas.get("requestsPerMinute", None)
            quota_blocked = (tpm == 0 or rpm == 0)

            is_auth = (status == "AUTHORIZED") and not quota_blocked
            effective_status = "ZERO_QUOTA_RESTRICTED" if quota_blocked else status

            return PreflightStatus(
                model_id=model_id,
                region=self.region_name,
                is_authorized=is_auth,
                authorization_status=effective_status,
                identity_arn=identity_arn,
                account_id=account_id,
                agreement_status=agreements,
                quota_tpm=tpm,
                quota_rpm=rpm,
                raw_response=resp,
            )
        except Exception as exc:
            logger.error("Bedrock preflight call failed: %s", exc)
            return PreflightStatus(
                model_id=model_id,
                region=self.region_name,
                is_authorized=False,
                authorization_status=f"ERROR: {exc}",
                identity_arn=identity_arn,
                account_id=account_id,
                agreement_status="ERROR",
                quota_tpm=0,
                quota_rpm=0,
                raw_response={"error": str(exc)},
            )

    def execute_resilient(
        self,
        prompt: str,
        primary_agent: Agent,
        fallback_handler: Callable[[str], dict[str, Any]],
        model_id: str = "amazon.nova-lite-v1:0",
    ) -> dict[str, Any]:
        """Execute agent with preflight validation and seamless multi-provider fallback."""
        status = self.check_availability(model_id=model_id)
        if not status.is_authorized:
            logger.info(
                "Model %s is %s. Bypassing primary to avoid runtime crash.",
                model_id,
                status.authorization_status,
            )
            return fallback_handler(prompt)

        try:
            resp = primary_agent(prompt)
            return {
                "active_engine": "bedrock_primary",
                "output": str(resp),
                "preflight": status,
            }
        except (ClientError, Exception) as exc:
            logger.warning("Bedrock invocation failed (%s). Activating multi-provider fallback.", exc)
            return fallback_handler(prompt)


def check_bedrock_availability(
    model_id: str = "amazon.nova-lite-v1:0",
    profile_name: str | None = None,
    region_name: str = "us-east-1",
) -> PreflightStatus:
    """Convenience helper to check Bedrock foundation model availability."""
    guard = BedrockPreflightGuard(profile_name=profile_name, region_name=region_name)
    return guard.check_availability(model_id=model_id)
