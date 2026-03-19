import pytest
import uuid
import sys
from datetime import datetime, timedelta
from enum import auto

# Ensure current directory is in python path so we can import activity
sys.path.append(".")

from tts_plan.activity import (
    Activity,
    Claim,
    TemporalRelation,
    ConstraintTarget,
    Claimables,
    ActivityConstraint,
    ModeledValueConstraint,
    AbsoluteTimeConstraint
)

# -------------------------------------------------------------------------
# Fixtures and Helpers
# -------------------------------------------------------------------------

class ScienceActivity(Activity):
    """Concrete implementation for testing subclass behavior."""
    TYPE = "ScienceActivity"
    COLOR = "blue"

    def _to_json_dict(self):
        # Override to add custom field
        data = super()._to_json_dict()
        data['science_mode'] = self.metadata.get('science_mode', 'default')
        return data

    def _from_json_dict(self, json_data):
        # Override to restore custom field
        super()._from_json_dict(json_data)
        if 'science_mode' in json_data:
            self.metadata['science_mode'] = json_data['science_mode']

class CommActivity(Activity):
    """Simple concrete implementation."""
    TYPE = "CommActivity"
    COLOR = "green"

@pytest.fixture
def base_time():
    return datetime(2026, 1, 20, 12, 0, 0)

@pytest.fixture
def science_activity(base_time):
    return ScienceActivity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="Test Science",
        description="Testing Description",
        metadata={"science_mode": "high_res"}
    )

# -------------------------------------------------------------------------
# Core Activity Tests
# -------------------------------------------------------------------------

def test_initialization(science_activity, base_time):
    """Test basic initialization and property calculation."""
    assert science_activity.name == "Test Science"
    assert science_activity.begin_time == base_time
    assert science_activity.duration == timedelta(minutes=30)
    assert science_activity.end_time == base_time + timedelta(minutes=30)
    assert science_activity.uuid is not None
    
    # The instance attribute .color now defaults to the class COLOR value.
    # The class attribute .COLOR stores the default ("blue").
    assert science_activity.color == "blue"
    assert science_activity.COLOR == "blue"

def test_color_resolution(science_activity):
    """Test that the color resolves correctly in JSON output."""
    # 1. Default Behavior (Class Color)
    json_data = science_activity.to_json()
    assert json_data['color'] == "blue"

    # 2. Override Behavior (Instance Color)
    science_activity.color = "red"
    json_data_override = science_activity.to_json()
    assert json_data_override['color'] == "red"

def test_description_defaults():
    """Test description fallback logic."""
    t = datetime.now()
    # 1. Explicit description
    a1 = CommActivity(t, timedelta(1), description="Explicit")
    assert a1.description == "Explicit"
    
    # 2. Class level DESCRIPTION (Mocking it)
    CommActivity.DESCRIPTION = "Class Default"
    a2 = CommActivity(t, timedelta(1))
    assert a2.description == "Class Default"
    CommActivity.DESCRIPTION = None # Reset
    
    # 3. Fallback to Class Name
    a3 = CommActivity(t, timedelta(1))
    assert "CommActivity activity" in a3.description

def test_claims_management(science_activity):
    """Test adding, checking, and removing resource claims."""
    # Add Claimables enum
    science_activity.add_claim(Claimables.CPU)
    
    # Add String claim with metadata
    science_activity.add_claim("BATTERY", metadata={"unit": "Ah"})
    
    assert len(science_activity.claims) == 2
    
    # Verify contents - claims are now Claim objects
    cpu_claim = next(c for c in science_activity.claims if c.resource == Claimables.CPU)
    assert cpu_claim.resource == Claimables.CPU
    
    batt_claim = next(c for c in science_activity.claims if c.resource == "BATTERY")
    assert batt_claim.metadata['unit'] == "Ah"

    # Remove
    science_activity.remove_claim(Claimables.CPU)
    assert len(science_activity.claims) == 1
    assert science_activity.claims[0].resource == "BATTERY"

