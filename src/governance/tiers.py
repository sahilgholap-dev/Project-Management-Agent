"""Frozen item_type -> tier map (PRD section 10: tiers are fixed to the skill
that produced the item, NOT adjustable by any client config). This is the one
deliberate exception to config-not-code — a config that tried to set a tier is
rejected by the config validator (there is no such config key)."""

from types import MappingProxyType

TIER_BY_ITEM_TYPE = MappingProxyType(
    {
        # Tier 1 — single-tap approve/reject
        "risk_alert": 1,          # 8.5 step 6
        "off_track_alert": 1,     # 8.4 step 8
        "infeasible_plan": 1,     # 8.2 step 9
        "unassignable_task": 1,   # 8.3 step 5
        "slip_impact": 1,         # 8.6 step 6
        "clarification": 1,       # 8.1 steps 3-4, 8.7 step 6
        # Tier 2 — full review before it goes out
        "comms_draft": 2,         # 8.8 step 4
        "status_report": 2,       # section 10 example
        "retrospective": 2,       # section 11 close path (confirmed Q18)
        # Tier 3 — formal packet, explicit sign-off
        "change_request": 3,      # section 10
        "signoff_packet": 3,      # section 10
    }
)
