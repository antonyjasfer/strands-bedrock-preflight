# strands-bedrock-preflight

[![PyPI version](https://img.shields.io/badge/pypi-v0.1.0-blue.svg)](https://pypi.org/project/strands-bedrock-preflight/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Strands Agents](https://img.shields.io/badge/Strands_Agents-v1.54.0-purple.svg)](https://github.com/strands-ai/strands)

**strands-bedrock-preflight** is a standalone, open-source resilience utility for developers building AI agents with **AWS Bedrock** and the **Strands Agents SDK**.

---

## The Problem

When developing applications using the AWS Bedrock Converse API with models such as `amazon.nova-lite-v1:0`, invocation requests fail with:
```text
botocore.errorfactory.ValidationException: An error occurred (ValidationException) 
when calling the ConverseStream operation: Operation not allowed
```
This occurs when:
1. Model access agreements have not yet propagated to the account.
2. The account is an **AWS India (AISPL)** account undergoing verification (e.g., AWS Support Case `178842133900178`).
3. Account quotas are set to `0 TPM / 0 RPM` pending billing activation.

Crashing during live demos, hackathon judging, or critical production workflows is unacceptable.

---

## The Solution

`strands-bedrock-preflight` queries Bedrock's control plane via `bedrock.get_foundation_model_availability()` and AWS STS **before** making expensive runtime inference calls. If authorization is `NOT_AUTHORIZED`, it seamlessly activates your fallback strategy (e.g. Gemini, OpenRouter, or a deterministic local tool router) without crashing your application.

---

## Installation

```bash
pip install strands-bedrock-preflight
```

---

## Quickstart

```python
import boto3
from strands_bedrock_preflight import BedrockPreflightGuard

# 1. Initialize guard
guard = BedrockPreflightGuard(profile_name="ledgerguard", region_name="us-east-1")

# 2. Check model availability
status = guard.check_availability("amazon.nova-lite-v1:0")

if status.is_authorized:
    print(f"Model is ready for inference on {status.identity_arn}")
else:
    print(f"Model access is {status.authorization_status}. Routing to fallback!")
```

### Wrapping Strands Agent Execution

```python
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands_bedrock_preflight import BedrockPreflightGuard

guard = BedrockPreflightGuard(profile_name="ledgerguard")
primary_agent = Agent(model=BedrockModel(model_id="amazon.nova-lite-v1:0"))

def my_fallback_handler(prompt: str):
    return {"active_engine": "local_tool_router", "output": "Verified deterministically."}

result = guard.execute_resilient(
    prompt="Audit invoice 102",
    primary_agent=primary_agent,
    fallback_handler=my_fallback_handler,
)

print("Active Engine:", result["active_engine"])
```

---

## Hackathon Open Source Mini-Challenge

Built as part of **LedgerGuard** for the **Amazon Developer Hackathon** (Alexa+ Primary Track + Open Source Mini-Challenge + AWS Builder Mini-Challenge).

Licensed under the permissive [MIT License](LICENSE).
