import pytest
import json
import os
from datetime import datetime, timedelta

# Assumes scheduler.py and activity.py are available in the python path
from tts_plan.scheduler import Scheduler, BelowTheFoldContainer
from tts_plan.activity import Activity, Claimables

# -------------------------------------------------------------------------
# Helpers / Fixtures
# -------------------------------------------------------------------------

class TestMissionScheduler(Scheduler):
    """Concrete implementation of Scheduler for testing."""
    MISSION = "TEST_MISSION"

    def build_schedule(self) -> list:
        # Simple implementation for testing
        return self.activities

@pytest.fixture
def start_time():
    return datetime(2026, 1, 20, 12, 0, 0)

@pytest.fixture
def end_time():
    return datetime(2026, 1, 21, 12, 0, 0)

@pytest.fixture
def scheduler(start_time, end_time):
    return TestMissionScheduler(start_time=start_time, end_time=end_time)

# -------------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------------

def test_initialization(scheduler, start_time):
    """Test scheduler initialization."""
    assert scheduler.mission == "TEST_MISSION"
    assert scheduler.start_time == start_time
    assert scheduler.activities == []

def test_add_activity(scheduler, start_time):
    """Test adding activities to normal and below-the-fold lists."""
    act1 = Activity(start_time, timedelta(minutes=10), name="Normal")
    act2 = Activity(start_time, timedelta(minutes=10), name="Hidden", below_the_fold=True)

    scheduler.add_activity(act1)
    scheduler.add_activity(act2)

    assert act1 in scheduler.activities
    assert act2 not in scheduler.activities
    assert act2 in scheduler.below_the_fold_activities

def test_get_activities_in_timerange(scheduler, start_time):
    """Test filtering activities by time range."""
    t0 = start_time
    # Activity 1: 12:00 - 12:10
    a1 = Activity(t0, timedelta(minutes=10), name="A1")
    # Activity 2: 12:30 - 12:40
    a2 = Activity(t0 + timedelta(minutes=30), timedelta(minutes=10), name="A2")
    # Activity 3: 13:00 - 13:10
    a3 = Activity(t0 + timedelta(hours=1), timedelta(minutes=10), name="A3")

    scheduler.add_activity(a1)
    scheduler.add_activity(a2)
    scheduler.add_activity(a3)

    # Query range: 12:15 to 12:45 (Should only catch A2)
    range_start = t0 + timedelta(minutes=15)
    range_end = t0 + timedelta(minutes=45)

    results = scheduler.get_activities_in_timerange(range_start, range_end)

    assert len(results) == 1
    assert results[0].name == "A2"

def test_conflict_detection_no_conflict(scheduler, start_time):
    """Test that non-overlapping activities do not conflict."""
    a1 = Activity(start_time, timedelta(minutes=10), name="A1")
    a1.add_claim(Claimables.CPU)

    a2 = Activity(start_time + timedelta(minutes=20), timedelta(minutes=10), name="A2")
    a2.add_claim(Claimables.CPU)

    scheduler.add_activity(a1)
    scheduler.add_activity(a2)

    conflicts = scheduler.detect_conflicts()
    assert len(conflicts) == 0

def test_conflict_detection_temporal_overlap_different_resources(scheduler, start_time):
    """Test that overlapping activities with different resources do not conflict."""
    a1 = Activity(start_time, timedelta(minutes=10), name="A1")
    a1.add_claim(Claimables.CPU)

    # Starts 5 mins in (overlap)
    a2 = Activity(start_time + timedelta(minutes=5), timedelta(minutes=10), name="A2")
    a2.add_claim(Claimables.XBAND)  # Different resource

    scheduler.add_activity(a1)
    scheduler.add_activity(a2)

    conflicts = scheduler.detect_conflicts()
    assert len(conflicts) == 0

