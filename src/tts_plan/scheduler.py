"""
Scheduler module for spacecraft activity planning.

This module provides the framework for generating, managing, and validating
spacecraft activity schedules. It defines the abstract base `Scheduler` class,
which serves as the engine for mission-specific planning logic.

The Scheduler handles:
1. Containerization of activities (managing main schedule vs. "below the fold" items).
2. Time-range filtering and retrieval.
3. Conflict detection (temporal overlap + shared resource claims).
4. Serialization (JSON I/O) with dynamic class resolution.
5. Visualization (ASCII timelines).
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, Type, Tuple
from datetime import datetime, timedelta
import uuid
import json
from pathlib import Path
import importlib
import sys

from tts_utilities.logger import create_logger
from tts_html_utils.core.components.base import HtmlComponent

logger = create_logger(__name__)

from tts_plan.activity import Activity
from tts_plan.modeled_values import ModeledValues
from tts_plan.conflicts import ConflictActivity, Conflict



class BelowTheFoldContainer(Activity):
    """
    Special container activity for grouping modeling-only items taht would otherwise 
    clutter the primary gantt chart when displayed that way.

    This activity is used to wrap multiple "below the fold" activities into a 
    single block for visualization or summary purposes, keeping the main 
    timeline clean.
    """
    BELOW_THE_FOLD = True
    
    def __init__(self, activities: List[Activity]):
        """
        Initialize the container based on a list of activities.

        The container's start time is the start of the first activity, and 
        its duration spans to the start of the last activity (approximation).

        Args:
            activities: List of activities to group.
        """
        super().__init__(
            activities[0].begin_time, 
            activities[-1].begin_time - activities[0].begin_time, 
            name='Below the Fold',
            activities=activities
        )
    

class Scheduler(ABC):
    """
    Abstract Base Class for mission schedulers.

    Subclasses must implement `build_schedule()` to define the specific logic 
    for generating activities (e.g., importing orbit events, calculating 
    slews, creating comm windows).

    Attributes:
        MISSION (str): The identifier for the mission (e.g., "DEMOSAT"). 
            Must be set by subclasses.
        start_time (datetime): The start boundary of the planning horizon.
        end_time (datetime): The end boundary of the planning horizon.
        activities (List[Activity]): The primary list of scheduled activities.
        below_the_fold_activities (List[Activity]): Secondary list of lower 
            priority or background activities.
        metadata (dict): Arbitrary dictionary for scheduler state/configuration.
    """
    MISSION = None
    
    def __init__(self, start_time: datetime = None, end_time: datetime = None, metadata=None):
        """
        Initialize a new Scheduler instance.

        Args:
            start_time: Start time of the scheduling period.
            end_time: End time of the scheduling period.
            metadata: Optional dictionary for subclass-specific configuration 
                or state.

        Raises:
            ValueError: If the subclass does not define a `MISSION` attribute.
        """
        if self.MISSION is None:
            raise ValueError("Scheduler must be initialized with a mission")
        self.mission = self.MISSION
        self.start_time = start_time
        self.end_time = end_time
        self.activities = []
        self.below_the_fold_activities = []
        self.metadata = {} if metadata is None else metadata
        self.modeled_values = ModeledValues()  # System for tracking state variables over time
        self.conflicts = None
        
    @abstractmethod
    def build_schedule(self) -> List[Activity]:
        """
        Generate the activity schedule.

        This abstract method must be implemented by subclasses. It contains the
        core logic to populate `self.activities` based on mission requirements,
        constraints, and external inputs (like ephemeris or ground station
        availability).

        Returns:
            List[Activity]: The list of generated Activity objects.
        """
        pass
    
    def merge_above_and_below_the_fold(self) -> List[Activity]:
        """
        Combine primary activities with a summary container of secondary ones.

        Useful for visualization where you want to see the main schedule alongside
        a collapsed view of background tasks.

        Returns:
            List[Activity]: A list containing all primary activities plus one
            `BelowTheFoldContainer` holding all secondary activities.
        """
        
        return self.activities + [BelowTheFoldContainer(self.below_the_fold_activities)]
    
    def add_activity(self, activity: Activity) -> None:
        """
        Add an activity to the appropriate internal list.

        Checks the `below_the_fold` flag on the activity to determine if it
        belongs in the primary `activities` list or the `below_the_fold_activities`
        list.

        Args:
            activity: The Activity object to add.
        """
        activity.scheduler = self
        if activity.below_the_fold:
            self.below_the_fold_activities.append(activity)
        else:
            self.activities.append(activity)
        
    def get_activities(self) -> List[Activity]:
        """
        Retrieve all primary activities.

        Returns:
            List[Activity]: The list of primary activities.
        """
        return self.activities
    
    def get_activities_by_type(self, activity_type: Type[Activity]) -> List[Activity]:
        """
        Filter primary activities by class type.

        Args:
            activity_type: The class (e.g., `ScienceActivity`) to filter by.
            
        Returns:
            List[Activity]: A list of activities matching the provided type.
        """
        return [a for a in self.activities if isinstance(a, activity_type)]
    
    def get_activities_in_timerange(self, start_time: datetime, end_time: datetime) -> List[Activity]:
        """
        Get all activities that overlap with a specified time range.

        Logic implies strict overlap: The activity must start before the range ends
        AND end after the range starts.

        Args:
            start_time: Start of the query range.
            end_time: End of the query range.
            
        Returns:
            List[Activity]: Activities overlapping the window.
        """
        return [
            activity for activity in self.activities 
            if (activity.begin_time < end_time and activity.end_time > start_time)
        ]

    def get_activities_by_uuid(self, uuid: str) -> List[Activity]:
        """
        Get all activities that have a specified UUID.

        Args:
            uuid: UUID of the activities to retrieve.
            
        Returns:
            List[Activity]: Activities with the specified UUID.
        """
        activities = [
            activity for activity in self.activities 
            if activity.uuid == uuid
        ]
        if len(activities) == 0:
            raise Exception(f"No activities found with UUID {uuid}")
        elif len(activities) > 1:
            raise Exception(f"Multiple activities found with UUID {uuid}")
        return activities[0]

    def visualize_timerange(self, start_time: datetime, end_time: datetime, width: int = 80) -> str:
        """
        Generate an ASCII visualization of activities within a specific window.

        Args:
            start_time: Start of the visualization window.
            end_time: End of the visualization window.
            width: Character width of the ASCII output (default: 80).
            
        Returns:
            str: ASCII timeline string.
        """
        activities = self.get_activities_in_timerange(start_time, end_time)
        
        if not activities:
            return f"No activities found between {start_time} and {end_time}"
        
        # Sort activities by start time
        sorted_activities = sorted(activities, key=lambda a: a.begin_time)
        
        # Create a pseudo-activity to contain all activities in the range
        # This acts as a temporary parent to utilize Activity.ascii_timeline logic
        from tts_plan.activity import Activity
        container = Activity(begin_time=start_time, duration=(end_time - start_time))
        container.name = f"Schedule: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}"
        container.activities = sorted_activities
        
        # Generate the ASCII timeline
        return container.ascii_timeline(width=width, show_time=True)
    
    def detect_conflicts(self) -> List['Conflict']:
        """
        Analyze the schedule for resource conflicts.

        A conflict is defined as two activities that:
        1. Overlap in time.
        2. Claim the same resource (via `activity.claims`).
        
        This method checks ALL activities at ALL levels of the hierarchy,
        not just top-level activities. This allows child activities with
        specific resource claims to be compared against other activities.

        Returns:
            List[Conflict]: List of Conflict objects describing each conflict.
                Each conflict contains UUIDs of both activities, the conflicting
                resources, and the temporal overlap period.
        """
        conflicts = []
        seen_pairs = set()
        
        # Collect all activities at all levels (flatten the hierarchy)
        all_activities = []
        for activity in self.activities:
            all_activities.extend(activity.get_all_descendants())
        
        # Compare each activity with all others (O(N^2) complexity)
        for i, activity1 in enumerate(all_activities):
            for j, activity2 in enumerate(all_activities):
                if i < j:  # Only check each pair once (i < j avoids duplicates)
                    # Check for temporal overlap
                    if (activity1.begin_time < activity2.end_time and 
                        activity1.end_time > activity2.begin_time):
                        
                        # Get conflicting resources
                        conflicting_resources = self._get_conflicting_resources(activity1, activity2)
                        
                        if conflicting_resources:
                            # Calculate overlap period
                            overlap_start = max(activity1.begin_time, activity2.begin_time)
                            overlap_end = min(activity1.end_time, activity2.end_time)
                            
                            conflict = Conflict(
                                activity1=activity1,
                                activity2=activity2,
                                conflicting_resources=conflicting_resources,
                                overlap_start=overlap_start,
                                overlap_end=overlap_end
                            )
                            conflicts.append(conflict)
        self.conflicts = conflicts
        return conflicts
    
    def get_conflicts(self, uuid=None) -> List[Conflict]:
        if self.conflicts is None: return []
        if uuid:
            return [c for c in self.conflicts if c.activity1_uuid == uuid or c.activity2_uuid == uuid]
        return self.conflicts
    
    def create_conflict_report(self, format: str = "text") -> str:
        """
        Generate a formatted report of all schedule conflicts.
        
        Args:
            format: Report format - "text" for human-readable text, "markdown" for markdown format.
            
        Returns:
            str: Formatted conflict report.
        """
        if self.conflicts is None:
            conflicts = self.detect_conflicts()
        else:
            conflicts = self.conflicts
        
        if format == "markdown":
            return self._create_conflict_report_markdown(conflicts)
        else:
            return self._create_conflict_report_text(conflicts)
    
    def _create_conflict_report_text(self, conflicts: List[Conflict]) -> str:
        """Generate a text-based conflict report."""
        lines = []
        lines.append("=" * 80)
        lines.append("SCHEDULE CONFLICT REPORT")
        lines.append("=" * 80)
        lines.append("")
        
        if not conflicts:
            lines.append("✓ No conflicts detected in the schedule.")
            lines.append("")
            return "\n".join(lines)
        
        # Summary
        lines.append(f"Total Conflicts Found: {len(conflicts)}")
        lines.append("")
        
        # Count conflicts by resource
        resource_conflicts = {}
        for conflict in conflicts:
            for resource in conflict.conflicting_resources:
                resource_conflicts[resource] = resource_conflicts.get(resource, 0) + 1
        
        lines.append("Conflicts by Resource:")
        for resource, count in sorted(resource_conflicts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {resource}: {count} conflict(s)")
        lines.append("")
        
        # Detailed conflict list
        lines.append("-" * 80)
        lines.append("DETAILED CONFLICTS")
        lines.append("-" * 80)
        lines.append("")
        
        for i, conflict in enumerate(conflicts, 1):
            lines.append(f"Conflict #{i}")
            lines.append(f"  Activities:")
            lines.append(f"    1. {conflict.activity1.name}")
            lines.append(f"       UUID: {conflict.activity1_uuid}")
            lines.append(f"       Time: {conflict.activity1.begin_time} to {conflict.activity1.end_time}")
            lines.append(f"       Duration: {conflict.activity1.duration}")
            if hasattr(conflict, 'rule_id'):
                lines.append(f"       Rule ID: {conflict.rule_id}")
                lines.append("")

            for k, v in conflict.activity1.metadata.items():
                lines.append(f"       {k}: {v}")
            lines.append(f"")
            lines.append(f"    2. {conflict.activity2.name}")
            lines.append(f"       UUID: {conflict.activity2_uuid}")
            lines.append(f"       Time: {conflict.activity2.begin_time} to {conflict.activity2.end_time}")
            lines.append(f"       Duration: {conflict.activity2.duration}")
            for k, v in conflict.activity2.metadata.items():
                lines.append(f"       {k}: {v}")
            lines.append(f"")
            
            resources_str = ", ".join(str(r) for r in sorted(conflict.conflicting_resources, key=str))
            lines.append(f"  Conflicting Resources: {resources_str}")
            lines.append(f"")
            lines.append(f"  Overlap Period:")
            lines.append(f"    Start: {conflict.overlap_start}")
            lines.append(f"    End:   {conflict.overlap_end}")
            lines.append(f"    Duration: {conflict.overlap_duration}")
            lines.append("")
            lines.append("-" * 80)
            lines.append("")
        
        return "\n".join(lines)
    
    def _create_conflict_report_markdown(self, conflicts: List[Conflict]) -> str:
        """Generate a markdown-formatted conflict report."""
        lines = []
        lines.append("# Schedule Conflict Report")
        lines.append("")
        
        if not conflicts:
            lines.append("✓ **No conflicts detected in the schedule.**")
            lines.append("")
            return "\n".join(lines)
        
        # Summary
        lines.append(f"**Total Conflicts Found:** {len(conflicts)}")
        lines.append("")
        
        # Count conflicts by resource
        resource_conflicts = {}
        for conflict in conflicts:
            for resource in conflict.conflicting_resources:
                resource_conflicts[resource] = resource_conflicts.get(resource, 0) + 1
        
        lines.append("## Conflicts by Resource")
        lines.append("")
        for resource, count in sorted(resource_conflicts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- **{resource}**: {count} conflict(s)")
        lines.append("")
        
        # Detailed conflict list
        lines.append("## Detailed Conflicts")
        lines.append("")
        
        for i, conflict in enumerate(conflicts, 1):
            lines.append(f"### Conflict #{i}")
            lines.append("")
            lines.append("#### Activities")
            lines.append("")
            lines.append(f"**Activity 1:** {conflict.activity1.name}")
            lines.append(f"- UUID: `{conflict.activity1_uuid}`")
            lines.append(f"- Time: {conflict.activity1.begin_time} to {conflict.activity1.end_time}")
            lines.append(f"- Duration: {conflict.activity1.duration}")
            lines.append("")
            
            lines.append(f"**Activity 2:** {conflict.activity2.name}")
            lines.append(f"- UUID: `{conflict.activity2_uuid}`")
            lines.append(f"- Time: {conflict.activity2.begin_time} to {conflict.activity2.end_time}")
            lines.append(f"- Duration: {conflict.activity2.duration}")
            lines.append("")
            
            resources_str = ", ".join(f"`{r}`" for r in sorted(conflict.conflicting_resources, key=str))
            lines.append(f"**Conflicting Resources:** {resources_str}")
            lines.append("")

            if hasattr(conflict, 'rule_id'):
                lines.append(f"**Rule ID:** {conflict.rule_id}")
                lines.append("")

            lines.append("**Overlap Period:**")
            lines.append(f"- Start: {conflict.overlap_start}")
            lines.append(f"- End: {conflict.overlap_end}")
            lines.append(f"- Duration: {conflict.overlap_duration}")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    def add_conflict_activities(self, below_the_fold: bool = False) -> List['ConflictActivity']:
        """
        Create ConflictActivity instances for all conflicts and add them to the schedule.
        
        This allows conflicts to be visualized directly in the Gantt chart.
        
        Args:
            below_the_fold: If True, add conflict activities below the fold. Default False.
            
        Returns:
            List[ConflictActivity]: The conflict activities that were created and added.
        """
        if self.conflicts is None:
            self.detect_conflicts()
        
        conflict_activities = []
        for conflict in self.conflicts:
            conflict_activity = ConflictActivity(conflict, below_the_fold=below_the_fold)
            self.add_activity(conflict_activity)
            conflict_activities.append(conflict_activity)
        
        return conflict_activities

    def detect_model_constraint_violations(self) -> List[Tuple[Activity, 'ModelConstraint', float]]:
        """
        Check all activities for model constraint violations.
        
        This method evaluates each activity's model constraints against the current
        state of the modeled values system. It returns a list of violations where
        an activity's constraints are not satisfied.
        
        Returns:
            List of (activity, constraint, violating_value) tuples for any violations.
            Empty list if all constraints are satisfied or if modeled_values is not set.
            
        Note:
            This requires that the scheduler has a modeled_values instance and that
            compute_profile_from_activities has been called.
        """
        if not hasattr(self, 'modeled_values') or self.modeled_values is None:
            return []
        
        violations = []
        
        # Check all activities at all levels
        all_activities = []
        for activity in self.activities:
            all_activities.extend(activity.get_all_descendants())
        
        for activity in all_activities:
            activity_violations = activity.check_model_constraints(self.modeled_values)
            for constraint, value in activity_violations:
                violations.append((activity, constraint, value))
        
        self.model_constraint_violations = violations
        return violations
    
    def _get_conflicting_resources(self, activity1: Activity, activity2: Activity) -> set:
        """
        Get the set of resources that both activities claim, respecting claim types.

        Args:
            activity1: First activity.
            activity2: Second activity.
            
        Returns:
            set: Set of resources that create conflicts. Empty if no conflicts.
            
        Note:
            This method respects ClaimType:
            - EXCLUSIVE claims conflict with any other claim
            - AVOIDANCE claims only conflict with EXCLUSIVE claims (not with other AVOIDANCE claims)
        """
        from tts_plan.activity import ClaimType
        
        conflicting_resources = set()
        
        # Check each combination of claims
        for claim1 in activity1.claims:
            for claim2 in activity2.claims:
                # Check if they claim the same resource
                if claim1.resource != claim2.resource:
                    continue
                
                # Determine if this combination creates a conflict
                # EXCLUSIVE <-> EXCLUSIVE: conflict
                # EXCLUSIVE <-> AVOIDANCE: conflict
                # AVOIDANCE <-> EXCLUSIVE: conflict
                # AVOIDANCE <-> AVOIDANCE: NO conflict
                if claim1.claim_type == ClaimType.EXCLUSIVE or claim2.claim_type == ClaimType.EXCLUSIVE:
                    conflicting_resources.add(claim1.resource)
        
        return conflicting_resources
    
    def _activities_have_resource_conflict(self, activity1: Activity, activity2: Activity) -> bool:
        """
        Helper method to check if activities have conflicting resource claims.

        Args:
            activity1: First activity.
            activity2: Second activity.
            
        Returns:
            bool: True if they share at least one claimed resource.
        """
        return bool(self._get_conflicting_resources(activity1, activity2))
    
    def activity_conflicts_with_schedule(self, activity: Activity) -> List[Activity]:
        """
        Check if an activity conflicts with any activity already in the schedule.
        
        This is useful for testing whether a new activity can be added to the schedule
        without creating resource conflicts.
        
        Args:
            activity: The activity to check for conflicts.
            
        Returns:
            List[Activity]: A list of activities in the schedule that conflict with the given activity.
                Returns an empty list if there are no conflicts.
        """
        conflicting_activities = []
        
        for scheduled_activity in self.activities:
            if activity.conflicts_with(scheduled_activity):
                conflicting_activities.append(scheduled_activity)
        
        return conflicting_activities
    
    def find_all_conflicts(self) -> List[tuple[Activity, Activity]]:
        """
        Find all pairs of activities in the schedule that have conflicts.
        
        This method is more efficient for batch conflict checking than calling
        conflicts_with on every pair, as it only checks each unique pair once.
        
        Returns:
            List[tuple[Activity, Activity]]: A list of tuples where each tuple contains
                two conflicting activities. Each conflict pair appears only once.
                
        Examples:
            >>> scheduler = MroScheduler(start_time, end_time)
            >>> # ... build schedule ...
            >>> conflicts = scheduler.find_all_conflicts()
            >>> if conflicts:
            ...     print(f"Found {len(conflicts)} conflicts:")
            ...     for act1, act2 in conflicts:
            ...         print(f"  {act1.name} conflicts with {act2.name}")
        """
        conflicts = []
        
        # Only check each pair once (i < j)
        for i in range(len(self.activities)):
            for j in range(i + 1, len(self.activities)):
                activity1 = self.activities[i]
                activity2 = self.activities[j]
                
                if activity1.conflicts_with(activity2):
                    conflicts.append((activity1, activity2))
        
        return conflicts
    
    def compute_model(self, initial_values: Optional[Dict[str, float]] = None):
        """Compute the modeled value profiles based on activity effects.
        
        This walks through all activities in chronological order and applies their
        effects to update the modeled state variables over time.
        
        Args:
            initial_values: Optional dictionary of initial values for modeled variables.
                If not provided, uses the current modeled_values initial_values.
                
        Examples:
            >>> scheduler.compute_model({'battery_charge': 100.0, 'data_volume': 0.0})
            >>> battery_at_noon = scheduler.modeled_values.get_value_at_time('battery_charge', noon_time)
        """
        if initial_values:
            for model_name, value in initial_values.items():
                self.modeled_values.register_model(model_name, value)
        
        # Compute profiles from all activities
        self.modeled_values.compute_profile_from_activities(
            self.activities,
            self.start_time,
            self.end_time
        )
        
    def validate_model_constraints(self, check_descendants: bool = True) -> List[Tuple[Activity, datetime, str]]:
        """Validate all ModeledValueConstraints in the schedule.
        
        This checks all activities with ModeledValueConstraints against the computed
        model to find violations.
        
        Args:
            check_descendants: If True, also check constraints on child activities
            
        Returns:
            List of tuples (activity, time, message) for each violation
            
        Examples:
            >>> scheduler.compute_model({'battery_charge': 100.0})
            >>> violations = scheduler.validate_model_constraints()
            >>> if violations:
            ...     for activity, time, message in violations:
            ...         print(f"{activity.name} at {time}: {message}")
        """
        all_violations = []
        
        for activity in self.activities:
            violations = self.modeled_values.get_constraint_violations(
                activity,
                check_descendants=check_descendants
            )
            all_violations.extend(violations)
        
        return all_violations
    
    def _to_json_dict(self) -> Dict[str, Any]:
        """
        Convert scheduler-specific attributes to a dictionary for JSON serialization.
        
        This method is meant to be overridden by subclasses to add their specific attributes.
        
        Returns:
            Dict[str, Any]: Dictionary with scheduler attributes.
        """
        # Convert datetime objects to ISO format strings for JSON serialization
        start_time_str = self.start_time.isoformat() if self.start_time else None
        end_time_str = self.end_time.isoformat() if self.end_time else None
        
        # Base attributes that all schedulers have
        result = {
            'mission': self.mission,
            'start_time': start_time_str,
            'end_time': end_time_str,
            'scheduler_type': self.__class__.__name__
        }
        
        # Add metadata if present
        if hasattr(self, 'metadata') and self.metadata:
            # Process metadata to ensure it's JSON serializable
            metadata_json = {}
            for key, value in self.metadata.items():
                if hasattr(value, 'to_json') and callable(getattr(value, 'to_json')):
                    metadata_json[key] = value.to_json()
                else:
                    metadata_json[key] = value
            result['metadata'] = metadata_json
            
        return result
    
    def to_json(self) -> Dict[str, Any]:
        """
        Serialize the entire scheduler state to a dictionary.

        This includes scheduler configuration, metadata, and all activities 
        (both primary and below-the-fold).

        Returns:
            Dict[str, Any]: JSON-compatible dictionary.
        """
        # Helper function to convert datetime objects to ISO format strings
        def convert_datetime_to_iso(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_datetime_to_iso(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_datetime_to_iso(item) for item in obj]
            else:
                return obj
        
        # Get scheduler-specific attributes from subclass implementation
        result = self._to_json_dict()
        
        # Convert activities to JSON using their to_json method if available
        activities_json = []
        for activity in self.activities:
            if hasattr(activity, 'to_json') and callable(getattr(activity, 'to_json')):
                activity_json = activity.to_json()
                # Convert any datetime objects in the activity JSON
                activity_json = convert_datetime_to_iso(activity_json)
                activities_json.append(activity_json)
            else:
                # Fallback for activities without to_json method
                activities_json.append({
                    'name': activity.name,
                    'begin_time': activity.begin_time.isoformat() if hasattr(activity, 'begin_time') and activity.begin_time else None,
                    'end_time': activity.end_time.isoformat() if hasattr(activity, 'end_time') and activity.end_time else None,
                    'type': activity.__class__.__name__
                })
        
        # Convert below-the-fold activities to JSON
        btf_activities_json = []
        for activity in self.below_the_fold_activities:
            if hasattr(activity, 'to_json') and callable(getattr(activity, 'to_json')):
                activity_json = activity.to_json()
                # Convert any datetime objects in the activity JSON
                activity_json = convert_datetime_to_iso(activity_json)
                btf_activities_json.append(activity_json)
            else:
                # Fallback for activities without to_json method
                btf_activities_json.append({
                    'name': activity.name,
                    'begin_time': activity.begin_time.isoformat() if hasattr(activity, 'begin_time') and activity.begin_time else None,
                    'end_time': activity.end_time.isoformat() if hasattr(activity, 'end_time') and activity.end_time else None,
                    'type': activity.__class__.__name__
                })
        
        # Add activities to the result
        result['activities'] = activities_json
        result['below_the_fold_activities'] = btf_activities_json
        
        return result
    
    def to_json_file(self, file_path: str) -> None:
        """
        Serialize the scheduler to JSON and write to a file.

        Args:
            file_path: Absolute or relative path to the output file. 
                Directories will be created if they do not exist.
        """
        # Convert to JSON dictionary
        json_data = self.to_json()
        
        # Ensure the directory exists
        output_path = Path(file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Custom JSON encoder to handle HTML components
        class HTMLComponentEncoder(json.JSONEncoder):
            def default(self, obj):                
                if isinstance(obj, HtmlComponent):
                    # Render the component to HTML string
                    return obj.render()
                
                # Let the default encoder handle everything else
                return super().default(obj)
        
        # Write to file with nice formatting
        with open(file_path, 'w') as f:
            json.dump(json_data, f, indent=2, cls=HTMLComponentEncoder)
            
        logger.info(f"Scheduler data saved to {file_path}")
    
    def _from_json_dict(self, json_data: Dict[str, Any]) -> None:
        """
        Populate scheduler-specific attributes from a JSON dictionary.
        
        This method is meant to be overridden by subclasses to handle their specific attributes.
        
        Args:
            json_data: Dictionary containing scheduler data
        """
        # Process metadata if present
        if "metadata" in json_data and json_data["metadata"]:
            self.metadata = json_data["metadata"]
            
        # Subclasses should call super()._from_json_dict(json_data) and then
        # extract their specific data from self.metadata
    
    @classmethod
    def from_json(cls, json_data: Dict[str, Any]) -> 'Scheduler':
        """
        Factory method to create a Scheduler instance from a JSON dictionary.

        This method includes logic to dynamically discover and instantiate the
        correct `Scheduler` subclass based on the 'scheduler_type' or 'mission'
        fields in the JSON data.

        Args:
            json_data: Dictionary containing scheduler data.

        Returns:
            Scheduler: An instance of the correct Scheduler subclass populated 
            with the JSON data.
        """
        # Try to determine the correct scheduler class based on mission or scheduler_type
        scheduler_class = cls  # Default to the class this method was called on
        mission = json_data.get('mission')
        scheduler_type = json_data.get('scheduler_type')
        
        if (mission and mission != getattr(scheduler_class, 'MISSION', None)) or \
           (scheduler_type and scheduler_type != scheduler_class.__name__):
            # Try to find a scheduler class for this mission or type
            # Check common locations for scheduler classes
            for module_name in ["tts_plan.scheduler", "demosat_plan.demosat_scheduler"]:
                try:
                    module = importlib.import_module(module_name)
                    # First try to match by scheduler_type if available
                    if scheduler_type and hasattr(module, scheduler_type):
                        scheduler_class = getattr(module, scheduler_type)
                        break
                        
                    # Otherwise look for classes that match the mission
                    if mission:
                        for attr_name in dir(module):
                            if attr_name.endswith('Scheduler'):
                                attr = getattr(module, attr_name)
                                if hasattr(attr, 'MISSION') and getattr(attr, 'MISSION') == mission:
                                    scheduler_class = attr
                                    break
                except (ImportError, AttributeError):
                    continue
                
        # Check if the scheduler class has its own from_json method
        if scheduler_class != cls and hasattr(scheduler_class, 'from_json') and callable(getattr(scheduler_class, 'from_json')):
            # Use the subclass's from_json method
            return scheduler_class.from_json(json_data)
        
        # Parse datetime strings
        start_time = None
        if 'start_time' in json_data and json_data['start_time']:
            start_time = datetime.strptime(json_data["start_time"], "%Y-%m-%dT%H:%M:%S")
        end_time = None
        if 'end_time' in json_data and json_data['end_time']:
            end_time = datetime.strptime(json_data["end_time"], "%Y-%m-%dT%H:%M:%S")
        
        # Extract metadata if present
        metadata = json_data.get('metadata')
        
        # Create the scheduler instance
        scheduler = scheduler_class(start_time=start_time, end_time=end_time, metadata=metadata)
        
        # Set the mission if it's not already set
        if hasattr(scheduler, 'mission') and not scheduler.mission and mission:
            scheduler.mission = mission
        
        # Call the subclass-specific method to handle additional attributes
        scheduler._from_json_dict(json_data)
        
        # Import Activity class here to avoid circular imports
        from tts_plan.activity import Activity
        
        # Process activities
        if 'activities' in json_data and json_data['activities']:
            for activity_json in json_data['activities']:
                # Use the "type" field from the JSON to determine which activity class to use
                # This allows proper deserialization without hardcoding mission-specific paths
                activity = Activity.from_json(activity_json)
                scheduler.activities.append(activity)
        
        # Process below-the-fold activities
        if 'below_the_fold_activities' in json_data and json_data['below_the_fold_activities']:
            for activity_json in json_data['below_the_fold_activities']:
                # Use the "type" field from the JSON to determine which activity class to use
                activity = Activity.from_json(activity_json)
                scheduler.below_the_fold_activities.append(activity)
        
        return scheduler
    
    @classmethod
    def from_json_file(cls, file_path: str) -> 'Scheduler':
        """
        Factory method to create a Scheduler instance from a JSON file.

        Args:
            file_path: Path to the JSON file.

        Returns:
            Scheduler: A populated scheduler instance.
        """
        # Import Activity class here to avoid circular imports
        from tts_plan.activity import Activity
        
        # Read the JSON file
        with open(file_path, 'r') as f:
            json_data = json.load(f)
        
        # Create the scheduler from the JSON data
        scheduler = cls.from_json(json_data)
        
        logger.info(f"Loaded scheduler data from {file_path}")
        return scheduler