"""Feature gating rules and manual overrides."""

import pytest
from fastapi import HTTPException

from app.services import FeatureGate


def test_level_one_features_enabled(db_session, level_one_tenant):
    assert FeatureGate.is_enabled(db_session, level_one_tenant, "maintenance_stats")
    assert not FeatureGate.is_enabled(
        db_session, level_one_tenant, "failure_risk_scoring"
    )


def test_require_raises_403_with_upgrade_detail(db_session, level_one_tenant):
    with pytest.raises(HTTPException) as excinfo:
        FeatureGate.require(db_session, level_one_tenant, "rul_prediction")

    assert excinfo.value.status_code == 403
    detail = excinfo.value.detail
    assert detail["error"] == "feature_locked"
    assert detail["required_level"] == 3
    assert detail["current_level"] == 1


def test_unknown_feature_raises_keyerror(db_session, level_one_tenant):
    with pytest.raises(KeyError):
        FeatureGate.is_enabled(db_session, level_one_tenant, "no_such_feature")


def test_manual_override_grants_locked_feature(db_session, level_one_tenant):
    """An admin override lets a Level 1 tenant trial a Level 3 feature."""
    assert not FeatureGate.is_enabled(db_session, level_one_tenant, "rul_prediction")

    FeatureGate.set_override(db_session, level_one_tenant, "rul_prediction", True)

    assert FeatureGate.is_enabled(db_session, level_one_tenant, "rul_prediction")
    FeatureGate.require(db_session, level_one_tenant, "rul_prediction")


def test_manual_override_survives_toggle_sync(db_session, level_one_tenant):
    FeatureGate.set_override(db_session, level_one_tenant, "rul_prediction", True)
    FeatureGate.sync_toggles(db_session, level_one_tenant)

    assert FeatureGate.is_enabled(db_session, level_one_tenant, "rul_prediction")


def test_manual_override_can_revoke_an_earned_feature(db_session, level_two_tenant):
    FeatureGate.set_override(db_session, level_two_tenant, "roi_analysis", False)

    assert not FeatureGate.is_enabled(db_session, level_two_tenant, "roi_analysis")


def test_list_features_partitions_catalogue(db_session, level_two_tenant):
    listing = FeatureGate.list_features(db_session, level_two_tenant)

    enabled = {f.feature_key for f in listing.enabled}
    locked = {f.feature_key for f in listing.locked}

    assert enabled & locked == set()
    assert "cascade_impact_analysis" in enabled
    assert "anomaly_detection" in locked
    assert all(f.required_level <= 2 for f in listing.enabled)