def test_child_activities(science_activity, base_time):
    """Test adding children and hierarchy."""
    child = CommActivity(base_time, timedelta(minutes=10), name="Child")
    res = science_activity.add_child(child)
    
    assert res == child # Verify method chaining return
    assert len(science_activity.activities) == 1
    assert science_activity.activities[0] is child

# -------------------------------------------------------------------------
# Constraint Tests
# -------------------------------------------------------------------------

def test_activity_constraints(science_activity):
    """Test relative activity constraints (before, after, during)."""
    target_uuid = str(uuid.uuid4())
    
    # Test 'must_be_before'
    c1 = science_activity.must_be_before(target_uuid, timedelta(minutes=5))
    assert isinstance(c1, ActivityConstraint)
    assert c1.relation == TemporalRelation.BEFORE
    assert c1.target == target_uuid
    assert c1.lead_time == timedelta(minutes=5)

    # Test 'must_not_be_during'
    c2 = science_activity.must_not_be_during("Eclipse")
    assert c2.relation == TemporalRelation.NOT_DURING
    assert c2.target == "Eclipse"
    assert c2.target_type == ConstraintTarget.CLASS

def test_absolute_time_constraints(science_activity, base_time):
    """Test absolute time constraints."""
    target_time = base_time + timedelta(hours=1)
    
    c = science_activity.must_be_before_time(target_time)
    
    assert isinstance(c, AbsoluteTimeConstraint)
    assert c.relation == TemporalRelation.BEFORE
    assert c.absolute_time == target_time

def test_model_constraints(science_activity):
    """Test modeled value constraints."""
    c = science_activity.add_model_constraint("Battery", 20.0, ">")
    
    assert isinstance(c, ModeledValueConstraint)
    assert c.model_name == "Battery"
    assert c.threshold == 20.0
    assert c.comparison == ">"

# -------------------------------------------------------------------------
# Serialization Tests
# -------------------------------------------------------------------------

def test_to_json(science_activity, base_time):
    """Test serialization to dictionary."""
    # Setup complex activity
    child = CommActivity(base_time, timedelta(minutes=5))
    science_activity.add_child(child)
    
    data = science_activity.to_json()
    
    assert data['name'] == "Test Science"
    assert data['type'] == "ScienceActivity"
    assert data['science_mode'] == "high_res" # Subclass specific
    assert len(data['children']) == 1
    assert data['children'][0]['type'] == "CommActivity"

def test_from_json(base_time):
    """Test deserialization from dictionary."""
    data = {
        "type": "ScienceActivity",
        "name": "Restored",
        "begin_time": base_time.isoformat(),
        "duration": "00:30:00",
        "science_mode": "safe_mode",
        "children": [
            {
                "type": "CommActivity",
                "name": "Restored Child",
                "begin_time": base_time.isoformat()
            }
        ]
    }
    
    act = ScienceActivity.from_json(data)
    
    assert isinstance(act, ScienceActivity)
    assert act.name == "Restored"
    assert act.duration == timedelta(minutes=30)
    assert act.metadata['science_mode'] == "safe_mode"
    assert len(act.activities) == 1
    assert act.activities[0].name == "Restored Child"

def test_claim_class():
    """Test the Claim class."""
    # Create claim without metadata
    claim1 = Claim(Claimables.CPU)
    assert claim1.resource == Claimables.CPU
    assert claim1.metadata == {}
    
    # Create claim with metadata
    claim2 = Claim("BATTERY", metadata={"unit": "Ah", "voltage": 28})
    assert claim2.resource == "BATTERY"
    assert claim2.metadata['unit'] == "Ah"
    assert claim2.metadata['voltage'] == 28
    
    # Test equality (based on resource only)
    claim3 = Claim(Claimables.CPU, metadata={"different": "metadata"})
    assert claim1 == claim3  # Same resource, different metadata
    
    claim4 = Claim(Claimables.INSTRUMENT)
    assert claim1 != claim4  # Different resources
    
    # Test repr
    assert "Claim(Claimables.CPU)" in repr(claim1)
    assert "metadata" in repr(claim2)
    
    # Test hash (can be used in sets)
    claim_set = {claim1, claim3}  # Should have only 1 element due to equality
    assert len(claim_set) == 1
