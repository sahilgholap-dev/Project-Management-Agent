"""Single Anthropic client wrapper for every runtime LLM call.

Runtime model is Claude Sonnet 5 (PRD section 2, v4.1 correction) — Fable 5 is
the build-time tool only and never appears here.

Structured output uses the API's output_config.format (JSON Schema) so the
response text is guaranteed schema-valid JSON; we still validate defensively
with jsonschema, retry once on a malformed result, and then HALT AND SURFACE
(PRD 8.1 step 4: a missing required field halts and goes to the reviewer — it
is never silently patched). Callers catch LLMValidationError / LLMRefusalError
and raise a Tier 1 clarification item.

Schema constraints (API-enforced): every object needs additionalProperties:
false and required; no numeric/length constraints. Keep prompt schemas simple.
"""

from __future__ import annotations

import json
from typing import Any

import jsonschema

MODEL = "claude-sonnet-5"
MAX_TOKENS = 16000  # non-streaming guidance; every skill call is a bounded single call


class LLMValidationError(Exception):
    """Model output failed schema validation after retries. Halt and surface."""


class LLMRefusalError(Exception):
    """The model declined the request (stop_reason == 'refusal')."""


class SonnetClient:
    def __init__(self, client: Any = None, model: str = MODEL):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model

    def structured(
        self,
        system: str,
        user_content: str,
        schema: dict,
        max_retries: int = 1,
    ) -> dict:
        """One bounded call returning schema-validated JSON.

        Retries once on malformed/invalid output (appending the validation
        error), then raises LLMValidationError — the caller surfaces it to the
        reviewer rather than guessing.
        """
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema)

        content = user_content
        last_error: str | None = None
        for _attempt in range(max_retries + 1):
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": content}],
            )
            if response.stop_reason == "refusal":
                raise LLMRefusalError("model declined the request")
            if response.stop_reason == "max_tokens":
                last_error = "output truncated at max_tokens"
                continue
            text = next((b.text for b in response.content if b.type == "text"), "")
            try:
                data = json.loads(text)
                validator.validate(data)
                return data
            except (json.JSONDecodeError, jsonschema.ValidationError) as err:
                last_error = str(err)
                content = (
                    f"{user_content}\n\nYour previous output failed validation:"
                    f" {last_error}\nReturn corrected JSON matching the schema exactly."
                )
        raise LLMValidationError(f"output invalid after {max_retries + 1} attempts: {last_error}")

    def text(self, system: str, user_content: str) -> str:
        """One bounded free-text call (plain-language summaries)."""
        response = self._client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        if response.stop_reason == "refusal":
            raise LLMRefusalError("model declined the request")
        return next((b.text for b in response.content if b.type == "text"), "")
