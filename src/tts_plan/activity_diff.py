"""
Activity comparison and diffing utilities.

This module provides tools for comparing activity trees, generating
readable differences between activities and their hierarchical structures.
It facilitates testing by allowing detailed comparison between activity 
objects to identify exactly what changed.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Set, Tuple
import json

from tts_plan.activity import Activity


class ActivityDiffResult:
    """Contains the results of an activity comparison."""
    
    def __init__(self):
        """Initialize an empty diff result."""
        self.differences = []
        self.is_identical = True
    
    def add_difference(self, path: str, attr_name: str, left_value: Any, right_value: Any):
        """
        Record a detected difference.
        
        Args:
            path: The path to the activity (with indexes or identifiers)
            attr_name: The name of the attribute that differs
            left_value: The value from the first activity
            right_value: The value from the second activity
        """
        self.differences.append({
            'path': path,
            'attribute': attr_name,
            'left': left_value,
            'right': right_value
        })
        self.is_identical = False
    
    def __bool__(self) -> bool:
        """Convert to boolean - True if differences were found."""
        return not self.is_identical
    
    def __str__(self) -> str:
        """Generate a readable summary of differences."""
        if self.is_identical:
            return "Activity trees are identical"
        
        # Group differences by path to make output more organized
        diff_by_path = {}
        for diff in self.differences:
            path = diff['path']
            if path not in diff_by_path:
                diff_by_path[path] = []
            diff_by_path[path].append(diff)
        
        lines = [f"Activity differences found: {len(self.differences)} total differences"]
        
        # Count special types of differences
        missing_left = sum(1 for d in self.differences if d['attribute'] == 'missing_child_in_left')
        missing_right = sum(1 for d in self.differences if d['attribute'] == 'missing_child_in_right')
        
        if missing_left:
            lines.append(f"  Activities missing in left tree: {missing_left}")
        if missing_right:
            lines.append(f"  Activities missing in right tree: {missing_right}")
        
        lines.append("")
        lines.append("Detailed differences:")
        lines.append("---------------------")
        
        # Output all differences organized by path
        for path, diffs in sorted(diff_by_path.items()):
            lines.append(f"\nPath: {path}")
            for diff in diffs:
                attr = diff['attribute']
                left = diff['left']
                right = diff['right']
                
                # Format special difference types
                if attr == 'child_count':
                    lines.append(f"  Child count differs: {left} vs {right}")
                elif attr == 'missing_child_in_left':
                    lines.append(f"  Child exists only in right: {right}")
                elif attr == 'missing_child_in_right':
                    lines.append(f"  Child exists only in left: {left}")
                else:
                    # Handle datetime objects for better readability
                    if isinstance(left, datetime) and isinstance(right, datetime):
                        diff_sec = abs((left - right).total_seconds())
                        lines.append(f"  {attr}: {left} vs {right} (diff: {diff_sec:.6f} seconds)")
                    else:
                        lines.append(f"  {attr}: {left} vs {right}")
        
        return "\n".join(lines)


def diff_activities(
    left: Activity, 
    right: Activity, 
    ignore_attrs: Optional[Set[str]] = None,
    float_tolerance: float = 1e-10,
    time_tolerance: timedelta = None,
    path: str = ""
) -> ActivityDiffResult:
    """
    Compare two activities and their child hierarchies.
    
    This function recursively compares two activity objects and all their
    children, recording any differences in attributes or structure.
    
    Args:
        left: The first activity to compare
        right: The second activity to compare
        ignore_attrs: Set of attribute names to exclude from comparison
        float_tolerance: Maximum allowable difference for float comparisons
        time_tolerance: Maximum allowable difference for datetime comparisons
        path: Current path in the recursion (used internally)
        
    Returns:
        ActivityDiffResult containing all found differences
    """
    if ignore_attrs is None:
        ignore_attrs = {'uuid'}  # Default to ignoring UUIDs
    
    if time_tolerance is None:
        time_tolerance = timedelta(seconds=0)  # Default to exact time match
    
    result = ActivityDiffResult()
    
    # If path is empty, we're at the root
    if not path:
        path = f"{left.__class__.__name__}"
    
    # Compare basic attributes
    for attr_name in dir(left):
        # Skip private attributes, methods, etc.
        if attr_name.startswith('_') or attr_name in ignore_attrs or callable(getattr(left, attr_name)):
            continue
            
        # Skip child activities list - we handle that separately
        if attr_name == 'activities':
            continue
            
        left_value = getattr(left, attr_name)
        right_value = getattr(right, attr_name)
        
        # Special case for datetime objects - use time tolerance
        if isinstance(left_value, datetime) and isinstance(right_value, datetime):
            if abs((left_value - right_value).total_seconds()) > time_tolerance.total_seconds():
                result.add_difference(path, attr_name, left_value, right_value)
        
        # Special case for float values - use tolerance
        elif isinstance(left_value, float) and isinstance(right_value, float):
            if abs(left_value - right_value) > float_tolerance:
                result.add_difference(path, attr_name, left_value, right_value)
                
        # Regular value comparison
        elif left_value != right_value:
            result.add_difference(path, attr_name, left_value, right_value)
    
    # Compare child activities using a smarter matching algorithm
    left_children = left.activities
    right_children = right.activities

    # Check for count difference first
    if len(left_children) != len(right_children):
        result.add_difference(
            path, 
            "child_count", 
            len(left_children),
            len(right_children)
        )

    # Try to match children by type and name first
    left_children_by_key = {f"{c.__class__.__name__}:{c.name}": c for c in left_children}
    right_children_by_key = {f"{c.__class__.__name__}:{c.name}": c for c in right_children}
    
    # Create name-only dictionaries for special case matching (like keepout activities)
    # This is needed because when activities are serialized to JSON and then deserialized,
    # For these special activities, we'll match by name only to avoid spurious differences.
    left_children_by_name = {}
    right_children_by_name = {}
    
    # Find children only in left
    for key, child in left_children_by_key.items():
        if key not in right_children_by_key:
            # For keepout activities, check if the name exists in right_children_by_name
            
            result.add_difference(
                path,
                "missing_child_in_right",
                f"{child.__class__.__name__}:{child.name}",
                "None"
            )

    # Find children only in right
    for key, child in right_children_by_key.items():
        if key not in left_children_by_key:
            # For keepout activities, check if the name exists in left_children_by_name
                
            result.add_difference(
                path,
                "missing_child_in_left",
                "None",
                f"{child.__class__.__name__}:{child.name}"
            )

    # Compare matching children
    for key in set(left_children_by_key.keys()) & set(right_children_by_key.keys()):
        left_child = left_children_by_key[key]
        right_child = right_children_by_key[key]
        child_path = f"{path}/{key}"
        
        child_result = diff_activities(
            left_child,
            right_child,
            ignore_attrs,
            float_tolerance,
            time_tolerance,
            child_path
        )
        
        # Merge child differences into this result
        if not child_result.is_identical:
            result.differences.extend(child_result.differences)
            result.is_identical = False
    
    # Also compare keepout activities that match by name only
    for name in set(left_children_by_name.keys()) & set(right_children_by_name.keys()):
        # Skip if we already compared these activities by their full key
        left_child = left_children_by_name[name]
        right_child = right_children_by_name[name]
        
        left_key = f"{left_child.__class__.__name__}:{left_child.name}"
        right_key = f"{right_child.__class__.__name__}:{right_child.name}"
        
        # Only compare if we haven't already compared them by their full key
        if left_key in left_children_by_key and right_key in right_children_by_key and left_key == right_key:
            continue
            
        child_path = f"{path}/{name}"
        
        child_result = diff_activities(
            left_child,
            right_child,
            ignore_attrs,
            float_tolerance,
            time_tolerance,
            child_path
        )
        
        # Merge child differences into this result
        if not child_result.is_identical:
            result.differences.extend(child_result.differences)
            result.is_identical = False
    
    return result


# Add the diff method to the Activity class
def _activity_diff(
    self,
    other: 'Activity',
    ignore_attrs: Optional[Set[str]] = None,
    float_tolerance: float = 1e-10,
    time_tolerance: Optional[timedelta] = None
) -> ActivityDiffResult:
    """
    Compare this activity with another and return their differences.
    
    Args:
        other: The activity to compare against
        ignore_attrs: Set of attribute names to ignore during comparison
        float_tolerance: Maximum allowable difference for float values
        time_tolerance: Maximum allowable difference for datetime values
            
    Returns:
        ActivityDiffResult containing all differences between the activities
    """
    return diff_activities(
        self, other, 
        ignore_attrs=ignore_attrs,
        float_tolerance=float_tolerance,
        time_tolerance=time_tolerance
    )

# Monkey-patch the Activity class to add the diff method
Activity.diff = _activity_diff
