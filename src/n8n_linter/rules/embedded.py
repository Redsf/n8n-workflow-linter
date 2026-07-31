"""Secrets that the known-key-format scanner cannot see.

`hardcoded-secret` matches shapes it recognises — `sk-...`, `AKIA...`, `ghp_...`.
That covers the big providers and misses everything else: an internal service's
key, a customer's API token, anything assigned inside a Code node. These rules
close that gap from the other direction — instead of asking "does this look like
an OpenAI key?", they ask "is a value that behaves like a credential sitting
somewhere a credential should never be?"

Entropy is what keeps this honest. A field called `token` holding
"REPLACE_WITH_TOKEN" or "xxxxxxxxxxxxxxxx" is a placeholder; one holding
"7f3Ka92mFhs82nXq" is not. Requiring no whitespace removes prose before entropy
is even consulted.
"""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import parse_qsl, urlsplit

from ..model import Workflow
from ..report import RuleHit, Severity
from ..text_utils import line_of_offset, redact, shannon_entropy
from .base import Rule

# Below this, a long no-whitespace string is repetition or a template, not a key.
ENTROPY_FLOOR = 3.0
MIN_SECRET_LENGTH = 16

CODE_PARAM_KEYS = ("jsCode", "pythonCode", "functionCode", "code")

