"""
Example demonstrating conflict detection with the Conflict class.

The detect_conflicts() method returns a list of Conflict objects that provide
detailed information about each conflict including:
- Direct references to both conflicting Activity objects
- UUIDs of both conflicting activities (via properties)
- Which resources are in conflict
- The temporal overlap period and duration
"""

from datetime import datetime, timedelta
from enum import Enum, auto
from tts_plan.activity import Activity
from tts_plan.scheduler import Scheduler, ConflictActivity


class MyClaimables(Enum):
    """Example claimable resources."""
    CPU = auto()
    TRANSMITTER = auto()
    INSTRUMENT_A = auto()
    INSTRUMENT_B = auto()


class SimpleScheduler(Scheduler):
    """Simple scheduler for demonstration."""
    MISSION = "Example"
    
    def build_schedule(self):
        """Not needed for this example - we'll manually add activities."""
        pass


def example_basic_conflict_detection():
    """Detect conflicts between overlapping activities."""
    print("=" * 60)
    print("BASIC CONFLICT DETECTION")
    print("=" * 60)
    
    scheduler = SimpleScheduler(
        start_time=datetime(2026, 1, 1, 10, 0, 0),
        end_time=datetime(2026, 1, 1, 12, 0, 0)
    )
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Create two activities that overlap and claim the same resource
    activity1 = Activity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="CPU Task 1"
    )
    activity1.add_claim(MyClaimables.CPU)
    
    activity2 = Activity(
        begin_time=base_time + timedelta(minutes=15),  # Overlaps with activity1
        duration=timedelta(minutes=30),
        name="CPU Task 2"
    )
    activity2.add_claim(MyClaimables.CPU)
    
    scheduler.add_activity(activity1)
    scheduler.add_activity(activity2)
    
    # Detect conflicts
    conflicts = scheduler.detect_conflicts()
    
    print(f"\nScheduled {len(scheduler.activities)} activities")
    print(f"Found {len(conflicts)} conflict(s)\n")
    
    if conflicts:
        for conflict in conflicts:
            print(f"Conflict Details:")
            print(f"  Activity 1: {conflict.activity1.name} (UUID: {conflict.activity1_uuid})")
            print(f"  Activity 2: {conflict.activity2.name} (UUID: {conflict.activity2_uuid})")
            print(f"  Conflicting resources: {conflict.conflicting_resources}")
            print(f"  Overlap period: {conflict.overlap_start} to {conflict.overlap_end}")
            print(f"  Overlap duration: {conflict.overlap_duration}")
            print(f"  Direct access: '{conflict.activity1.name}' vs '{conflict.activity2.name}'")
    
    print("\n✓ Conflict detected and reported\n")


def example_no_conflict_different_resources():
    """No conflict when activities claim different resources."""
    print("=" * 60)
    print("NO CONFLICT - DIFFERENT RESOURCES")
    print("=" * 60)
    
    scheduler = SimpleScheduler(
        start_time=datetime(2026, 1, 1, 10, 0, 0),
        end_time=datetime(2026, 1, 1, 12, 0, 0)
    )
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Two overlapping activities with different resources
    activity1 = Activity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="CPU Task"
    )
    activity1.add_claim(MyClaimables.CPU)
    
    activity2 = Activity(
        begin_time=base_time + timedelta(minutes=15),  # Overlaps
        duration=timedelta(minutes=30),
        name="Transmitter Task"
    )
    activity2.add_claim(MyClaimables.TRANSMITTER)  # Different resource
    
    scheduler.add_activity(activity1)
    scheduler.add_activity(activity2)
    
    conflicts = scheduler.detect_conflicts()
    
    print(f"\nScheduled {len(scheduler.activities)} overlapping activities")
    print(f"Activity 1: {activity1.name} claims {[c.resource for c in activity1.claims]}")
    print(f"Activity 2: {activity2.name} claims {[c.resource for c in activity2.claims]}")
    print(f"Found {len(conflicts)} conflict(s)")
    
    print("\n✓ No conflicts - different resources\n")


