"""
Test the activity diffing functionality.
"""

import pytest
from datetime import datetime, timedelta

from tts_plan.activity import Activity
from tts_plan.activity_diff import diff_activities


class SimpleActivity(Activity):
    """Simple activity implementation for testing."""
    TYPE = "SIMPLE"
    NAME = "Simple Activity"
    DESCRIPTION = "A simple activity for testing"
    COLOR = "blue"


class ChildActivity(Activity):
    """Child activity implementation for testing."""
    TYPE = "CHILD"
    NAME = "Child Activity"
    DESCRIPTION = "A child activity for testing"
    COLOR = "green"


class GrandchildActivity(Activity):
    """Grandchild activity implementation for testing."""
    TYPE = "GRANDCHILD"
    NAME = "Grandchild Activity"
    DESCRIPTION = "A grandchild activity for testing"
    COLOR = "yellow"


@pytest.fixture
def base_time():
    """Provide a common base time for tests."""
    return datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture
def identical_activities(base_time):
    """Create two identical activities with identical children for testing."""
    # Create identical activities
    act1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="Test Activity",
        description="Activity for testing"
    )
    
    act2 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="Test Activity",
        description="Activity for testing"
    )
    
    # Add identical children
    child1 = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=10),
        name="Child 1"
    )
    
    child2 = ChildActivity(
        begin_time=base_time + timedelta(minutes=10),
        duration=timedelta(minutes=10),
        name="Child 2"
    )
    
    act1.activities = [child1, child2]
    
    child1_copy = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=10),
        name="Child 1"
    )
    
    child2_copy = ChildActivity(
        begin_time=base_time + timedelta(minutes=10),
        duration=timedelta(minutes=10),
        name="Child 2"
    )
    
    act2.activities = [child1_copy, child2_copy]
    
    return act1, act2
    
def test_identical_activities(identical_activities):
    """Test comparing identical activities."""
    act1, act2 = identical_activities
    result = act1.diff(act2)
    assert result.is_identical
    assert len(result.differences) == 0
    
def test_different_name(identical_activities):
    """Test comparing activities with different names."""
    act1, act2 = identical_activities
    act2.name = "Changed Name"
    result = act1.diff(act2)
    assert not result.is_identical
    assert len(result.differences) == 1
    assert result.differences[0]['attribute'] == 'name'
    
def test_different_child_attribute(identical_activities):
    """Test comparing activities with a difference in a child."""
    act1, act2 = identical_activities
    
    # Store the original name for verification
    original_name = act2.activities[1].name
    
    # Change the name of the second child
    act2.activities[1].name = "Changed Child Name"
    result = act1.diff(act2)
    assert not result.is_identical
    
    # The diff will report missing children in both trees since the names changed
    # and our matching uses type+name as key
    expected_diffs = [
        {
            'attribute': 'missing_child_in_left',
            'right_value': f"ChildActivity:Changed Child Name",
            'parent_path': 'SimpleActivity'
        },
        {
            'attribute': 'missing_child_in_right',
            'left_value': f"ChildActivity:{original_name}",
            'parent_path': 'SimpleActivity'
        }
    ]
    
    # Verify each expected difference is in the results
    for expected in expected_diffs:
        found = False
        for diff in result.differences:
            if diff['attribute'] == expected['attribute']:
                if expected['attribute'] == 'missing_child_in_left':
                    if diff['right'] == expected['right_value'] and expected['parent_path'] in diff['path']:
                        found = True
                        break
                elif expected['attribute'] == 'missing_child_in_right':
                    if diff['left'] == expected['left_value'] and expected['parent_path'] in diff['path']:
                        found = True
                        break
        
        assert found, f"Expected difference not found: {expected['attribute']} with correct value"
    
def test_different_child_time(identical_activities, base_time):
    """Test comparing activities with different child timing."""
    act1, act2 = identical_activities
    # Change the start time of the second child
    act2.activities[1].begin_time = base_time + timedelta(minutes=15)
    result = act1.diff(act2)
    assert not result.is_identical
    
    # Check for specific begin_time difference in the child
    # Get the name of the child we changed for path verification
    child_name = act2.activities[1].name
    
    # We expect a begin_time difference specifically for this child
    found = False
    expected_path_contains = f"ChildActivity:{child_name}"
    
    for diff in result.differences:
        if (diff['attribute'] == 'begin_time' and 
            expected_path_contains in diff['path']):
            found = True
            break
            
    assert found, f"Should detect begin_time difference in path containing {expected_path_contains}"
    
def test_time_tolerance(identical_activities, base_time):
    """Test that time tolerance works."""
    act1, act2 = identical_activities
    # Change the start time by a small amount
    act2.begin_time = base_time + timedelta(seconds=5)
    
    # Without tolerance, should detect the difference
    result = act1.diff(act2)
    assert not result.is_identical
    
    # With sufficient tolerance, should ignore the difference
    result = act1.diff(act2, time_tolerance=timedelta(seconds=10))
    assert result.is_identical
    