# name = "value" / name: "value", where the name reads like a credential.
ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(
        api[_-]?key | apikey | secret[_-]?key | client[_-]?secret | secret |
        access[_-]?token | auth[_-]?token | refresh[_-]?token | token |
        password | passwd | pwd | private[_-]?key | credential
    )\b
    \s* [:=] \s*
    ['"]([^'"\s]{16,200})['"]
    """
)

# Authorization: Bearer <token>, however it is quoted.
BEARER = re.compile(r"(?i)bearer\s+([A-Za-z0-9_\-\.]{20,400})")

# n8n stores header and query collections as separate name/value fields, so an
# assignment regex never sees them adjacent. This does.
NAME_VALUE_PAIR = re.compile(
    r"""(?ix)
    "name"\s*:\s*"([^"]*(?:api[_-]?key|apikey|token|secret|authorization|password)[^"]*)"
    \s*,\s*
    "value"\s*:\s*"([^"\s]{16,400})"
    """
)

PLACEHOLDER_MARKERS = (
    "REPLACE", "YOUR", "EXAMPLE", "PLACEHOLDER", "XXXX", "DUMMY",
    "TEST_", "SAMPLE", "CHANGEME", "<", "...",
)

# An n8n expression resolves at runtime — it is the correct way to do this, not
# a leak. Anything referencing one is skipped.
EXPRESSION_MARKERS = ("{{", "$json", "$node", "$credentials", "$env", "$secrets", "$vars")

# Query parameters whose value is a credential by definition.
CREDENTIAL_PARAMS = frozenset({
    "api_key", "apikey", "api-key", "key", "token", "access_token", "accesstoken",
    "auth", "auth_token", "authorization", "password", "passwd", "pwd",
    "secret", "client_secret", "app_secret", "private_key", "signature",
})


def _is_placeholder(value: str) -> bool:
    upper = value.upper()
    return any(marker in upper for marker in PLACEHOLDER_MARKERS)


def _is_expression(value: str) -> bool:
    return any(marker in value for marker in EXPRESSION_MARKERS)


def _looks_like_secret(value: str) -> bool:
    if len(value) < MIN_SECRET_LENGTH:
        return False
    if _is_placeholder(value) or _is_expression(value):
        return False
    return shannon_entropy(value) >= ENTROPY_FLOOR


class EmbeddedSecret(Rule):
    id = "embedded-secret"
    default_severity = Severity.ERROR
    summary = "A credential-shaped value is assigned inside a Code node or a header/query parameter."
    plain_title = "A password or key is typed into a step instead of stored safely"
    plain_meaning = (
        "n8n has a Credentials vault. Anything you put there is encrypted and "
        "left out when you export a workflow. This value was typed straight into "
        "a Code step or a header field instead, so it is sitting in the file as "
        "plain readable text. It does not match the shape of a well-known key "
        "like an OpenAI one, which is exactly why it went unnoticed — but "
        "whatever it unlocks, anyone holding this file can unlock too."
    )
    plain_fix = (
        "1. Treat the value as already exposed. Go to whatever service it belongs "
        "to and regenerate or revoke it.\n"
        "2. In n8n, open the step named above. If it is an HTTP Request, use the "
        "'Authentication' section and create a proper credential rather than "
        "typing the key into a header.\n"
        "3. If it is a Code step, do not put the key in code at all — pass it in "
        "from a credential on an earlier node, or use an environment variable.\n"
        "4. Export again and re-run this check to confirm it is gone."
    )

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        reported: set[tuple[str, int]] = set()

        for node in workflow.nodes:
            for key in CODE_PARAM_KEYS:
                body = node.parameters.get(key)
                if not isinstance(body, str):
                    continue
                for label, value in self._scan_code(body):
                    marker = (value, node.line or 0)
                    if marker in reported:
                        continue
                    reported.add(marker)
                    yield RuleHit(
                        message=(
                            f"{label} assigned directly in code ({redact(value)}) — "
                            f"move it into an n8n credential"
                        ),
                        node_name=node.name,
                        line=node.line,
                    )

        for match in NAME_VALUE_PAIR.finditer(workflow.raw_text):
            field, value = match.group(1), match.group(2)
            if not _looks_like_secret(value):
                continue
            line = line_of_offset(workflow.raw_text, match.start())
            if (value, line) in reported:
                continue
            reported.add((value, line))
            yield RuleHit(
                message=(
                    f'"{field}" parameter holds a literal credential '
                    f"({redact(value)}) — move it into an n8n credential"
                ),
                line=line,
            )

    @staticmethod
    def _scan_code(body: str) -> Iterable[tuple[str, str]]:
        for match in ASSIGNMENT.finditer(body):
            value = match.group(2)
            if _looks_like_secret(value):
                yield f"'{match.group(1)}'", value
        for match in BEARER.finditer(body):
            value = match.group(1)
            if _looks_like_secret(value):
                yield "bearer token", value


class CredentialInUrl(Rule):
    id = "credential-in-url"
    default_severity = Severity.ERROR
    summary = "An API key or token is passed in a URL query string."
    plain_title = "A key is being sent inside the web address itself"
    plain_meaning = (
        "This step calls a URL with the key written into the address, like "
        "...?api_key=abc123. Two problems. First, the key is now in this file in "
        "plain text. Second, and worse in the long run: web addresses get logged "
        "everywhere — by the service you are calling, by proxies in between, by "
        "error trackers. A key sent this way ends up in log files you will never "
        "see and cannot clean."
    )
    plain_fix = (
        "1. Regenerate the key at the service it belongs to. Assume the old one "
        "is compromised — it has been travelling in plain sight.\n"
        "2. In n8n, open the HTTP Request step named above.\n"
        "3. Remove the key from the URL field.\n"
        "4. Use the 'Authentication' section instead — most services accept the "
        "key as a header, which is not logged the way URLs are. If the service "
        "genuinely only supports a query parameter, at least move the value into "
        "a credential so it stays out of the exported file."
    )

    def check(self, workflow: Workflow) -> Iterable[RuleHit]:
        for node in workflow.nodes:
            if node.disabled:
                continue
            url = node.parameters.get("url")
            if not isinstance(url, str) or "?" not in url:
                continue
            if _is_expression(url):
                continue

            query = urlsplit(url).query
            for name, value in parse_qsl(query, keep_blank_values=True):
                if name.strip().lower() not in CREDENTIAL_PARAMS:
                    continue
                if len(value) < 8 or _is_placeholder(value) or _is_expression(value):
                    continue
                yield RuleHit(
                    message=(
                        f"URL passes '{name}' as a query parameter ({redact(value)}) — "
                        f"send it as a header via a credential instead"
                    ),
                    node_name=node.name,
                    line=node.line,
                )
