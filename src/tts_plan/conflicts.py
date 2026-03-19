from tts_plan.activity import Activity
from datetime import datetime, timedelta

class ConflictActivity(Activity):
    """
    Special activity for visualizing conflicts in a Gantt chart.
    
    This activity represents a resource conflict between two activities,
    showing the overlap period where both activities claim the same resource(s).
    
    Attributes:
        conflict: The Conflict object this activity represents.
    """
    TYPE = "CONFLICT"
    NAME = "Resource Conflict"
    COLOR = "#ff0f0f"  # Warning Red
    HIGHLIGHT_FULL_HEIGHT = True
    BELOW_THE_FOLD = False
    
    def __init__(self, conflict: 'Conflict', **kwargs):
        """
        Initialize a ConflictActivity from a Conflict object.
        
        Args:
            conflict: The Conflict object to visualize.
            **kwargs: Additional arguments passed to Activity.__init__.
        """
        self.conflict = conflict
        
        # Create a name describing the conflict
        resources_str = ", ".join(str(r) for r in sorted(conflict.conflicting_resources, key=str))
        name = f"Conflict: {conflict.activity1.name} vs {conflict.activity2.name} ({resources_str})"
        
        # Initialize the activity with the overlap period
        super().__init__(
            begin_time=conflict.overlap_start,
            end_time=conflict.overlap_end,
            name=name,
            color=conflict.color if conflict.color else self.COLOR,
            highlight_full_height=kwargs.get('highlight_full_height', self.HIGHLIGHT_FULL_HEIGHT),
            below_the_fold=kwargs.get('below_the_fold', self.BELOW_THE_FOLD),
            **{k: v for k, v in kwargs.items() if k not in ['color', 'highlight_full_height', 'below_the_fold']}
        )

    def _get_hover_text_rows(self):
        rows = super()._get_hover_text_rows()
        rows.append(("Rule ID", f"{self.conflict.rule_id}"))
        rows.append(("Criticality", f"{self.conflict.criticality}"))
        return rows

class Conflict:
    """Represents a resource conflict between two activities.
    
    A conflict occurs when two activities overlap in time and claim
    the same resource(s).
    
    Attributes:
        activity1: Reference to the first conflicting activity.
        activity2: Reference to the second conflicting activity.
        conflicting_resources: Set of resources that both activities claim.
        overlap_start: When the temporal overlap begins.
        overlap_end: When the temporal overlap ends.
        criticality: Criticality level of the conflict (0-1).
        rule_id: ID of the rule that triggered the conflict.
        color: Color of the conflict activity.
    """
    
    def __init__(self, 
                 activity1: Activity,
                 activity2: Activity,
                 conflicting_resources: set,
                 overlap_start: datetime,
                 overlap_end: datetime,
                 criticality: float = None,
                 rule_id: str = None,
                 color: str = None,
                 ):
        self.activity1 = activity1
        self.activity2 = activity2
        self.conflicting_resources = conflicting_resources
        self.overlap_start = overlap_start
        self.overlap_end = overlap_end
        self.criticality = criticality
        self.rule_id = rule_id
        self.color = color

    @property
    def activity1_uuid(self) -> str:
        """UUID of the first activity (for backward compatibility)."""
        return self.activity1.uuid
    
    @property
    def activity2_uuid(self) -> str:
        """UUID of the second activity (for backward compatibility)."""
        return self.activity2.uuid
    
    @property
    def overlap_duration(self) -> timedelta:
        """Duration of the temporal overlap."""
        return self.overlap_end - self.overlap_start

        
    
    def __repr__(self):
        resources_str = ', '.join(str(r) for r in self.conflicting_resources)
        name1 = getattr(self.activity1, 'name', self.activity1_uuid[:8])
        name2 = getattr(self.activity2, 'name', self.activity2_uuid[:8])
        return (f"Conflict(activity1='{name1}', "
                f"activity2='{name2}', "
                f"resources=[{resources_str}], "
                f"overlap={self.overlap_duration})")
    
    def __eq__(self, other):
        if not isinstance(other, Conflict):
            return False
            
        # Check if the conflicts involve the same activities (order doesn't matter)
        if {self.activity1_uuid, self.activity2_uuid} != {other.activity1_uuid, other.activity2_uuid}:
            return False
            
        # Check if they have the same rule ID
        if getattr(self, 'rule_id', None) != getattr(other, 'rule_id', None):
            return False
            
        # Check if they have the same overlap period
        if self.overlap_start != other.overlap_start or self.overlap_end != other.overlap_end:
            return False
            
        # Conflicts appear to be the same
        return True
    
    def __hash__(self):
        # Hash based on the set of UUIDs (order-independent), rule_id, and overlap times
        # Note: We need to make this consistent with __eq__, but we can't use mutable objects in hash
        rule_id = getattr(self, 'rule_id', None) or ''
        
        # Create a tuple of components to hash
        components = (
            frozenset([self.activity1_uuid, self.activity2_uuid]),
            rule_id,
            self.overlap_start,
            self.overlap_end
        )
        
        return hash(components)