def test_conflict_detection_true_conflict(scheduler, start_time):
    """Test detection of overlap + same resource claim."""
    a1 = Activity(start_time, timedelta(minutes=10), name="A1")
    a1.add_claim(Claimables.CPU)

    # Starts 5 mins in (overlap)
    a2 = Activity(start_time + timedelta(minutes=5), timedelta(minutes=10), name="A2")
    a2.add_claim(Claimables.CPU)  # Same resource

    scheduler.add_activity(a1)
    scheduler.add_activity(a2)

    conflicts = scheduler.detect_conflicts()

    # Should have exactly one conflict
    assert len(conflicts) == 1
    
    conflict = conflicts[0]
    # Check that the conflict involves both activities
    assert {conflict.activity1_uuid, conflict.activity2_uuid} == {a1.uuid, a2.uuid}
    # Check that CPU is the conflicting resource
    assert Claimables.CPU in conflict.conflicting_resources
    # Check overlap times
    assert conflict.overlap_start == start_time + timedelta(minutes=5)
    assert conflict.overlap_end == start_time + timedelta(minutes=10)
    assert conflict.overlap_duration == timedelta(minutes=5)

def test_conflict_report_with_conflicts(scheduler, start_time):
    """Test generating a conflict report with conflicts."""
    a1 = Activity(start_time, timedelta(minutes=20), name="Task A")
    a1.add_claim(Claimables.CPU)
    
    a2 = Activity(start_time + timedelta(minutes=10), timedelta(minutes=20), name="Task B")
    a2.add_claim(Claimables.CPU)
    
    scheduler.add_activity(a1)
    scheduler.add_activity(a2)
    
    # Generate text report
    text_report = scheduler.create_conflict_report(format="text")
    assert "SCHEDULE CONFLICT REPORT" in text_report
    assert "Total Conflicts Found: 1" in text_report
    assert "Task A" in text_report
    assert "Task B" in text_report
    assert "Claimables.CPU" in text_report
    
    # Generate markdown report
    md_report = scheduler.create_conflict_report(format="markdown")
    assert "# Schedule Conflict Report" in md_report
    assert "**Total Conflicts Found:** 1" in md_report
    assert "**Activity 1:** Task A" in md_report or "**Activity 1:** Task B" in md_report

def test_conflict_report_no_conflicts(scheduler, start_time):
    """Test generating a conflict report with no conflicts."""
    a1 = Activity(start_time, timedelta(minutes=10), name="Task A")
    a1.add_claim(Claimables.CPU)
    
    a2 = Activity(start_time + timedelta(minutes=20), timedelta(minutes=10), name="Task B")
    a2.add_claim(Claimables.CPU)
    
    scheduler.add_activity(a1)
    scheduler.add_activity(a2)
    
    # Generate report
    report = scheduler.create_conflict_report()
    assert "No conflicts detected" in report

def test_merge_above_and_below_the_fold(scheduler, start_time):
    """Test merging standard activities with the below-the-fold container."""
    a1 = Activity(start_time, timedelta(minutes=10), name="A1")
    btf1 = Activity(start_time, timedelta(minutes=10), name="BTF1", below_the_fold=True)
    btf2 = Activity(start_time + timedelta(minutes=20), timedelta(minutes=10), name="BTF2", below_the_fold=True)

    scheduler.add_activity(a1)
    scheduler.add_activity(btf1)
    scheduler.add_activity(btf2)

    merged = scheduler.merge_above_and_below_the_fold()

    # Should contain A1 and one BelowTheFoldContainer
    assert len(merged) == 2
    assert merged[0].name == "A1"
    assert isinstance(merged[1], BelowTheFoldContainer)
    # The container should hold the 2 B-T-F activities
    assert len(merged[1].activities) == 2

def test_json_file_io(scheduler, start_time, tmp_path):
    """Test saving scheduler to file and reloading it."""
    # tmp_path is a built-in pytest fixture for temporary directories
    a1 = Activity(start_time, timedelta(minutes=10), name="A1")
    scheduler.add_activity(a1)

    filepath = tmp_path / "schedule.json"
    
    # Save
    scheduler.to_json_file(str(filepath))
    assert filepath.exists()

    # Reload
    loaded_scheduler = TestMissionScheduler.from_json_file(str(filepath))

    assert loaded_scheduler.mission == "TEST_MISSION"
    assert len(loaded_scheduler.activities) == 1
    assert loaded_scheduler.activities[0].name == "A1"
    assert loaded_scheduler.activities[0].begin_time == start_time
