"""Phase 0 gate: config validation on every save, override resolution
(project first, client fallback, hard error on required-missing-at-both-levels),
and the PRD section 16 edge cases."""

import pytest

from src import config_loader as cl
from tests.conftest import set_overrides_raw

# --- save + load round-trip ------------------------------------------------

def test_valid_config_round_trips(seeded, valid_config):
    cl.save_client_config(seeded, 1, valid_config)
    loaded = cl.load_client_config(seeded, 1)
    assert loaded == valid_config


def test_save_is_upsert(seeded, valid_config):
    cl.save_client_config(seeded, 1, valid_config)
    valid_config["reporting_cadence"] = "daily"
    cl.save_client_config(seeded, 1, valid_config)
    assert cl.load_client_config(seeded, 1)["reporting_cadence"] == "daily"


def test_save_writes_audit_log(seeded, valid_config):
    cl.save_client_config(seeded, 1, valid_config)
    row = seeded.execute(
        "SELECT skill, action, actor FROM audit_log ORDER BY audit_id DESC"
    ).fetchone()
    assert (row["skill"], row["action"], row["actor"]) == (
        "config", "save_client_config", "user",
    )


# --- validation on every save (PRD sections 13, 16) -------------------------

def test_missing_required_field_rejected(seeded, valid_config):
    del valid_config["slip_threshold_days"]
    with pytest.raises(cl.ConfigDefectError, match="slip_threshold_days"):
        cl.save_client_config(seeded, 1, valid_config)


def test_bad_cadence_rejected(seeded, valid_config):
    valid_config["reporting_cadence"] = "hourly"
    with pytest.raises(cl.ConfigDefectError, match="reporting_cadence"):
        cl.save_client_config(seeded, 1, valid_config)


def test_bad_assignment_strategy_rejected(seeded, valid_config):
    valid_config["assignment_strategy"] = "random"
    with pytest.raises(cl.ConfigDefectError):
        cl.save_client_config(seeded, 1, valid_config)


def test_stakeholder_comms_can_never_be_autonomous(seeded, valid_config):
    """PRD section 8.8: the one skill that never gets a fully-automatic depth."""
    valid_config["skill_depth"]["stakeholder_comms"] = "autonomous"
    with pytest.raises(cl.ConfigDefectError, match="stakeholder_comms"):
        cl.save_client_config(seeded, 1, valid_config)


def test_unknown_key_rejected(seeded, valid_config):
    valid_config["frobnicate"] = True
    with pytest.raises(cl.ConfigDefectError):
        cl.save_client_config(seeded, 1, valid_config)


def test_nonexistent_reviewer_rejected(seeded, valid_config):
    valid_config["primary_reviewer_id"] = 999
    with pytest.raises(cl.ConfigDefectError, match="999 does not exist"):
        cl.save_client_config(seeded, 1, valid_config)


def test_disabled_approver_rejected(seeded, valid_config):
    seeded.execute("UPDATE users SET invite_status = 'disabled' WHERE user_id = 1")
    with pytest.raises(cl.ConfigDefectError, match="disabled"):
        cl.save_client_config(seeded, 1, valid_config)


def test_all_defects_reported_at_once(seeded, valid_config):
    valid_config["reporting_cadence"] = "hourly"
    valid_config["slip_threshold_days"] = -1
    with pytest.raises(cl.ConfigDefectError) as exc:
        cl.save_client_config(seeded, 1, valid_config)
    assert len(exc.value.defects) >= 2


# --- override validation ----------------------------------------------------

def test_valid_override_saves(seeded, valid_config):
    cl.save_client_config(seeded, 1, valid_config)
    cl.save_project_overrides(seeded, 10, {"escalation_delay_hours": 4})


def test_unknown_override_key_rejected(seeded):
    with pytest.raises(cl.ConfigDefectError, match="not a config key"):
        cl.save_project_overrides(seeded, 10, {"nonsense": 1})


