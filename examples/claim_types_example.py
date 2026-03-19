"""Example demonstrating EXCLUSIVE vs AVOIDANCE claim types.

This example shows how to use ClaimType.AVOIDANCE to model scenarios where
multiple activities need to avoid a resource without conflicting with each other.
"""

from datetime import datetime, timedelta
from tts_plan.activity import Activity, ClaimType
from tts_plan.scheduler import Scheduler


class ExampleScheduler(Scheduler):
    """Concrete scheduler for this example."""
    
    MISSION = "EXAMPLE"
    
    def build_schedule(self):
        """Not used in this example."""
        pass


class InstrumentActivity(Activity):
    """Activity that uses an instrument."""
    NAME = "Instrument Activity"
    COLOR = "red"
    
    def _from_json_dict(self, json_data):
        pass


class AvoidanceActivity(Activity):
    """Activity that needs to avoid an instrument."""
    NAME = "Avoidance Activity"
    COLOR = "blue"
    
    def _from_json_dict(self, json_data):
        pass


def main():
    """Demonstrate the three-activity scenario: A and B avoid C, but not each other."""
    
    # Create scheduler
    scheduler = ExampleScheduler()
    base_time = datetime(2020, 1, 1, 12, 0, 0)
    
    # Activity C: Uses SHARAD instrument (EXCLUSIVE claim)
    activity_c = InstrumentActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="SHARAD Observation"
    )
    activity_c.add_claim('SHARAD', claim_type=ClaimType.EXCLUSIVE)
    scheduler.add_activity(activity_c)
    
    # Activity A: Needs to avoid SHARAD (AVOIDANCE claim)
    activity_a = AvoidanceActivity(
        begin_time=base_time + timedelta(minutes=20),
        duration=timedelta(hours=1),
        name="Science Observation A"
    )
    activity_a.add_claim('SHARAD', claim_type=ClaimType.AVOIDANCE)
    scheduler.add_activity(activity_a)
    
    # Activity B: Also needs to avoid SHARAD (AVOIDANCE claim)
    activity_b = AvoidanceActivity(
        begin_time=base_time + timedelta(minutes=40),
        duration=timedelta(hours=1),
        name="Science Observation B"
    )
    activity_b.add_claim('SHARAD', claim_type=ClaimType.AVOIDANCE)
    scheduler.add_activity(activity_b)
    
    # Detect conflicts
    scheduler.detect_conflicts()
    
    # Print results
    print("=" * 80)
    print("ClaimType Example: Three-Activity Scenario")
    print("=" * 80)
    print()
    print("Activities:")
    print(f"  C: SHARAD Observation (EXCLUSIVE claim on SHARAD)")
    print(f"     Time: {activity_c.begin_time} - {activity_c.end_time}")
    print()
    print(f"  A: Science Observation A (AVOIDANCE claim on SHARAD)")
    print(f"     Time: {activity_a.begin_time} - {activity_a.end_time}")
    print()
    print(f"  B: Science Observation B (AVOIDANCE claim on SHARAD)")
    print(f"     Time: {activity_b.begin_time} - {activity_b.end_time}")
    print()
    print("-" * 80)
    print(f"Conflicts Detected: {len(scheduler.conflicts)}")
    print("-" * 80)
    
    for i, conflict in enumerate(scheduler.conflicts, 1):
        print(f"{i}. {conflict.activity1.name} ↔ {conflict.activity2.name}")
        print(f"   Resources: {conflict.conflicting_resources}")
        print(f"   Overlap: {conflict.overlap_start} - {conflict.overlap_end}")
        print()
    
    print("=" * 80)
    print("Analysis:")
    print("=" * 80)
    print("✓ Activity A conflicts with Activity C (AVOIDANCE vs EXCLUSIVE)")
    print("✓ Activity B conflicts with Activity C (AVOIDANCE vs EXCLUSIVE)")
    print("✓ Activity A does NOT conflict with Activity B (AVOIDANCE vs AVOIDANCE)")
    print()
    print("This demonstrates how AVOIDANCE claims allow multiple activities")
    print("to avoid a resource without conflicting with each other!")
    print("=" * 80)
    
    # Verify expected behavior
    assert len(scheduler.conflicts) == 2, f"Expected 2 conflicts, got {len(scheduler.conflicts)}"
    
    # Check that we have the right conflicts
    conflict_pairs = {
        (c.activity1.name, c.activity2.name) for c in scheduler.conflicts
    }
    
    expected_conflicts = {
        ("SHARAD Observation", "Science Observation A"),
        ("Science Observation A", "SHARAD Observation"),
        ("SHARAD Observation", "Science Observation B"),
        ("Science Observation B", "SHARAD Observation"),
    }
    
    # At least one of each pair should be present
    assert any(pair in conflict_pairs for pair in [
        ("SHARAD Observation", "Science Observation A"),
        ("Science Observation A", "SHARAD Observation")
    ]), "Missing conflict between C and A"
    
    assert any(pair in conflict_pairs for pair in [
        ("SHARAD Observation", "Science Observation B"),
        ("Science Observation B", "SHARAD Observation")
    ]), "Missing conflict between C and B"
    
    # Make sure A and B don't conflict
    assert ("Science Observation A", "Science Observation B") not in conflict_pairs
    assert ("Science Observation B", "Science Observation A") not in conflict_pairs
    
    print("\n✅ All assertions passed!")


if __name__ == "__main__":
    main()