def example_multiple_conflicts():
    """Multiple conflicts in a complex schedule."""
    print("=" * 60)
    print("MULTIPLE CONFLICTS")
    print("=" * 60)
    
    scheduler = SimpleScheduler(
        start_time=datetime(2026, 1, 1, 10, 0, 0),
        end_time=datetime(2026, 1, 1, 12, 0, 0)
    )
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Create several activities with overlapping claims
    activities = [
        ("Task A", base_time, 20, MyClaimables.CPU),
        ("Task B", base_time + timedelta(minutes=10), 20, MyClaimables.CPU),  # Conflicts with A
        ("Task C", base_time + timedelta(minutes=15), 20, MyClaimables.CPU),  # Conflicts with A and B
        ("Task D", base_time, 30, MyClaimables.INSTRUMENT_A),
        ("Task E", base_time + timedelta(minutes=15), 20, MyClaimables.INSTRUMENT_A),  # Conflicts with D
    ]
    
    for name, start, duration_mins, resource in activities:
        activity = Activity(
            begin_time=start,
            duration=timedelta(minutes=duration_mins),
            name=name
        )
        activity.add_claim(resource)
        scheduler.add_activity(activity)
    
    conflicts = scheduler.detect_conflicts()
    
    print(f"\nScheduled {len(scheduler.activities)} activities")
    print(f"Found {len(conflicts)} conflict(s)\n")
    
    for i, conflict in enumerate(conflicts, 1):
        resources_str = ', '.join(str(r) for r in conflict.conflicting_resources)
        
        print(f"Conflict {i}:")
        print(f"  '{conflict.activity1.name}' vs '{conflict.activity2.name}'")
        print(f"  Resource(s): {resources_str}")
        print(f"  Overlap: {conflict.overlap_duration}")
        print()
    
    print("✓ Multiple conflicts detected\n")


def example_conflict_with_multiple_resources():
    """Conflict where multiple resources overlap."""
    print("=" * 60)
    print("CONFLICT WITH MULTIPLE RESOURCES")
    print("=" * 60)
    
    scheduler = SimpleScheduler(
        start_time=datetime(2026, 1, 1, 10, 0, 0),
        end_time=datetime(2026, 1, 1, 12, 0, 0)
    )
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Activity claiming multiple resources
    activity1 = Activity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="Complex Task 1"
    )
    activity1.add_claim(MyClaimables.CPU)
    activity1.add_claim(MyClaimables.TRANSMITTER)
    
    # Another activity claiming some of the same resources
    activity2 = Activity(
        begin_time=base_time + timedelta(minutes=15),
        duration=timedelta(minutes=30),
        name="Complex Task 2"
    )
    activity2.add_claim(MyClaimables.CPU)
    activity2.add_claim(MyClaimables.INSTRUMENT_A)  # Different
    
    scheduler.add_activity(activity1)
    scheduler.add_activity(activity2)
    
    conflicts = scheduler.detect_conflicts()
    
    print(f"\nFound {len(conflicts)} conflict(s)")
    
    if conflicts:
        conflict = conflicts[0]
        
        print(f"\nActivity 1: {conflict.activity1.name}")
        print(f"  Claims: {[c.resource for c in conflict.activity1.claims]}")
        print(f"\nActivity 2: {conflict.activity2.name}")
        print(f"  Claims: {[c.resource for c in conflict.activity2.claims]}")
        print(f"\nConflicting resources: {conflict.conflicting_resources}")
        print(f"Overlap duration: {conflict.overlap_duration}")
    
    print("\n✓ Multi-resource conflict detected\n")


