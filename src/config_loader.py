"""Config loading, validation, and override resolution (PRD sections 3, 5, 13, 16).

Doctrine: every skill reads behavior parameters exclusively through
``resolve(conn, project_id, key)`` — project override first, client default
otherwise, hard error if a required key is missing at both levels. No skill
touches client_config or projects.config_overrides directly.

Validation runs on EVERY save (PRD section 13), against config/config_schema.json
plus referential checks the JSON Schema cannot express (reviewer/approver users
must exist). A failure raises ConfigDefectError listing every defect — nothing
is silently patched or defaulted.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from src.lib import audit

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_SCHEMA_PATH = REPO_ROOT / "config" / "config_schema.json"

# Columns whose DB representation is JSON text.
_JSON_FIELDS = {"skill_depth", "tools_channels", "escalation_delay_by_tier", "working_calendar"}

# Fields referencing users(user_id): (field name, may be null)
_USER_REF_FIELDS = (
    ("primary_reviewer_id", False),
    ("backup_reviewer_id", True),
    ("change_approver_id", False),
    ("signoff_approver_id", False),
)


class ConfigDefectError(Exception):
    """A config save or resolution failed validation. PRD section 16: surfaced
    as a defect, never silently accepted; the affected skill refuses to run."""

    def __init__(self, defects: list[str]):
        self.defects = defects
        super().__init__("; ".join(defects))


@lru_cache(maxsize=1)
def _schema() -> dict:
    return json.loads(CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _validator() -> jsonschema.Validator:
    schema = _schema()
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def config_keys() -> set[str]:
    """All config field names — also the set of keys a project may override."""
    return set(_schema()["properties"].keys())


def required_keys() -> set[str]:
    return set(_schema()["required"])


def _schema_defects(instance: Any, validator: jsonschema.Validator, prefix: str = "") -> list[str]:
    defects = []
    for err in sorted(validator.iter_errors(instance), key=str):
        path = ".".join(str(p) for p in err.absolute_path)
        where = f"{prefix}{path}" if path else (prefix.rstrip(".") or "<root>")
        defects.append(f"{where}: {err.message}")
    return defects


def validate_client_config(conn: sqlite3.Connection, config: dict) -> None:
    """Full validation: JSON Schema + referential checks. Raises ConfigDefectError."""
    defects = _schema_defects(config, _validator())
    if not defects:  # referential checks only make sense on a well-shaped config
        for field, nullable in _USER_REF_FIELDS:
            value = config.get(field)
            if value is None:
                if not nullable:
                    defects.append(f"{field}: required user reference is unset")
                continue
            row = conn.execute(
                "SELECT invite_status FROM users WHERE user_id = ?", (value,)
            ).fetchone()
            if row is None:
                defects.append(f"{field}: user {value} does not exist")
            elif row["invite_status"] == "disabled":
                defects.append(f"{field}: user {value} is disabled")
    if defects:
        raise ConfigDefectError(defects)


def save_client_config(conn: sqlite3.Connection, client_id: int, config: dict) -> None:
    """Validate then upsert the client_config row. Validation on every save."""
    validate_client_config(conn, config)
    fields = sorted(config_keys())
    values = []
    for field in fields:
        value = config.get(field)
        if field in _JSON_FIELDS and value is not None:
            value = json.dumps(value)
        values.append(value)
    assignments = ", ".join(f"{f} = ?" for f in fields)
    conn.execute(
        f"INSERT INTO client_config (client_id, {', '.join(fields)})"
        f" VALUES (?{', ?' * len(fields)})"
        f" ON CONFLICT (client_id) DO UPDATE SET {assignments}, updated_at = datetime('now')",
        (client_id, *values, *values),
    )
    audit.log_action(
        conn,
        skill="config",
        action="save_client_config",
        input_summary={"client_id": client_id, "keys": fields},
        actor="user",
    )
    conn.commit()


def load_client_config(conn: sqlite3.Connection, client_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM client_config WHERE client_id = ?", (client_id,)
    ).fetchone()
    if row is None:
        raise ConfigDefectError([f"no client_config row for client {client_id}"])
    config = {}
    for field in config_keys():
        value = row[field]
        if field in _JSON_FIELDS and value is not None:
            value = json.loads(value)
        config[field] = value
    return config


def validate_overrides(overrides: dict) -> None:
    """Validate a project's config_overrides: known keys, each value valid for
    its field's subschema. A None value means 'not overridden' and is rejected —
    remove the key instead, so resolution semantics stay unambiguous."""
    defects = []
    properties = _schema()["properties"]
    for key, value in overrides.items():
        if key not in properties:
            defects.append(f"config_overrides.{key}: not a config key")
            continue
        if value is None:
            defects.append(
                f"config_overrides.{key}: null override is ambiguous — remove the key to fall back"
            )
            continue
        sub = jsonschema.validators.validator_for(_schema())(properties[key])
        defects.extend(_schema_defects(value, sub, prefix=f"config_overrides.{key}."))
    if defects:
        raise ConfigDefectError(defects)


def save_project_overrides(conn: sqlite3.Connection, project_id: int, overrides: dict) -> None:
    validate_overrides(overrides)
    cur = conn.execute(
        "UPDATE projects SET config_overrides = ? WHERE project_id = ?",
        (json.dumps(overrides), project_id),
    )
    if cur.rowcount == 0:
        raise ConfigDefectError([f"project {project_id} does not exist"])
    audit.log_action(
        conn,
        skill="config",
        action="save_project_overrides",
        input_summary={"project_id": project_id, "keys": sorted(overrides.keys())},
        actor="user",
    )
    conn.commit()


def resolve(conn: sqlite3.Connection, project_id: int, key: str) -> Any:
    """Resolution order (PRD section 5): project override first, client default
    otherwise. A required key missing at both levels is a hard ConfigDefectError
    (PRD section 16) — the caller (skill) must refuse to run, not default."""
    if key not in config_keys():
        raise KeyError(f"unknown config key: {key}")
    row = conn.execute(
        "SELECT client_id, config_overrides FROM projects WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if row is None:
        raise ConfigDefectError([f"project {project_id} does not exist"])
    overrides = json.loads(row["config_overrides"] or "{}")
    if key in overrides and overrides[key] is not None:
        return overrides[key]
    config = load_client_config(conn, row["client_id"])
    value = config.get(key)
    if value is None and key in required_keys():
        raise ConfigDefectError(
            [f"required config key '{key}' unset at both project and client level"]
        )
    return value


def resolve_escalation_delay_hours(conn: sqlite3.Connection, project_id: int, tier: int) -> float:
    """Per-tier delay if configured (PRD section 5 v2-correction), else the
    client-wide escalation_delay_hours."""
    by_tier = resolve(conn, project_id, "escalation_delay_by_tier") or {}
    value = by_tier.get(str(tier))
    if value is not None:
        return float(value)
    return float(resolve(conn, project_id, "escalation_delay_hours"))