def test_ignore_attributes(identical_activities):
    """Test that ignored attributes are skipped."""
    act1, act2 = identical_activities
    # Change color which we'll ignore
    act2.color = "red"
    
    # Without ignoring, should detect the difference
    result = act1.diff(act2)
    assert not result.is_identical
    
    # With ignore, should not detect the difference
    result = act1.diff(act2, ignore_attrs={'color', 'uuid'})
    assert result.is_identical


def test_parent_attribute_differences(base_time):
    """Test detecting multiple attribute differences in the parent activity."""
    # Create new activities for this test
    parent1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="Parent",
        description="Original description",
        color="blue"
    )
    
    parent2 = SimpleActivity(
        begin_time=base_time + timedelta(minutes=5),  # Different start time
        duration=timedelta(minutes=40),              # Different duration
        name="Parent",                               # Same name
        description="Modified description",           # Different description
        color="red"                                 # Different color
    )
    
    result = parent1.diff(parent2)
    
    # Should find at least 4 differences (begin_time, duration, description, color)
    assert not result.is_identical
    assert len(result.differences) >= 4
    
    # Verify we found each specific difference
    attrs_with_diffs = [diff['attribute'] for diff in result.differences]
    assert 'begin_time' in attrs_with_diffs
    assert 'duration' in attrs_with_diffs
    assert 'description' in attrs_with_diffs
    assert 'color' in attrs_with_diffs
    
def test_child_attribute_differences(base_time):
    """Test detecting attribute differences in child activities."""
    # Create fresh activities with children
    parent1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="Parent"
    )
    
    child1 = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=15),
        name="Child",
        description="Original child description"
    )
    
    parent1.activities = [child1]
    
    # Create second activity with same structure but different child attribute
    parent2 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="Parent"
    )
    
    child2 = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=20),  # Different duration
        name="Child",
        description="Modified child description"  # Different description
    )
    
    parent2.activities = [child2]
    
    result = parent1.diff(parent2)
    
    # Check that the differences are correctly identified
    assert not result.is_identical
    
    # Expected differences with their specific paths
    expected_diffs = [
        {'path_contains': 'ChildActivity:Child', 'attribute': 'duration'},
        {'path_contains': 'ChildActivity:Child', 'attribute': 'description'}
    ]
    
    # Verify each expected difference is in the results with the correct path
    for expected in expected_diffs:
        found = False
        for diff in result.differences:
            # Check that the path contains the expected child identifier and the attribute matches
            if (expected['path_contains'] in diff['path'] and 
                diff['attribute'] == expected['attribute']):
                found = True
                break
        
        assert found, f"Expected difference not found: {expected['attribute']} in path containing {expected['path_contains']}"
    
def test_grandchild_attribute_differences(base_time):
    """Test detecting differences in grandchild activities."""
    # Create a three-level activity hierarchy
    parent1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=60),
        name="Parent"
    )
    
    child1 = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="Child"
    )
    
    grandchild1 = GrandchildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=15),
        name="Grandchild",
        description="Original grandchild description"
    )
    
    child1.activities = [grandchild1]
    parent1.activities = [child1]
    
    # Create second hierarchy with modified grandchild
    parent2 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=60),
        name="Parent"
    )
    
    child2 = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=30),
        name="Child"
    )
    
    grandchild2 = GrandchildActivity(
        begin_time=base_time + timedelta(minutes=5),  # Different start time
        duration=timedelta(minutes=10),               # Different duration
        name="Grandchild",
        description="Modified grandchild description"  # Different description
    )
    
    child2.activities = [grandchild2]
    parent2.activities = [child2]
    
    result = parent1.diff(parent2)
    
    # Should find 3 differences in the grandchild
    assert not result.is_identical
    assert len(result.differences) == 3
    
    # Expected differences with their specific paths and attributes
    expected_diffs = [
        {'path_contains': 'GrandchildActivity:Grandchild', 'attribute': 'begin_time'},
        {'path_contains': 'GrandchildActivity:Grandchild', 'attribute': 'duration'},
        {'path_contains': 'GrandchildActivity:Grandchild', 'attribute': 'description'}
    ]
    
    # Verify each expected difference is in the results with the correct path
    for expected in expected_diffs:
        found = False
        for diff in result.differences:
            # Check that the path contains the expected grandchild identifier and the attribute matches
            if (expected['path_contains'] in diff['path'] and 
                diff['attribute'] == expected['attribute']):
                found = True
                break
        
        assert found, f"Expected difference not found: {expected['attribute']} in path containing {expected['path_contains']}"
    
