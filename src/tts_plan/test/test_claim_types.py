"""Tests for ClaimType functionality (EXCLUSIVE vs AVOIDANCE claims)."""

import pytest
from datetime import datetime, timedelta

from tts_plan.activity import Activity, ClaimType


class SimpleActivity(Activity):
    """Simple activity for testing."""
    NAME = "Simple Activity"
    COLOR = "blue"
    
    def _from_json_dict(self, json_data):
        pass


@pytest.fixture
def base_time():
    """Base time for tests."""
    return datetime(2020, 1, 1, 12, 0, 0)


def test_exclusive_claims_conflict(base_time):
    """Test that EXCLUSIVE claims conflict with each other (traditional behavior)."""
    # Two activities with EXCLUSIVE claims on the same resource
    activity_a = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Activity A"
    )
    activity_a.add_claim('RESOURCE_X', claim_type=ClaimType.EXCLUSIVE)
    
    activity_b = SimpleActivity(
        begin_time=base_time + timedelta(minutes=30),
        duration=timedelta(hours=1),
        name="Activity B"
    )
    activity_b.add_claim('RESOURCE_X', claim_type=ClaimType.EXCLUSIVE)
    
    # They should conflict
    assert activity_a.conflicts_with(activity_b)
    conflicts = activity_a.get_conflicts_with(activity_b)
    assert len(conflicts) == 1
    assert 'RESOURCE_X' in conflicts[0][2]


def test_exclusive_and_avoidance_conflict(base_time):
    """Test that EXCLUSIVE and AVOIDANCE claims conflict."""
    # Activity C has EXCLUSIVE claim (e.g., using a resource)
    activity_c = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Activity C - Uses Resource"
    )
    activity_c.add_claim('RESOURCE_X', claim_type=ClaimType.EXCLUSIVE)
    
    # Activity A has AVOIDANCE claim (e.g., needs to avoid the resource)
    activity_a = SimpleActivity(
        begin_time=base_time + timedelta(minutes=30),
        duration=timedelta(hours=1),
        name="Activity A - Avoids Resource"
    )
    activity_a.add_claim('RESOURCE_X', claim_type=ClaimType.AVOIDANCE)
    
    # They should conflict
    assert activity_a.conflicts_with(activity_c)
    assert activity_c.conflicts_with(activity_a)
    
    conflicts = activity_a.get_conflicts_with(activity_c)
    assert len(conflicts) == 1
    assert 'RESOURCE_X' in conflicts[0][2]


def test_avoidance_claims_do_not_conflict(base_time):
    """Test that AVOIDANCE claims do NOT conflict with each other.
    
    This is the key new behavior: if Activities A and B both need to avoid
    a resource (without using it), they don't conflict with each other.
    """
    # Activity A has AVOIDANCE claim
    activity_a = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Activity A - Avoids Resource"
    )
    activity_a.add_claim('RESOURCE_X', claim_type=ClaimType.AVOIDANCE)
    
    # Activity B has AVOIDANCE claim
    activity_b = SimpleActivity(
        begin_time=base_time + timedelta(minutes=30),
        duration=timedelta(hours=1),
        name="Activity B - Avoids Resource"
    )
    activity_b.add_claim('RESOURCE_X', claim_type=ClaimType.AVOIDANCE)
    
    # They should NOT conflict
    assert not activity_a.conflicts_with(activity_b)
    conflicts = activity_a.get_conflicts_with(activity_b)
    assert len(conflicts) == 0


def test_three_activity_scenario(base_time):
    """Test the scenario: A and B both avoid C, but A and B don't conflict.
    
    This is the primary use case that motivated the ClaimType system.
    """
    # Activity C makes EXCLUSIVE claim (e.g., uses SHARAD instrument)
    activity_c = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Activity C - Uses SHARAD"
    )
    activity_c.add_claim('SHARAD', claim_type=ClaimType.EXCLUSIVE)
    
    # Activity A makes AVOIDANCE claim (needs to avoid SHARAD)
    activity_a = SimpleActivity(
        begin_time=base_time + timedelta(minutes=20),
        duration=timedelta(hours=1),
        name="Activity A - Avoids SHARAD"
    )
    activity_a.add_claim('SHARAD', claim_type=ClaimType.AVOIDANCE)
    
    # Activity B makes AVOIDANCE claim (also needs to avoid SHARAD)
    activity_b = SimpleActivity(
        begin_time=base_time + timedelta(minutes=40),
        duration=timedelta(hours=1),
        name="Activity B - Avoids SHARAD"
    )
    activity_b.add_claim('SHARAD', claim_type=ClaimType.AVOIDANCE)
    
    # A should conflict with C
    assert activity_a.conflicts_with(activity_c)
    assert activity_c.conflicts_with(activity_a)
    
    # B should conflict with C
    assert activity_b.conflicts_with(activity_c)
    assert activity_c.conflicts_with(activity_b)
    
    # A and B should NOT conflict with each other
    assert not activity_a.conflicts_with(activity_b)
    assert not activity_b.conflicts_with(activity_a)


def test_default_claim_type_is_exclusive(base_time):
    """Test that the default claim type is EXCLUSIVE (backward compatibility)."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Activity"
    )
    activity.add_claim('RESOURCE_X')  # No claim_type specified
    
    # Check that the claim has EXCLUSIVE type
    assert len(activity.claims) == 1
    assert activity.claims[0].claim_type == ClaimType.EXCLUSIVE


def test_mixed_claims_on_same_activity(base_time):
    """Test an activity with both EXCLUSIVE and AVOIDANCE claims on different resources."""
    activity_a = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Activity A"
    )
    activity_a.add_claim('RESOURCE_X', claim_type=ClaimType.EXCLUSIVE)
    activity_a.add_claim('RESOURCE_Y', claim_type=ClaimType.AVOIDANCE)
    
    activity_b = SimpleActivity(
        begin_time=base_time + timedelta(minutes=30),
        duration=timedelta(hours=1),
        name="Activity B"
    )
    activity_b.add_claim('RESOURCE_X', claim_type=ClaimType.AVOIDANCE)
    activity_b.add_claim('RESOURCE_Y', claim_type=ClaimType.AVOIDANCE)
    
    # Should conflict on RESOURCE_X (EXCLUSIVE vs AVOIDANCE)
    # Should NOT conflict on RESOURCE_Y (AVOIDANCE vs AVOIDANCE)
    assert activity_a.conflicts_with(activity_b)
    
    conflicts = activity_a.get_conflicts_with(activity_b)
    assert len(conflicts) == 1
    assert 'RESOURCE_X' in conflicts[0][2]
    assert 'RESOURCE_Y' not in conflicts[0][2]


def test_claim_repr_shows_type(base_time):
    """Test that Claim.__repr__ shows the claim type when it's AVOIDANCE."""
    from tts_plan.activity import Claim
    
    # EXCLUSIVE claims don't show type (default)
    exclusive_claim = Claim('RESOURCE_X', ClaimType.EXCLUSIVE)
    assert 'EXCLUSIVE' not in repr(exclusive_claim)
    
    # AVOIDANCE claims do show type
    avoidance_claim = Claim('RESOURCE_Y', ClaimType.AVOIDANCE)
    assert 'AVOIDANCE' in repr(avoidance_claim)
