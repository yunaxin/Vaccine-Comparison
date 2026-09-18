"""
run_agent_test.py

Calls the Washington ADK agent programmatically for a single patient
and prints its final response, so we can confirm the runner API works
and the agent produces valid, parseable JSON before scaling this up to
many patients.

Usage:
    python3 run_agent_test.py "Reynaldo722 Beatty507"
"""

import sys
import json
import asyncio

from google.adk.runners import InMemoryRunner
from google.genai import types

from adk_agents.washington_agent.agent import root_agent


def extract_json_block(text: str):
    """Pulls the JSON object out of the agent's response text, stripping
    markdown code fences (```json ... ```) if present."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None

    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


async def run_for_patient(patient_name: str):
    runner = InMemoryRunner(agent=root_agent, app_name="washington_agent_test")

    session = await runner.session_service.create_session(
        app_name="washington_agent_test", user_id="test_user"
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=f"Check {patient_name}'s compliance with Washington's school immunization requirements.")],
    )

    final_text = None
    async for event in runner.run_async(user_id="test_user", session_id=session.id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text

    return final_text


if __name__ == "__main__":
    patient_name = sys.argv[1] if len(sys.argv) > 1 else "Reynaldo722 Beatty507"
    response_text = asyncio.run(run_for_patient(patient_name))

    print("=== Full agent response ===")
    print(response_text)

    print("\n=== Extracted JSON ===")
    parsed = extract_json_block(response_text or "")
    if parsed:
        print(json.dumps(parsed, indent=2))
    else:
        print("Could not extract valid JSON from the response -- check the full response above.")