def test_added_removed_children(base_time):
    """Test detecting added and removed children."""
    # Create parent with three children
    parent1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=60),
        name="Parent"
    )
    
    child1 = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=20),
        name="Child 1"
    )
    
    child2 = ChildActivity(
        begin_time=base_time + timedelta(minutes=20),
        duration=timedelta(minutes=20),
        name="Child 2"
    )
    
    child3 = ChildActivity(
        begin_time=base_time + timedelta(minutes=40),
        duration=timedelta(minutes=20),
        name="Child 3"
    )
    
    parent1.activities = [child1, child2, child3]
    
    # Create second parent with first and third child only, plus a new fourth child
    parent2 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=60),
        name="Parent"
    )
    
    child1_copy = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=20),
        name="Child 1"
    )
    
    child3_copy = ChildActivity(
        begin_time=base_time + timedelta(minutes=40),
        duration=timedelta(minutes=20),
        name="Child 3"
    )
    
    child4 = ChildActivity(
        begin_time=base_time + timedelta(minutes=60),
        duration=timedelta(minutes=20),
        name="Child 4"  # This is a new child
    )
    
    parent2.activities = [child1_copy, child3_copy, child4]
    
    result = parent1.diff(parent2)
    
    # Should not be identical
    assert not result.is_identical
    
    # Expected differences with their specific attributes and values
    expected_diffs = [
        {
            'attribute': 'missing_child_in_left',
            'right_value': "ChildActivity:Child 4",
            'parent_path_contains': 'SimpleActivity'
        },
        {
            'attribute': 'missing_child_in_right',
            'left_value': "ChildActivity:Child 2",
            'parent_path_contains': 'SimpleActivity'
        }
    ]
    
    # Verify each expected difference is in the results
    for expected in expected_diffs:
        found = False
        for diff in result.differences:
            # Check attribute and value match, and the path contains the parent identifier
            if (diff['attribute'] == expected['attribute'] and
                expected['parent_path_contains'] in diff['path']):
                
                # Check specific value depending on which attribute we're checking
                if expected['attribute'] == 'missing_child_in_left':
                    if diff['right'] == expected['right_value']:
                        found = True
                        break
                elif expected['attribute'] == 'missing_child_in_right':
                    if diff['left'] == expected['left_value']:
                        found = True
                        break
        
        attr_name = expected['attribute']
        assert found, f"Expected difference not found: {attr_name} with correct value in path containing {expected['parent_path_contains']}"
    
def test_added_removed_grandchildren(base_time):
    """Test detecting added and removed grandchildren."""
    # Create a hierarchy with multiple grandchildren
    parent1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=60),
        name="Parent"
    )
    
    child1 = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=60),
        name="Child"
    )
    
    gc1 = GrandchildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=20),
        name="Grandchild 1"
    )
    
    gc2 = GrandchildActivity(
        begin_time=base_time + timedelta(minutes=20),
        duration=timedelta(minutes=20),
        name="Grandchild 2"
    )
    
    gc3 = GrandchildActivity(
        begin_time=base_time + timedelta(minutes=40),
        duration=timedelta(minutes=20),
        name="Grandchild 3"
    )
    
    child1.activities = [gc1, gc2, gc3]
    parent1.activities = [child1]
    
    # Create second hierarchy with different grandchildren
    parent2 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(minutes=60),
        name="Parent"
    )
    
    child2 = ChildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=60),
        name="Child"
    )
    
    gc1_copy = GrandchildActivity(
        begin_time=base_time,
        duration=timedelta(minutes=20),
        name="Grandchild 1"
    )
    
    # Skip gc2 - it's removed
    
    gc3_copy = GrandchildActivity(
        begin_time=base_time + timedelta(minutes=40),
        duration=timedelta(minutes=20),
        name="Grandchild 3"
    )
    
    gc4 = GrandchildActivity(
        begin_time=base_time + timedelta(minutes=60),
        duration=timedelta(minutes=20),
        name="Grandchild 4"  # This is a new grandchild
    )
    
    child2.activities = [gc1_copy, gc3_copy, gc4]
    parent2.activities = [child2]
    
    result = parent1.diff(parent2)
    
    # Should not be identical
    assert not result.is_identical
    
    # Expected differences with their specific attributes and values
    expected_diffs = [
        {
            'attribute': 'missing_child_in_left',
            'right_value': "GrandchildActivity:Grandchild 4",
            'parent_path_contains': 'ChildActivity'
        },
        {
            'attribute': 'missing_child_in_right',
            'left_value': "GrandchildActivity:Grandchild 2",
            'parent_path_contains': 'ChildActivity'
        }
    ]
    
    # Verify each expected difference is in the results
    for expected in expected_diffs:
        found = False
        for diff in result.differences:
            # Check attribute and value match, and the path contains the parent identifier
            if (diff['attribute'] == expected['attribute'] and
                expected['parent_path_contains'] in diff['path']):
                
                # Check specific value depending on which attribute we're checking
                if expected['attribute'] == 'missing_child_in_left':
                    if diff['right'] == expected['right_value']:
                        found = True
                        break
                elif expected['attribute'] == 'missing_child_in_right':
                    if diff['left'] == expected['left_value']:
                        found = True
                        break
        
        attr_name = expected['attribute']
        assert found, f"Expected difference not found: {attr_name} with correct value in path containing {expected['parent_path_contains']}"


# No need for main block in pytest
