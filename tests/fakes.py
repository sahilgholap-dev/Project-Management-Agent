"""Test doubles for the LLM layer — unit tests never hit the network.
Real-model behavior is covered by the eval_* scripts against the holdout
project."""

import jsonschema


class FakeSonnet:
    """Returns queued responses in order. Queue an Exception instance to make
    the corresponding call raise (validation-failure / refusal paths)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _next(self, system, user_content, schema=None):
        self.calls.append({"system": system, "user": user_content})
        if not self.responses:
            raise AssertionError("FakeSonnet ran out of queued responses")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if schema is not None:
            jsonschema.validate(response, schema)  # keep fakes honest
        return response

    def structured(self, system, user_content, schema, max_retries=1):
        return self._next(system, user_content, schema)

    def text(self, system, user_content):
        return self._next(system, user_content)