def test_invalid_override_value_rejected(seeded):
    with pytest.raises(cl.ConfigDefectError):
        cl.save_project_overrides(seeded, 10, {"reporting_cadence": "hourly"})


def test_null_override_rejected_as_ambiguous(seeded):
    with pytest.raises(cl.ConfigDefectError, match="remove the key"):
        cl.save_project_overrides(seeded, 10, {"voice_style": None})


def test_override_cannot_make_comms_autonomous(seeded, valid_config):
    depth = dict(valid_config["skill_depth"], stakeholder_comms="autonomous")
    with pytest.raises(cl.ConfigDefectError, match="stakeholder_comms"):
        cl.save_project_overrides(seeded, 10, {"skill_depth": depth})


# --- resolution: project override first, client default otherwise -----------

def test_resolve_client_default(seeded, valid_config):
    cl.save_client_config(seeded, 1, valid_config)
    assert cl.resolve(seeded, 10, "reporting_cadence") == "weekly"


def test_resolve_project_override_wins(seeded, valid_config):
    cl.save_client_config(seeded, 1, valid_config)
    cl.save_project_overrides(seeded, 10, {"reporting_cadence": "daily"})
    assert cl.resolve(seeded, 10, "reporting_cadence") == "daily"


def test_resolve_unknown_key_raises_keyerror(seeded):
    with pytest.raises(KeyError):
        cl.resolve(seeded, 10, "not_a_key")


def test_required_key_missing_at_both_levels_is_hard_error(seeded, valid_config):
    """PRD section 16: e.g. no reviewer set at either level — the skill must
    refuse to run. Two defense layers: the DB's NOT NULL rejects a direct edit
    that would null a required column, and if the config row is missing
    entirely (the reachable defect state), resolve() hard-errors."""
    import sqlite3

    cl.save_client_config(seeded, 1, valid_config)
    with pytest.raises(sqlite3.IntegrityError):
        seeded.execute(
            "UPDATE client_config SET primary_reviewer_id = NULL WHERE client_id = 1"
        )
    seeded.execute("DELETE FROM client_config WHERE client_id = 1")
    seeded.commit()
    with pytest.raises(cl.ConfigDefectError, match="no client_config row"):
        cl.resolve(seeded, 10, "primary_reviewer_id")


def test_optional_key_missing_at_both_levels_is_none(seeded, valid_config):
    valid_config["backup_reviewer_id"] = None
    cl.save_client_config(seeded, 1, valid_config)
    assert cl.resolve(seeded, 10, "backup_reviewer_id") is None


def test_resolve_ignores_raw_null_override(seeded, valid_config):
    """A null smuggled into config_overrides by direct edit falls back to the
    client default instead of resolving to None."""
    cl.save_client_config(seeded, 1, valid_config)
    set_overrides_raw(seeded, 10, {"reporting_cadence": None})
    assert cl.resolve(seeded, 10, "reporting_cadence") == "weekly"


def test_resolve_missing_project(seeded, valid_config):
    cl.save_client_config(seeded, 1, valid_config)
    with pytest.raises(cl.ConfigDefectError, match="project 99"):
        cl.resolve(seeded, 99, "reporting_cadence")


# --- escalation delay resolution (per-tier override, PRD section 5) ---------

def test_escalation_delay_per_tier_override(seeded, valid_config):
    cl.save_client_config(seeded, 1, valid_config)  # by_tier: {"1": 8, "3": 48}
    assert cl.resolve_escalation_delay_hours(seeded, 10, 1) == 8
    assert cl.resolve_escalation_delay_hours(seeded, 10, 2) == 24  # falls back
    assert cl.resolve_escalation_delay_hours(seeded, 10, 3) == 48


def test_escalation_delay_project_override_beats_client_by_tier(seeded, valid_config):
    cl.save_client_config(seeded, 1, valid_config)
    cl.save_project_overrides(seeded, 10, {"escalation_delay_by_tier": {"1": 2}})
    assert cl.resolve_escalation_delay_hours(seeded, 10, 1) == 2
