"""Core activity type definitions for spacecraft activity planning.

This module provides the fundamental building blocks for creating a mission
schedule. It defines the base `Activity` class, which serves as the parent
for all specific mission tasks (e.g., Science, Communication, Orbit Events).

It also defines the Constraint system, allowing activities to be anchored
to one another or to absolute time points using temporal logic (BEFORE,
DURING, AFTER).
"""

from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from enum import Enum, auto, Flag
import uuid
import importlib
import importlib.util
import os
import sys
from typing import Dict, Any, Optional, List, Union, Type, Sequence, TypeVar, cast, Tuple, Set

from tts_data_utils.core.data_item import DataItem

from tts_html_utils.core.components.text import Span
from tts_html_utils.core.components.misc import BR
from tts_html_utils.core.components.structure import Div

class ClaimType(Enum):
    """Enum defining types of resource claims.
    
    Attributes:
        EXCLUSIVE: Traditional claim - conflicts with any other claim on the same resource.
        AVOIDANCE: Soft claim - only conflicts with EXCLUSIVE claims, not with other AVOIDANCE claims.
                   Useful when multiple activities need to avoid a resource without conflicting with each other.
    
    Example:
        If Activity C makes an EXCLUSIVE claim on a resource, and Activities A and B both make
        AVOIDANCE claims on the same resource:
        - A will conflict with C (AVOIDANCE vs EXCLUSIVE)
        - B will conflict with C (AVOIDANCE vs EXCLUSIVE)
        - A will NOT conflict with B (AVOIDANCE vs AVOIDANCE)
    """
    EXCLUSIVE = auto()  # Conflicts with any other claim (default behavior)
    AVOIDANCE = auto()  # Only conflicts with EXCLUSIVE claims