def example_conflict_report():
    """Generate formatted conflict reports."""
    print("=" * 60)
    print("CONFLICT REPORT GENERATION")
    print("=" * 60)
    
    scheduler = SimpleScheduler(
        start_time=datetime(2026, 1, 1, 10, 0, 0),
        end_time=datetime(2026, 1, 1, 12, 0, 0)
    )
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Create several activities with conflicts
    activities = [
        ("Science Observation A", base_time, 30, MyClaimables.INSTRUMENT_A),
        ("Science Observation B", base_time + timedelta(minutes=15), 30, MyClaimables.INSTRUMENT_A),
        ("Data Downlink", base_time + timedelta(minutes=20), 25, MyClaimables.TRANSMITTER),
        ("Battery Charge", base_time + timedelta(minutes=10), 40, MyClaimables.TRANSMITTER),
        ("CPU Task 1", base_time, 20, MyClaimables.CPU),
        ("CPU Task 2", base_time + timedelta(minutes=10), 20, MyClaimables.CPU),
    ]
    
    for name, start, duration_mins, resource in activities:
        activity = Activity(
            begin_time=start,
            duration=timedelta(minutes=duration_mins),
            name=name
        )
        activity.add_claim(resource)
        scheduler.add_activity(activity)
    
    # Generate text report
    print("\n--- TEXT FORMAT REPORT ---\n")
    text_report = scheduler.create_conflict_report(format="text")
    print(text_report)
    
    # Generate markdown report
    print("\n--- MARKDOWN FORMAT REPORT ---\n")
    markdown_report = scheduler.create_conflict_report(format="markdown")
    print(markdown_report)
    
    print("✓ Conflict reports generated\n")


def example_conflict_activities():
    """Create ConflictActivity instances for Gantt chart visualization."""
    print("=" * 60)
    print("CONFLICT ACTIVITIES FOR GANTT CHART")
    print("=" * 60)
    
    scheduler = SimpleScheduler(
        start_time=datetime(2026, 1, 1, 10, 0, 0),
        end_time=datetime(2026, 1, 1, 12, 0, 0)
    )
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Create conflicting activities
    a1 = Activity(base_time, timedelta(minutes=30), name="Task A")
    a1.add_claim(MyClaimables.CPU)
    
    a2 = Activity(base_time + timedelta(minutes=15), timedelta(minutes=30), name="Task B")
    a2.add_claim(MyClaimables.CPU)
    
    a3 = Activity(base_time + timedelta(minutes=40), timedelta(minutes=20), name="Task C")
    a3.add_claim(MyClaimables.TRANSMITTER)
    
    a4 = Activity(base_time + timedelta(minutes=45), timedelta(minutes=25), name="Task D")
    a4.add_claim(MyClaimables.TRANSMITTER)
    
    scheduler.add_activity(a1)
    scheduler.add_activity(a2)
    scheduler.add_activity(a3)
    scheduler.add_activity(a4)
    
    print(f"\nInitial activities: {len(scheduler.activities)}")
    
    # Add conflict activities to the schedule
    conflict_activities = scheduler.add_conflict_activities()
    
    print(f"After adding conflicts: {len(scheduler.activities)} activities")
    print(f"Created {len(conflict_activities)} conflict visualization activities\n")
    
    for conflict_activity in conflict_activities:
        print(f"ConflictActivity:")
        print(f"  Name: {conflict_activity.name}")
        print(f"  Time: {conflict_activity.begin_time} to {conflict_activity.end_time}")
        print(f"  Duration: {conflict_activity.duration}")
        print(f"  Color: {conflict_activity.color}")
        print(f"  Full Height: {conflict_activity.highlight_full_height}")
        print(f"  Activities: {conflict_activity.conflict.activity1.name} vs {conflict_activity.conflict.activity2.name}")
        print()
    
    print("✓ Conflict activities ready for Gantt chart visualization\n")


if __name__ == "__main__":
    example_basic_conflict_detection()
    example_no_conflict_different_resources()
    example_multiple_conflicts()
    example_conflict_with_multiple_resources()
    example_conflict_report()
    example_conflict_activities()
    
    print("=" * 60)
    print("All conflict detection examples completed!")
    print("=" * 60)