class ModelConstraint:
    """Base class for constraints on modeled values.
    
    ModelConstraints allow activities to specify requirements about system state
    (e.g., "battery must be above 30%", "roll angle must be between -10 and +10 degrees").
    
    Attributes:
        model_name: Name of the modeled value to constrain.
        metadata: Optional metadata about the constraint.
    """
    def __init__(self, model_name: str, metadata: Optional[Dict[str, Any]] = None):
        self.model_name = model_name
        self.metadata = metadata or {}
    
    def is_violated(self, value: float) -> bool:
        """Check if a given value violates this constraint.
        
        Args:
            value: The value to check.
            
        Returns:
            True if the constraint is violated, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement is_violated()")
    
    def __repr__(self):
        return f"{self.__class__.__name__}({self.model_name})"

class MinConstraint(ModelConstraint):
    """Constraint requiring a modeled value to be at or above a minimum.
    
    Example: Battery charge must be >= 30%
    """
    def __init__(self, model_name: str, min_value: float, metadata: Optional[Dict[str, Any]] = None):
        super().__init__(model_name, metadata)
        self.min_value = min_value
    
    def is_violated(self, value: float) -> bool:
        if value is None:
            return False  # No value means no constraint to check
        return value < self.min_value
    
    def __repr__(self):
        if self.metadata:
            return f"MinConstraint({self.model_name} >= {self.min_value}, metadata={self.metadata})"
        return f"MinConstraint({self.model_name} >= {self.min_value})"

class MaxConstraint(ModelConstraint):
    """Constraint requiring a modeled value to be at or below a maximum.
    
    Example: Temperature must be <= 50°C
    """
    def __init__(self, model_name: str, max_value: float, metadata: Optional[Dict[str, Any]] = None):
        super().__init__(model_name, metadata)
        self.max_value = max_value
    
    def is_violated(self, value: float) -> bool:
        if value is None:
            return False  # No value means no constraint to check
        return value > self.max_value
    
    def __repr__(self):
        if self.metadata:
            return f"MaxConstraint({self.model_name} <= {self.max_value}, metadata={self.metadata})"
        return f"MaxConstraint({self.model_name} <= {self.max_value})"

class RangeConstraint(ModelConstraint):
    """Constraint requiring a modeled value to be within a range.
    
    Example: Roll angle must be between -10 and +10 degrees
    """
    def __init__(self, model_name: str, min_value: float, max_value: float, 
                 metadata: Optional[Dict[str, Any]] = None):
        super().__init__(model_name, metadata)
        self.min_value = min_value
        self.max_value = max_value
        
        if min_value > max_value:
            raise ValueError(f"min_value ({min_value}) must be <= max_value ({max_value})")
    
    def is_violated(self, value: float) -> bool:
        return value < self.min_value or value > self.max_value
    
    def __repr__(self):
        if self.metadata:
            return f"RangeConstraint({self.model_name} in [{self.min_value}, {self.max_value}], metadata={self.metadata})"
        return f"RangeConstraint({self.model_name} in [{self.min_value}, {self.max_value}])"

class ExactConstraint(ModelConstraint):
    """Constraint requiring a modeled value to equal a specific value.
    
    Example: Instrument mode must be exactly 3
    """
    def __init__(self, model_name: str, value: float, metadata: Optional[Dict[str, Any]] = None):
        super().__init__(model_name, metadata)
        self.value = value
    
    def is_violated(self, actual_value: float) -> bool:
        return actual_value != self.value
    
    def __repr__(self):
        if self.metadata:
            return f"ExactConstraint({self.model_name} == {self.value}, metadata={self.metadata})"
        return f"ExactConstraint({self.model_name} == {self.value})"

class Claim:
    """Represents a resource claim on an activity.
    
    Claims are boolean - an activity either claims a resource or it doesn't.
    For quantitative resource tracking, use ModeledValues instead.
    
    Attributes:
        resource: The resource being claimed (typically an Enum value).
        claim_type: Type of claim (EXCLUSIVE or AVOIDANCE).
        metadata: Optional metadata about the claim (e.g., specific configuration).
    """
    def __init__(self, resource: Union[Enum, str], 
                 claim_type: ClaimType = ClaimType.EXCLUSIVE,
                 metadata: Optional[Dict[str, Any]] = None):
        self.resource = resource
        self.claim_type = claim_type
        self.metadata = metadata or {}
    
    def __repr__(self):
        type_str = f", {self.claim_type.name}" if self.claim_type != ClaimType.EXCLUSIVE else ""
        if self.metadata:
            return f"Claim({self.resource}{type_str}, metadata={self.metadata})"
        return f"Claim({self.resource}{type_str})"
    
    def __eq__(self, other):
        if isinstance(other, Claim):
            return self.resource == other.resource
        return False
    
    def __hash__(self):
        return hash(self.resource)

class TemporalRelation(Flag):
    """Enum defining temporal relationships between activities.
    
    Used by `Constraint` classes to define how an activity relates to a 
    target (e.g., another activity or a specific time).
    """
    BEFORE = auto()       # Activity must occur before the reference
    AFTER = auto()        # Activity must occur after the reference
    DURING = auto()       # Activity must occur during the reference
    NOT_BEFORE = auto()   # Activity must not occur before the reference
    NOT_AFTER = auto()    # Activity must not occur after the reference
    NOT_DURING = auto()   # Activity must not occur during the reference

class ConstraintTarget(Enum):
    """Enum defining the scope of a constraint target.
    
    Attributes:
        CLASS: The constraint applies to *any* instance of the target class.
        INSTANCE: The constraint applies to a specific activity instance (by UUID).
    """
    CLASS = auto()        # Constraint applies to all instances of a class
    INSTANCE = auto()     # Constraint applies to a specific instance
    
class Constraint:
    """Base class for all scheduling constraints.
    
    Provides a common interface for definitions that limit when an activity
    can occur.
    
    Args:
        name: A human-readable identifier for the constraint.
        description: A detailed explanation of the constraint logic.
    """
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

class ActivityConstraint(Constraint):
    """Constraint that relates one activity to another activity or class of activities.
    
    This is used for relative scheduling, such as "Science must happen after
    Slew" or "Downlink must happen during Communication Window".
    
    Args:
        name: Name of the constraint.
        description: Description of the constraint.
        relation: The temporal relation (e.g., BEFORE, DURING).
        target_type: Whether this applies to a class (ConstraintTarget.CLASS) 
            or specific instance (ConstraintTarget.INSTANCE).
        target: The target activity class name (str) or instance UUID (str).
        lead_time: Minimum time buffer required *before* the reference point.
            Defaults to 0.
        trail_time: Minimum time buffer required *after* the reference point.
            Defaults to 0.
    """
    def __init__(self, 
                 name: str, 
                 description: str, 
                 relation: TemporalRelation,
                 target_type: ConstraintTarget,
                 target: Union[str, Type],
                 lead_time: Optional[timedelta] = None,
                 trail_time: Optional[timedelta] = None):
        super().__init__(name, description)
        self.relation = relation
        self.target_type = target_type
        self.target = target
        self.lead_time = lead_time or timedelta(0)
        self.trail_time = trail_time or timedelta(0)

class AbsoluteTimeConstraint(Constraint):
    """Constraint based on a specific absolute UTC time.

    Used for anchoring activities to wall-clock time, such as "Must occur
    before 2026-01-01T12:00:00".

    Args:
        name: Name of the constraint.
        description: Description of the constraint.
        absolute_time: The specific datetime object to constrain against.
        relation: The temporal relation (BEFORE, AFTER) relative to the time.
    """
    def __init__(self, name: str, description: str, absolute_time: datetime, relation: TemporalRelation):
        super().__init__(name, description)
        self.absolute_time = absolute_time
        self.relation = relation

class ModeledValueConstraint(Constraint):
    """Constraint based on a modeled system state value.

    Used for resource-based scheduling, such as "Activity requires Battery 
    Charge > 50%".
    
    Args:
        name: Name of the constraint.
        description: Description of the constraint.
        model_name: The identifier of the model resource (e.g., 'battery_soc').
        threshold: The numeric value against which to compare.
        comparison: The operator for comparison (e.g., '>', '<', '==', '>=').
    """
    def __init__(self, name: str, description: str, model_name: str, threshold: float, comparison: str):
        super().__init__(name, description)
        self.model_name = model_name
        self.threshold = threshold
        self.comparison = comparison


# IMPORTANT: Mission-specific implementation guidance
# 
# Each mission should define its own Claimables enum in its activity module
# (e.g., demosat_activity.py) rather than importing this one. This enum is
# provided as a reference implementation only.
#
# Example usage in a mission-specific module:
#
# ```python
# from enum import Enum, auto
#
# class Claimables(Enum):
#     CPU = auto()
#     INSTRUMENT = auto()
#     # ... other mission-specific resources
# ```
#
# Then in your mission-specific activities, you can use your own Claimables enum
# with proper type hints:
#
# ```python
# from .your_mission_activity import Claimables
#
# activity = YourActivity()
# activity.add_claim(Claimables.CPU, 0.75)
# ```
class Claimables(Enum):
    """Reference Enum of resources that can be claimed by activities.
    
    Note:
        Missions should define their own specific `Claimables` enum.
    """
    CPU = auto()
    INSTRUMENT = auto()
    XBAND = auto()
    SBAND = auto()
    ADCS = auto()


class Activity(ABC):
    """Base abstract class for all spacecraft activities.

    This class provides the core functionality for defining tasks within a
    schedule, including timing, resource claims, hierarchy (parent/child 
    activities), and constraints.

    Class Attributes:
        TYPE (str): The unique identifier string for this activity type.
        NAME (str): The default display name for this activity type.
        DESCRIPTION (str): The default description.
        COLOR (str): Visual hint for timeline rendering (e.g., "blue", "#FF0000").
        HIGHLIGHT_FULL_HEIGHT (bool): UI hint for timeline rendering.
        BELOW_THE_FOLD (bool): UI hint to group less critical activities.
        _activity_module_registry (Dict[str, List[str]]): Registry of mission-specific 
            activity module paths, keyed by base package name.
    """
    TYPE = None
    NAME = None
    DESCRIPTION = None
    COLOR = "grey"
    HIGHLIGHT_FULL_HEIGHT = False
    BELOW_THE_FOLD = False
    
    # Class-level registry for mission-specific activity modules
    _activity_module_registry: Dict[str, List[str]] = {}
    
    @classmethod
    def register_activity_modules(cls, base_package: str, module_paths: List[str]) -> None:
        """Register activity module paths for a mission package.
        
        This allows mission-specific packages to register their activity module
        locations so that Activity.from_json() can find and instantiate the
        correct activity subclasses without hardcoding mission-specific logic
        in the core library.
        
        Args:
            base_package: The base package name (e.g., "mro_plan", "europa_plan")
            module_paths: List of module paths to search for activity classes
                         (e.g., ["mro_plan.activities.hirise", "mro_plan.activities.ctx"])
        
        Example:
            >>> Activity.register_activity_modules("mro_plan", [
            ...     "mro_plan.activities.hirise",
            ...     "mro_plan.activities.ctx",
            ...     "mro_plan.activities.onc",
            ... ])
        """
        if base_package not in cls._activity_module_registry:
            cls._activity_module_registry[base_package] = []
        cls._activity_module_registry[base_package].extend(module_paths)

    def __init__(self, begin_time=None, duration=None, end_time=None, name=None, description=None, activity_uuid=None, activities=None, 
                 constraints: Optional[List[Constraint]] = None, command=None, seqid=None, claims=None, color=None, 
                 highlight_full_height=False, below_the_fold=None, metadata=None, **kwargs):
        """Initialize a new Activity.

        Args:
            begin_time (datetime): The scheduled start time of the activity.
            duration (timedelta): The duration of the activity.
            name (str, optional): The display name. Defaults to class NAME attribute.
            description (str, optional): Detailed text. Defaults to class DESCRIPTION attribute.
            activity_uuid (str, optional): Unique ID. Auto-generated if None.
            activities (list, optional): List of child `Activity` objects.
            constraints (list, optional): List of `Constraint` objects.
            command (str, optional): The actual spacecraft command string (mutually exclusive with seqid).
            seqid (str, optional): The sequence ID (mutually exclusive with command).
            claims (list, optional): List of Claim instances.
            color (str, optional): Override for the visualization color.
            highlight_full_height (bool): Override for UI rendering hint.
            below_the_fold (bool, optional): Override for UI grouping hint.
            metadata (dict, optional): Dictionary for mission-specific extra data.
            **kwargs: Additional keyword arguments for subclass flexibility.

        Raises:
            Exception: If both `seqid` and `command` are provided.
        """
        if begin_time is None and duration is None and end_time is None:
            raise Exception("begin_time, duration, and end_time cannot all be None")
        elif duration is None and end_time is None:
            #mostly this is here so when we create a parent we don't care about the
            #duration of (since we'll just autocalculate when we add children),
            #we don't end up with a completely broken activity
            duration = timedelta(seconds=30)
        elif begin_time is None:
            #then we have duration and end time
            begin_time = end_time - duration
        elif duration is None:
            #then we have begin time and end time        
            duration = end_time - begin_time
        elif end_time is None:
            #then we have begin time and duration
            pass #we have what we need
        else:
            kwargs_present = []
            if begin_time is not None: kwargs_present.append("begin_time")
            if duration is not None: kwargs_present.append("duration")
            if end_time is not None: kwargs_present.append("end_time")
            kwargs_present = ', '.join(kwargs_present)
            raise Exception(f"""
                            Activities must have one of the following combinations of kwargs:
                            begin_time only
                            begin_time and duration
                            end_time and duration
                            begin time and end time
                            Got: {kwargs_present}
                            """)

        self.begin_time = begin_time
        self.duration = duration
        self.uuid = activity_uuid if activity_uuid is not None else str(uuid.uuid4())
        self.name = self.NAME if name is None else name
        self.parent = None #do not add a kwarg for this. This gets set in add_child enforcing that the parent/child relationship is always 2 ways
        # Ensure description is never None
        if description is not None:
            self.description = description
        elif self.DESCRIPTION is not None:
            self.description = self.DESCRIPTION
        else:
            self.description = f"{self.__class__.__name__} activity"
        self.activities = [] if activities is None else activities
        self.constraints = [] if constraints is None else constraints
        self.seqid = seqid
        self.command = command
        if seqid is not None and command is not None:
            raise Exception('Activity cannot have both seqid and command.')
        self.claims = [] if claims is None else claims
        self.effects = []
        self.model_constraints = []  # Effects on modeled values (e.g., battery drain, data generation)
        self.color = color if color is not None else self.COLOR
        self.highlight_full_height = highlight_full_height or self.HIGHLIGHT_FULL_HEIGHT
        self.below_the_fold = below_the_fold if below_the_fold is not None else self.BELOW_THE_FOLD
        self.metadata = {} if metadata is None else metadata
        self.scheduler = None
        
    @property
    def end_time(self) -> datetime:
        """Calculate the end time based on begin_time and duration.
        
        Returns:
            datetime: The calculated end time. If duration is missing, 
            defaults to begin_time + 1 minute.
        """
        if self.begin_time is None:
            return None
        if self.duration is None or not isinstance(self.duration, timedelta):
            # Ensure we have a valid duration
            return self.begin_time + timedelta(minutes=1)
        return self.begin_time + self.duration
    
    def __str__(self) -> str:
        """Return a concise string representation of the activity."""
        start_str = self.begin_time.strftime('%Y-%m-%d %H:%M:%S') if self.begin_time else 'None'
        end_str = self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else 'None'
        child_count = f" [{len(self.activities)} children]" if self.activities else ""
        return f"{self.__class__.__name__}: {self.name} - {start_str} to {end_str}{child_count}"

    def get_hover_text(self):
        """Generate hover text for this activity.
        
        Uses _get_hover_text_rows() which can be extended in subclasses.
        
        Returns:
            HTML component for the hover tooltip
        """
        hover_text = Div()
        
        # Add title
        hover_text.add_child(Span(self.name if self.name else f"Activity {self.uuid[:8]}", 
                                style={'font-weight': 'bold'}))
        hover_text.add_child(BR())
        
        # Create a simple table structure
        table = Div(style={'display': 'table', 'width': '100%'})
        
        # Get rows from this class and any subclasses that override _get_hover_text_rows
        rows = self._get_hover_text_rows()
        
        # Create table rows
        for row_data in rows:
            row = Div(style={'display': 'table-row'})
            
            # Label cell
            label_cell = Div(style={'display': 'table-cell', 'padding-right': '10px', 'font-weight': 'bold'})
            label_cell.add_child(Span(f"{row_data[0]}:"))
            row.add_child(label_cell)
            
            # Value cell with optional styling
            value_style = row_data[2] if len(row_data) > 2 else {}
            value_style.update({'display': 'table-cell'})
            value_cell = Div(style=value_style)
            value_cell.add_child(Span(row_data[1]))
            row.add_child(value_cell)
            
            table.add_child(row)
        
        hover_text.add_child(table)
        return hover_text

    def _get_hover_text_rows(self):
        """Generate rows of data for hover text.
        
        This method can be overridden by subclasses to provide custom hover text rows.
        The default implementation provides basic activity information.
        
        Returns:
            List of tuples: (label, value, optional_style_dict)
        """
                
        def format_time(dt):
            """Format datetime for display."""
            if not dt:
                return "N/A"
            return dt.strftime('%Y-%jT%H:%M:%S.%f')[:-3]  # DOY format with milliseconds
        
        rows = []
        
        # Activity type
        rows.append(("Type", self.__class__.__name__, {"color": "#888"}))
        
        # Times
        if self.begin_time:
            rows.append(("Start", format_time(self.begin_time)))
        if self.end_time:
            rows.append(("End", format_time(self.end_time)))
        
        # Duration
        if self.duration:
            rows.append(("Duration", str(self.duration)))
        
        # Description
        if self.description:
            rows.append(("Description", self.description, {"color": "#666"}))
        
        # UUID for debugging
        rows.append(("UUID", self.uuid[:8]))
        
        return rows

    def _to_json_dict(self) -> Dict[str, Any]:
        """
        Convert activity-specific attributes to a dictionary for JSON serialization.
        
        This method is meant to be overridden by subclasses to add their specific attributes.
        
        Returns:
            Dictionary with activity-specific attributes.
        """
        # Base attributes that all activities have
        result = {
            "name": self.name if self.name else f"Activity {self.uuid[:8]}",
            "type": self.__class__.__name__,
            "uuid": self.uuid,
            "begin_time": self.begin_time,
            "end_time": self.end_time,
            "duration": str(self.duration) if self.duration else None,
            "description": self.description,
            "color": self.color if self.color else self.COLOR,
            "highlight_full_height": self.highlight_full_height,
            "below_the_fold": self.below_the_fold,
            "hover_text": self.get_hover_text(),  # Generate custom hover text
            "seqid": self.seqid,
            "command": self.command
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
            result["metadata"] = metadata_json
            
        return result
    
    def to_json(self, filepath=None, sort_children=True):
        """Convert the activity and its children to a JSON structure and optionally save to a file.
        
        This method recursively converts this activity and all its children to a JSON-compatible
        dictionary structure, and optionally writes it to a file.
        
        Args:
            filepath (str, optional): Path to save the JSON output. If None, the JSON is only returned.
            sort_children (bool): Whether to sort children by begin_time (default: True).
            
        Returns:
            dict: The JSON representation of the activity and its children.
        """
        import json
        from datetime import datetime
        
        # Custom JSON encoder to handle datetime objects
        class DateTimeEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                return super().default(obj)
        
        # Get the activity-specific attributes from the subclass implementation
        result = self._to_json_dict()

        # Add children if they exist
        if hasattr(self, 'activities') and self.activities:
            # Sort children by begin_time if requested
            children = self.activities
            if sort_children:
                children = sorted(
                    children, 
                    key=lambda x: x.begin_time if x.begin_time else datetime.min
                )
            
            # Recursively convert children to JSON
            result["children"] = [child.to_json(sort_children=sort_children) for child in children]
        
        # Save to file if filepath is provided
        if filepath:
            with open(filepath, 'w') as f:
                json.dump(result, f, cls=DateTimeEncoder, indent=2)
            print(f"JSON data saved to: {filepath}")
        
        return result
    
    def _from_json_dict(self, json_data: Dict[str, Any]) -> None:
        """
        Populate activity-specific attributes from a JSON dictionary.
        
        This method is meant to be overridden by subclasses to handle their specific attributes.
        
        Args:
            json_data: Dictionary containing activity data.
        """
        # Process metadata if present
        if "metadata" in json_data and json_data["metadata"]:
            self.metadata = json_data["metadata"]
            
        # Subclasses should call super()._from_json_dict(json_data) and then
        # extract their specific data from self.metadata
    
    @classmethod
    def from_json(cls, json_data: Dict[str, Any]) -> 'Activity':
        """
        Create an Activity object from a JSON dictionary.
        
        This method attempts to dynamically locate and instantiate the correct 
        subclass of `Activity` based on the 'type' field in the JSON data.
        It searches the current module, `sys.modules`, and a list of known 
        mission-specific package paths.
        
        Args:
            json_data: Dictionary containing activity data.
            
        Returns:
            Activity: An Activity object (or specific subclass) populated with the JSON data.
        """
        # If this is a subclass of Activity, try to use that class
        activity_type = json_data.get("type")
        activity_class = cls  # Default to the class this method was called on
        
        if activity_type and activity_type != cls.__name__:
            # Try to find the class in the current module first
            current_module = sys.modules[cls.__module__]
            if hasattr(current_module, activity_type):
                activity_class = getattr(current_module, activity_type)
            else:
                # Determine the base package from cls (e.g., "mro_plan" from "mro_plan.activities.crism")
                base_package = cls.__module__.split('.')[0]
                
                # Build a more dynamic list of modules to search
                modules_to_search = [
                    "tts_plan.activity",  # Core activities
                    f"{base_package}"     # Base mission package
                ]
                
                # Add all registered activity modules from ALL packages
                # This allows finding mission-specific classes even when called from the base Activity class
                for package_name, module_list in cls._activity_module_registry.items():
                    modules_to_search.extend(module_list)
                
                # Add activity packages dynamically from the base package
                modules_to_search.extend([
                    f"{base_package}.{activity_type}",                # Direct module with class name
                    f"{base_package}.activities",                    # Common activities package
                    f"{base_package}.activities.{activity_type.lower()}", # Module named after activity type
                ])
                
                # For standard naming pattern where activities are grouped by instrument
                if base_package.endswith("_plan"):
                    # Find all potential activity modules in the package
                    try:
                        # Import the activities package if it exists
                        activities_package = f"{base_package}.activities"
                        try:
                            importlib.import_module(activities_package)
                            # If we can import the activities package, add all its submodules
                            activities_package_spec = importlib.util.find_spec(activities_package)
                            if activities_package_spec and activities_package_spec.submodule_search_locations:
                                for location in activities_package_spec.submodule_search_locations:
                                    if os.path.isdir(location):
                                        for module_name in os.listdir(location):
                                            # Add any Python modules in the activities package
                                            if module_name.endswith('.py') and not module_name.startswith('__'):
                                                module_base = module_name[:-3]  # Remove .py extension
                                                modules_to_search.append(f"{activities_package}.{module_base}")
                        except ImportError:
                            # If activities package doesn't exist, that's okay
                            pass
                    except Exception:
                        # If anything fails in the dynamic search, we still have our base modules
                        pass
                
                # Find the activity class in the available modules
                for module_name in modules_to_search:
                    try:
                        module = importlib.import_module(module_name)
                        if hasattr(module, activity_type):
                            activity_class = getattr(module, activity_type)
                            break
                    except (ImportError, AttributeError):
                        continue
                
        # No special handling for subclass from_json methods
        
        # Parse datetime objects
        begin_time = None
        if "begin_time" in json_data:
            if isinstance(json_data["begin_time"], str):
                try:
                    begin_time = datetime.strptime(json_data["begin_time"], "%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    begin_time = datetime.strptime(json_data["begin_time"], "%Y-%m-%dT%H:%M:%S.%f")
            else:
                begin_time = json_data["begin_time"]
        
        # Calculate duration
        duration = None
        if "duration" in json_data and json_data["duration"]:
            if isinstance(json_data["duration"], str):
                # Parse duration string in format "HH:MM:SS"
                parts = json_data["duration"].split(":")
                if len(parts) == 3:
                    hours, minutes, seconds = map(float, parts)
                    duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        elif "end_time" in json_data and begin_time:
            end_time = None
            if isinstance(json_data["end_time"], str):
                end_time = datetime.strptime(json_data["end_time"], "%Y-%m-%dT%H:%M:%S")
            else:
                end_time = json_data["end_time"]
            if end_time:
                duration = end_time - begin_time
        
        if not duration and not isinstance(duration, timedelta):
            # Default duration if not provided or couldn't be calculated
            duration = timedelta(minutes=1)
        
        # Create the activity with basic attributes
        activity_uuid = None
        if "uuid" in json_data:
            activity_uuid = str(json_data["uuid"])
        
        # Extract metadata if present
        metadata = json_data.get("metadata")
        
        activity = activity_class(
            begin_time=begin_time,
            duration=duration,
            name=json_data.get("name"),
            description=json_data.get("description"),
            activity_uuid=activity_uuid,
            seqid=json_data.get("seqid"),
            command=json_data.get("command"),
            color=json_data.get("color"),
            highlight_full_height=json_data.get("highlight_full_height", False),
            below_the_fold=json_data.get("below_the_fold", False),
            metadata=metadata
        )
        
        # Call the subclass-specific method to handle additional attributes
        activity._from_json_dict(json_data)
        
        # Process child activities if present
        if "children" in json_data and json_data["children"]:
            for child_json in json_data["children"]:
                child_activity = Activity.from_json(child_json)
                activity.activities.append(child_activity)
        
        return activity
        
    
    def __repr__(self) -> str:
        """Return a detailed string representation of the activity.
        
        Includes name, start time, end time, and any child activities.
        """
        # Format the basic activity information
        start_str = self.begin_time.strftime('%Y-%m-%d %H:%M:%S') if self.begin_time else 'None'
        end_str = self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else 'None'
        duration_str = str(self.duration) if self.duration else 'None'
        
        result = f"{self.__class__.__name__}: {self.name} ({self.uuid[:8]}...)\n"
        result += f"  Start: {start_str}\n"
        result += f"  End: {end_str}\n"
        result += f"  Duration: {duration_str}\n"
        
        # Add claims if any exist
        if self.claims:
            result += f"  Claims: {len(self.claims)}\n"
        
        # Add child activities if any exist
        if self.activities:
            result += f"  Children: {len(self.activities)}\n"
            for i, child in enumerate(self.activities):
                # Format each child activity with indentation
                child_lines = repr(child).split('\n')
                # Add indentation to each line of the child's representation
                child_repr = '\n'.join([f"    {line}" for line in child_lines])
                result += f"  Child {i+1}:\n{child_repr}\n"
        
        return result
        
    def validate(self) -> bool:
        """Validate the activity configuration.
        
        Current logic acts as a stub. Future implementations should check that 
        sub-activities fit within the duration of the parent and possess 
        valid configurations themselves.
        
        Returns:
            bool: True if valid, False otherwise.
        """
        # TODO: Implement logic to check that sub-activities fill this one
        # TODO: Implement logic to check that sub-activities are themselves valid
        return True

    def add_claim(self, claimable: Union[Enum, str], 
                  claim_type: ClaimType = ClaimType.EXCLUSIVE,
                  metadata: Optional[Dict[str, Any]] = None):
        """Add a claim on a resource for this activity.
        
        Claims are boolean - an activity either claims a resource or it doesn't.
        For quantitative resource tracking (e.g., power consumption, data volume),
        use ModeledValues and add_effect() instead.
        
        Args:
            claimable: The resource to claim (typically an Enum value or string).
            claim_type: Type of claim (EXCLUSIVE or AVOIDANCE). Default is EXCLUSIVE.
                EXCLUSIVE: Conflicts with any other claim on the same resource (traditional behavior).
                AVOIDANCE: Only conflicts with EXCLUSIVE claims, not with other AVOIDANCE claims.
            metadata: Optional metadata about the claim (e.g., specific configuration).
            
        Note:
            It's recommended to use mission-specific Claimables enum values.
        """
        claim = Claim(claimable, claim_type, metadata)
        if claim not in self.claims:
            self.claims.append(claim)

    def add_child(self, child_activity):
        """Add a child activity to this activity.
        
        Args:
            child_activity (Activity): The activity object to add as a child.
            
        Returns:
            Activity: The added child activity (allows for method chaining).
        """
        child_activity.parent = self
        if self.activities is None:
            self.activities = []
            
        self.activities.append(child_activity)
        return child_activity
        
    def remove_claim(self, claimable: Union[Enum, str]):
        """Remove all claims on a specific resource.
        
        Args:
            claimable: The resource identifier to remove claims for.
        """
        self.claims = [claim for claim in self.claims if claim.resource != claimable]
        
    def add_effect(self, model_name: str, effect_type, timing, value: float, 
                   metadata: Optional[Dict[str, Any]] = None):
        """Add an effect on a modeled value.
        
        Effects describe how this activity modifies system state variables over time
        (e.g., battery drain, data generation, thermal changes).
        
        Args:
            model_name: Name of the modeled value to affect (e.g., 'battery_charge')
            effect_type: Type of effect (from EffectType enum)
            timing: When the effect is applied (from EffectTiming enum)
            value: Magnitude of the effect (interpretation depends on effect_type)
            metadata: Optional additional information about the effect
            
        Examples:
            # Battery drains at 5 W during activity
            activity.add_effect('battery_charge', EffectType.CONSTANT_RATE, 
                              EffectTiming.DURING, -5.0)
            
            # Generate 100 MB of data at activity end
            activity.add_effect('data_volume', EffectType.IMPULSE,
                              EffectTiming.AT_END, 100.0)
                              
            # Turn on instrument (power +50W) during activity
            activity.add_effect('power_consumption', EffectType.STEPPED,
                              EffectTiming.DURING, 50.0)
        """
        # Import here to avoid circular dependency
        from tts_plan.modeled_values import Effect
        
        effect = Effect(
            model_name=model_name,
            effect_type=effect_type,
            timing=timing,
            value=value,
            metadata=metadata or {}
        )
        self.effects.append(effect)
        return effect
        
    def remove_effect(self, model_name: str):
        """Remove all effects on a specific modeled value.
        
        Args:
            model_name: The modeled value identifier to remove effects for.
        """
        self.effects = [effect for effect in self.effects if effect.model_name != model_name]
    
    def add_model_constraint(self, constraint: ModelConstraint) -> ModelConstraint:
        """Add a constraint on a modeled value.
        
        This is the low-level method. Consider using the convenience methods instead:
        - add_model_constraint_min()
        - add_model_constraint_max()
        - add_model_constraint_range()
        - add_model_constraint_exact()
        
        Args:
            constraint: A ModelConstraint instance.
            
        Returns:
            The constraint object that was added.
        """
        self.model_constraints.append(constraint)
        return constraint
    
    def add_model_constraint_min(self, model_name: str, min_value: float, 
                                 metadata: Optional[Dict[str, Any]] = None) -> MinConstraint:
        """Add a minimum value constraint on a modeled value.
        
        Args:
            model_name: Name of the modeled value to constrain.
            min_value: Minimum acceptable value (inclusive).
            metadata: Optional additional information about the constraint.
            
        Returns:
            The MinConstraint that was added.
            
        Example:
            # Battery must be at least 30%
            activity.add_model_constraint_min('battery_charge', 30.0)
        """
        constraint = MinConstraint(model_name, min_value, metadata)
        self.model_constraints.append(constraint)
        return constraint
    
    def add_model_constraint_max(self, model_name: str, max_value: float,
                                 metadata: Optional[Dict[str, Any]] = None) -> MaxConstraint:
        """Add a maximum value constraint on a modeled value.
        
        Args:
            model_name: Name of the modeled value to constrain.
            max_value: Maximum acceptable value (inclusive).
            metadata: Optional additional information about the constraint.
            
        Returns:
            The MaxConstraint that was added.
            
        Example:
            # Temperature must not exceed 50°C
            activity.add_model_constraint_max('temperature', 50.0)
        """
        constraint = MaxConstraint(model_name, max_value, metadata)
        self.model_constraints.append(constraint)
        return constraint
    
    def add_model_constraint_range(self, model_name: str, min_value: float, max_value: float,
                                   metadata: Optional[Dict[str, Any]] = None) -> RangeConstraint:
        """Add a range constraint on a modeled value.
        
        Args:
            model_name: Name of the modeled value to constrain.
            min_value: Minimum acceptable value (inclusive).
            max_value: Maximum acceptable value (inclusive).
            metadata: Optional additional information about the constraint.
            
        Returns:
            The RangeConstraint that was added.
            
        Example:
            # Roll angle must be between -10 and +10 degrees
            activity.add_model_constraint_range('roll_angle', -10.0, 10.0)
        """
        constraint = RangeConstraint(model_name, min_value, max_value, metadata)
        self.model_constraints.append(constraint)
        return constraint
    
    def add_model_constraint_exact(self, model_name: str, value: float,
                                   metadata: Optional[Dict[str, Any]] = None) -> ExactConstraint:
        """Add an exact value constraint on a modeled value.
        
        Args:
            model_name: Name of the modeled value to constrain.
            value: The exact value required.
            metadata: Optional additional information about the constraint.
            
        Returns:
            The ExactConstraint that was added.
            
        Example:
            # Instrument mode must be exactly 3
            activity.add_model_constraint_exact('instrument_mode', 3.0)
        """
        constraint = ExactConstraint(model_name, value, metadata)
        self.model_constraints.append(constraint)
        return constraint
    
    def remove_model_constraint(self, model_name: str):
        """Remove all constraints on a specific modeled value.
        
        Args:
            model_name: The modeled value identifier to remove constraints for.
        """
        self.model_constraints = [c for c in self.model_constraints if c.model_name != model_name]
    
    def check_model_constraints(self, modeled_values: 'ModeledValues') -> List[Tuple[ModelConstraint, float]]:
        """Check all model constraints against current modeled values.
        
        Args:
            modeled_values: The ModeledValues instance to check against.
            
        Returns:
            List of (constraint, violating_value) tuples for any violated constraints.
            Empty list if all constraints are satisfied.
            
        Examples:
            >>> violations = activity.check_model_constraints(scheduler.modeled_values)
            >>> if violations:
            ...     for constraint, value in violations:
            ...         print(f"Constraint {constraint.model_name} violated: {value}")
        """
        violations = []
        for constraint in self.model_constraints:
            # Check the constraint at all times during the activity by examining all profile points
            if constraint.model_name not in modeled_values.profiles:
                continue
                
            profile = modeled_values.profiles[constraint.model_name]
            
            # Find all profile points within the activity's time range
            for timestamp, value in profile:
                # Check if this profile point falls within the activity's duration
                if self.begin_time <= timestamp <= self.end_time:
                    if constraint.is_violated(value):
                        violations.append((constraint, value))
                        break  # Only report the first violation for this constraint
            
            # Also check at activity boundaries if they're not in the profile
            for check_time in [self.begin_time, self.end_time]:
                value = modeled_values.get_value_at_time(constraint.model_name, check_time)
                if value is not None and constraint.is_violated(value):
                    violations.append((constraint, value))
                    break
                    
        return violations

    def add_constraint(self, relation: TemporalRelation, target: Union[str, Type],
                       lead_time: Optional[timedelta] = None, trail_time: Optional[timedelta] = None,
                       name: Optional[str] = None, description: Optional[str] = None) -> ActivityConstraint:
        """Add a temporal constraint relative to another activity.
        
        Args:
            relation: The temporal relation (BEFORE, AFTER, DURING, etc.).
            target: The target activity. Can be a class name (str) or a specific 
                instance UUID (str).
            lead_time: Buffer time required before the target.
            trail_time: Buffer time required after the target.
            name: Optional name for the constraint.
            description: Optional description.
            
        Returns:
            ActivityConstraint: The created constraint object.
            
        Examples:
            # Activity must start at least 5 minutes after any CommWindow activity
            activity.add_constraint(TemporalRelation.AFTER, "CommWindow", trail_time=timedelta(minutes=5))
                                    
            # Activity must not occur during a specific activity (by UUID) with padding
            activity.add_constraint(TemporalRelation.NOT_DURING, "550e8400...",
                                    lead_time=timedelta(minutes=3))
        """
        # Auto-detect target_type based on the target parameter
        # If target is a UUID (str with dashes), assume it's an instance
        if isinstance(target, str) and '-' in target:
            target_type = ConstraintTarget.INSTANCE
        else:
            target_type = ConstraintTarget.CLASS
        
        # Generate default name and description if not provided
        if name is None:
            relation_name = relation.name.lower()
            target_name = target if isinstance(target, str) else target.__name__
            name = f"{relation_name}_{target_name}"
            
        if description is None:
            lead_str = f" with {lead_time} lead time" if lead_time and lead_time > timedelta(0) else ""
            trail_str = f" with {trail_time} trail time" if trail_time and trail_time > timedelta(0) else ""
            time_str = f"{lead_str}{trail_str}"
            
            if target_type == ConstraintTarget.CLASS:
                description = f"Activity must be {relation.name.lower()} any {target} activity{time_str}"
            else:
                description = f"Activity must be {relation.name.lower()} activity {target}{time_str}"
        
        # Create and add the constraint
        constraint = ActivityConstraint(
            name=name,
            description=description,
            relation=relation,
            target_type=target_type,
            target=target,
            lead_time=lead_time,
            trail_time=trail_time
        )
        
        self.constraints.append(constraint)
        return constraint
        
    def must_be_before(self, target: Union[str, Type], offset: Optional[timedelta] = None) -> ActivityConstraint:
        """Helper method: Activity must occur before the target activity.
        
        Args:
            target: The target activity class or UUID.
            offset: Time buffer required before the target (lead_time).
            
        Returns:
            ActivityConstraint: The created constraint.
        """
        return self.add_constraint(TemporalRelation.BEFORE, target, lead_time=offset)
    
    def must_be_after(self, target: Union[str, Type], offset: Optional[timedelta] = None) -> ActivityConstraint:
        """Helper method: Activity must occur after the target activity.
        
        Args:
            target: The target activity class or UUID.
            offset: Time buffer required after the target (trail_time).
            
        Returns:
            ActivityConstraint: The created constraint.
        """
        return self.add_constraint(TemporalRelation.AFTER, target, trail_time=offset)
    
    def must_be_during(self, target: Union[str, Type], lead_time: Optional[timedelta] = None, 
                       trail_time: Optional[timedelta] = None) -> ActivityConstraint:
        """Helper method: Activity must occur during the target activity.
        
        Args:
            target: The target activity class or UUID.
            lead_time: Buffer inside the start of the target.
            trail_time: Buffer inside the end of the target.
            
        Returns:
            ActivityConstraint: The created constraint.
        """
        return self.add_constraint(TemporalRelation.DURING, target, lead_time=lead_time, trail_time=trail_time)
    
    def must_not_be_before(self, target: Union[str, Type], lead_time: Optional[timedelta] = None) -> ActivityConstraint:
        """Helper method: Activity must not occur before the target activity.
        
        Args:
            target: The target activity class or UUID.
            lead_time: Buffer time.
            
        Returns:
            ActivityConstraint: The created constraint.
        """
        return self.add_constraint(TemporalRelation.NOT_BEFORE, target, lead_time=lead_time)
    
    def must_not_be_after(self, target: Union[str, Type], trail_time: Optional[timedelta] = None) -> ActivityConstraint:
        """Helper method: Activity must not occur after the target activity.
        
        Args:
            target: The target activity class or UUID.
            trail_time: Buffer time.
            
        Returns:
            ActivityConstraint: The created constraint.
        """
        return self.add_constraint(TemporalRelation.NOT_AFTER, target, trail_time=trail_time)
    
    def must_not_be_during(self, target: Union[str, Type], lead_time: Optional[timedelta] = None, 
                           trail_time: Optional[timedelta] = None) -> ActivityConstraint:
        """Helper method: Activity must not occur during the target activity.
        
        Args:
            target: The target activity class or UUID.
            lead_time: Buffer time.
            trail_time: Buffer time.
            
        Returns:
            ActivityConstraint: The created constraint.
        """
        return self.add_constraint(TemporalRelation.NOT_DURING, target, lead_time=lead_time, trail_time=trail_time)
        
    def add_absolute_time_constraint(self, relation: TemporalRelation, absolute_time: datetime,
                                     name: Optional[str] = None, description: Optional[str] = None) -> AbsoluteTimeConstraint:
        """Add a constraint relative to a specific wall-clock time.
        
        Args:
            relation: The temporal relation (BEFORE, AFTER).
            absolute_time: The specific datetime object.
            name: Optional name.
            description: Optional description.
            
        Returns:
            AbsoluteTimeConstraint: The created constraint.
            
        Examples:
            # Activity must start before a specific time
            activity.add_absolute_time_constraint(TemporalRelation.BEFORE, 
                                                  datetime(2026, 1, 15, 12, 0, 0))
        """
        # Generate default name and description if not provided
        if name is None:
            relation_name = relation.name.lower()
            time_str = absolute_time.strftime('%Y-%m-%d_%H:%M:%S')
            name = f"{relation_name}_{time_str}"
            
        if description is None:
            time_str = absolute_time.strftime('%Y-%m-%d %H:%M:%S')
            description = f"Activity must be {relation.name.lower()} {time_str}"
        
        # Create and add the constraint
        constraint = AbsoluteTimeConstraint(
            name=name,
            description=description,
            absolute_time=absolute_time,
            relation=relation
        )
        
        self.constraints.append(constraint)
        return constraint
        
    def must_be_before_time(self, absolute_time: datetime) -> AbsoluteTimeConstraint:
        """Helper method: Activity must occur before the specified time.
        
        Args:
            absolute_time: The deadline datetime.
        """
        return self.add_absolute_time_constraint(TemporalRelation.BEFORE, absolute_time)
        
    def must_be_after_time(self, absolute_time: datetime) -> AbsoluteTimeConstraint:
        """Helper method: Activity must occur after the specified time.
        
        Args:
            absolute_time: The start-limit datetime.
        """
        return self.add_absolute_time_constraint(TemporalRelation.AFTER, absolute_time)
        
    def add_model_constraint(self, model_name: str, threshold: float, comparison: str,
                             name: Optional[str] = None, description: Optional[str] = None) -> ModeledValueConstraint:
        """Add a constraint based on a modeled system resource value.
        
        Args:
            model_name: Identifier for the model (e.g., 'power', 'data').
            threshold: The value to compare against.
            comparison: Operator string ('>', '<', '==', etc.).
            name: Optional name.
            description: Optional description.
            
        Returns:
            ModeledValueConstraint: The created constraint.
            
        Examples:
            # Activity must occur when power is above 500W
            activity.add_model_constraint('power', 500, '>')
        """
        # Generate default name and description if not provided
        if name is None:
            name = f"{model_name}_{comparison}_{threshold}"
            
        if description is None:
            description = f"Activity must occur when {model_name} {comparison} {threshold}"
        
        # Create and add the constraint
        constraint = ModeledValueConstraint(
            name=name,
            description=description,
            model_name=model_name,
            threshold=threshold,
            comparison=comparison
        )
        
        self.constraints.append(constraint)

        return constraint
    
    def get_all_descendants(self) -> List['Activity']:
        """Get all descendant activities recursively.
        
        This method traverses the activity tree and returns a flat list containing
        this activity and all of its descendants (children, grandchildren, etc.).
        
        Returns:
            List[Activity]: A list containing this activity and all descendants.
        """
        descendants = [self]
        if self.activities:
            for child in self.activities:
                descendants.extend(child.get_all_descendants())
        return descendants
    
    def get_conflicts_with(self, other: 'Activity') -> List[Tuple['Activity', 'Activity', Set]]:
        """Returns detailed information about conflicts between this activity and another.
        
        A conflict occurs when:
        1. Any descendant of this activity overlaps in time with any descendant of the other activity, AND
        2. They claim at least one common resource
        
        This method recursively checks all descendants (children, grandchildren, etc.) of both activities.
        
        Args:
            other: The other activity to check for conflicts.
                
        Returns:
            List of tuples (desc1, desc2, resources) where desc1 is a descendant of self,
            desc2 is a descendant of other, and resources is the set of conflicting resources.
        """
        conflicts = []
        
        # Early exit: if the parent activities don't overlap in time, no descendants can overlap
        # (parent span goes from earliest child start to latest child end)
        if not self._overlaps_with(other):
            return conflicts
        
        # Get all descendants (including self) for both activities
        self_descendants = self.get_all_descendants()
        other_descendants = other.get_all_descendants()
        
        # Check every pair of descendants for conflicts
        for self_desc in self_descendants:
            for other_desc in other_descendants:
                # Check if these two descendants overlap in time
                if not self_desc._overlaps_with(other_desc):
                    continue
                
                # Check if they share any claims
                if not self_desc.claims or not other_desc.claims:
                    # No claims means no resource conflicts
                    continue
                
                # Check for conflicts respecting claim types
                # EXCLUSIVE claims conflict with any other claim
                # AVOIDANCE claims only conflict with EXCLUSIVE claims (not with other AVOIDANCE claims)
                conflicting_resources = set()
                
                for self_claim in self_desc.claims:
                    for other_claim in other_desc.claims:
                        # Check if they claim the same resource
                        if self_claim.resource != other_claim.resource:
                            continue
                        
                        # Determine if this combination creates a conflict
                        # EXCLUSIVE <-> EXCLUSIVE: conflict
                        # EXCLUSIVE <-> AVOIDANCE: conflict
                        # AVOIDANCE <-> EXCLUSIVE: conflict
                        # AVOIDANCE <-> AVOIDANCE: NO conflict
                        if self_claim.claim_type == ClaimType.EXCLUSIVE or other_claim.claim_type == ClaimType.EXCLUSIVE:
                            conflicting_resources.add(self_claim.resource)
                
                if conflicting_resources:
                    conflicts.append((self_desc, other_desc, conflicting_resources))
        
        return conflicts

    def conflicts_with(self, other: 'Activity') -> bool:
        """Check if this activity conflicts with another activity.
        
        A conflict occurs when:
        1. Any descendant of this activity overlaps in time with any descendant of the other activity, AND
        2. They claim at least one common resource
        
        This method recursively checks all descendants (children, grandchildren, etc.) of both activities.
        
        Args:
            other: The other activity to check for conflicts.
            
        Returns:
            bool: True if there is a conflict, False otherwise.
            
        Examples:
            >>> activity1 = Activity(begin_time=datetime(2026, 1, 1, 10, 0), duration=timedelta(hours=1))
            >>> activity1.add_claim(Claimables.CPU)
            >>> activity2 = Activity(begin_time=datetime(2026, 1, 1, 10, 30), duration=timedelta(hours=1))
            >>> activity2.add_claim(Claimables.CPU)
            >>> activity1.conflicts_with(activity2)
            True
        """
        return len(self.get_conflicts_with(other)) > 0
    
    def _overlaps_with(self, other: 'Activity') -> bool:
        """Check if this activity overlaps in time with another activity.
        
        Args:
            other: The other activity to check for time overlap.
            
        Returns:
            bool: True if the activities overlap in time, False otherwise.
        """
        # Activities overlap if one starts before the other ends
        # and the other starts before the one ends
        return (self.begin_time < other.end_time and 
                other.begin_time < self.end_time)