"""Modeling system for tracking state variables over time in a schedule.

This module provides the infrastructure for modeling continuous or discrete
state variables (e.g., battery charge, data volume, temperature) that change
over time as activities execute. Activities can specify effects that modify
these values, and constraints can be checked against the modeled state.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass, field
from enum import Enum, auto

import pandas as pd
import tts_dtat.plot as dtat_plot
import tts_dtat.datachecker as datachecker


class EffectType(Enum):
    """Types of effects that can modify modeled values."""
    CONSTANT_RATE = auto()    # Constant rate of change (e.g., +5 W/s during activity)
    IMPULSE = auto()          # Instantaneous change at activity start or end
    STEPPED = auto()          # Step change during activity (e.g., power on/off)


class EffectTiming(Enum):
    """When an effect is applied."""
    AT_START = auto()         # Applied at activity begin_time
    DURING = auto()           # Applied continuously during activity
    AT_END = auto()           # Applied at activity end_time


class CombinationMode(Enum):
    """How multiple simultaneous effects on the same model are combined."""
    ADD = auto()              # Sum all effects (e.g., power drain from multiple activities)
    MAX = auto()              # Take maximum effect value (e.g., keepout zones)
    MIN = auto()              # Take minimum effect value
    EXCLUSIVE = auto()        # Only one effect allowed; error if multiple (e.g., on/off states)


@dataclass
class Effect:
    """Represents a change to a modeled value caused by an activity.
    
    Args:
        model_name: The name of the modeled value to affect (e.g., 'battery_charge')
        effect_type: How the effect modifies the value
        timing: When the effect is applied
        value: The magnitude of the effect (interpretation depends on effect_type)
        metadata: Optional additional information about the effect
    
    Examples:
        # Battery drains at 5 W/s during activity
        Effect(model_name='battery_charge', effect_type=EffectType.CONSTANT_RATE,
               timing=EffectTiming.DURING, value=-5.0)
        
        # Downlink reduces data volume by 100 MB at end
        Effect(model_name='data_volume', effect_type=EffectType.IMPULSE,
               timing=EffectTiming.AT_END, value=-100.0)
    """
    model_name: str
    effect_type: EffectType
    timing: EffectTiming
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModeledValues:
    """Tracks state variables over time as activities execute in a schedule.
    
    This class maintains the state of various modeled values (e.g., battery charge,
    data storage, temperature) and computes how they change over time based on
    activity effects.
    
    Attributes:
        initial_values: Initial values for each modeled variable
        profiles: Time-series data for each modeled variable
    """
    
    def __init__(self, initial_values: Optional[Dict[str, float]] = None):
        """Initialize the modeling system.

        Args:
            initial_values: Dictionary mapping model names to their initial values
                (e.g., {'battery_charge': 100.0, 'data_volume': 0.0})
        """
        self.initial_values = initial_values or {}
        self.profiles: Dict[str, List[Tuple[datetime, float]]] = {}
        self._current_values: Dict[str, float] = {}
        self._active_rates: Dict[str, List[Tuple[Any, float]]] = {}  # List of (activity, rate) for each model
        self._active_steps: Dict[str, List[Tuple[Any, float]]] = {}  # List of (activity, value) for STEPPED effects
        self._combination_modes: Dict[str, CombinationMode] = {}  # How to combine multiple effects
        self._min_values: Dict[str, float] = {}  # Minimum bounds for each model
        self._max_values: Dict[str, float] = {}  # Maximum bounds for each model
        
    def register_model(self, model_name: str, initial_value: float = 0.0,
                      combination_mode: CombinationMode = CombinationMode.ADD,
                      min_value: Optional[float] = None,
                      max_value: Optional[float] = None):
        """Register a new modeled value with optional bounds.

        Args:
            model_name: Name of the modeled value
            initial_value: Starting value at schedule start
            combination_mode: How to combine multiple simultaneous effects on this model
                - ADD: Sum all effects (default, for power drain, data generation, etc.)
                - MAX: Take maximum effect (for keepout zones, risk levels, etc.)
                - MIN: Take minimum effect
                - EXCLUSIVE: Only one effect allowed at a time (for on/off states)
            min_value: Minimum allowed value (enforced during computation). None = unbounded.
            max_value: Maximum allowed value (enforced during computation). None = unbounded.

        Examples:
            # Data storage: 0 MB to 32,000 MB
            scheduler.modeled_values.register_model(
                'onboard_data', initial_value=0.0,
                min_value=0.0, max_value=32000.0
            )

            # Battery: 0 Wh to 10,000 Wh
            scheduler.modeled_values.register_model(
                'battery_wh', initial_value=10000.0,
                min_value=0.0, max_value=10000.0
            )

            # Temperature: -40°C to +85°C
            scheduler.modeled_values.register_model(
                'temperature', initial_value=20.0,
                min_value=-40.0, max_value=85.0
            )
        """
        self.initial_values[model_name] = initial_value
        self._current_values[model_name] = initial_value
        self._combination_modes[model_name] = combination_mode
        self._active_rates[model_name] = []  # List of (activity, rate) tuples
        self._active_steps[model_name] = []  # List of (activity, value) tuples for STEPPED effects
        self.profiles[model_name] = []

        # Store bounds if specified
        if min_value is not None:
            self._min_values[model_name] = min_value
        if max_value is not None:
            self._max_values[model_name] = max_value
        
    def get_value_at_time(self, model_name: str, time: datetime) -> Optional[float]:
        """Get the value of a modeled variable at a specific time.
        
        This uses the most recent profile point before or at the requested time,
        essentially implementing step-wise interpolation (hold last value).
        
        Args:
            model_name: Name of the modeled value
            time: Time at which to query the value
            
        Returns:
            The value at the specified time, or None if the model doesn't exist
        """
        if model_name not in self.profiles:
            return None
            
        profile = self.profiles[model_name]
        if not profile:
            return self.initial_values.get(model_name, 0.0)
        
        # Find the two points that bracket the requested time for linear interpolation
        if time <= profile[0][0]:
            # Before first point, return first value
            return profile[0][1]
        
        if time >= profile[-1][0]:
            # After last point, return last value
            return profile[-1][1]
        
        # Find bracketing points - use step-wise interpolation (hold last value)
        for i in range(len(profile) - 1):
            t1, v1 = profile[i]
            t2, v2 = profile[i + 1]
            
            if t1 <= time < t2:
                # Step-wise: return the value at t1 (hold until next point)
                return v1
            elif time == t2:
                # Exactly at the next point, return its value
                return v2
        
        # Shouldn't get here, but return last value as fallback
        return profile[-1][1]
        
    def add_profile_point(self, model_name: str, time: datetime, value: float):
        """Add a point to a modeled value's time profile.
        
        Args:
            model_name: Name of the modeled value
            time: Time of the profile point
            value: Value at that time
        """
        if model_name not in self.profiles:
            self.register_model(model_name, value)
        
        # Insert in chronological order
        profile = self.profiles[model_name]
        for i, (t, _) in enumerate(profile):
            if t == time:
                # Update existing point
                profile[i] = (time, value)
                return
            elif t > time:
                # Insert before this point
                profile.insert(i, (time, value))
                return
        
        # Add to end
        profile.append((time, value))
        
    def compute_profile_from_activities(self, activities: List[Any], 
                                       start_time: datetime,
                                       end_time: Optional[datetime] = None):
        """Compute the time profiles for all modeled values based on activity effects.
        
        This walks through all activities in chronological order and applies their
        effects to update the modeled values.
        
        Args:
            activities: List of activities with potential effects
            start_time: Schedule start time
            end_time: Optional schedule end time (for final values)
        """
        # Reset profiles - use a time before any activities to avoid conflicts
        # We'll add the proper initial point after collecting events
        for model_name in self.initial_values:
            self.profiles[model_name] = []
            self._current_values[model_name] = self.initial_values[model_name]
            self._active_rates[model_name] = []  # List of (activity, rate) tuples
            self._active_steps[model_name] = []  # List of (activity, value) tuples
        
        # Collect all events (activity starts/ends with their effects)
        events: List[Tuple[datetime, str, Any, Effect]] = []
        
        def collect_effects(activity):
            """Recursively collect effects from activity and its descendants."""
            if hasattr(activity, 'effects') and activity.effects:
                for effect in activity.effects:
                    if effect.timing == EffectTiming.AT_START:
                        events.append((activity.begin_time, 'start', activity, effect))
                    elif effect.timing == EffectTiming.DURING:
                        if effect.effect_type == EffectType.CONSTANT_RATE:
                            events.append((activity.begin_time, 'rate_start', activity, effect))
                            events.append((activity.end_time, 'rate_end', activity, effect))
                        elif effect.effect_type == EffectType.STEPPED:
                            events.append((activity.begin_time, 'step_start', activity, effect))
                            events.append((activity.end_time, 'step_end', activity, effect))
                    elif effect.timing == EffectTiming.AT_END:
                        events.append((activity.end_time, 'end', activity, effect))
            
            # Process children
            if hasattr(activity, 'activities') and activity.activities:
                for child in activity.activities:
                    collect_effects(child)
        
        # Collect all effects from all activities
        for activity in activities:
            collect_effects(activity)
        
        # Sort events chronologically
        events.sort(key=lambda x: x[0])
        
        # Add initial profile points at the earlier of start_time or first event time
        if events:
            earliest_event_time = events[0][0]
            initial_time = min(start_time, earliest_event_time) - timedelta(microseconds=1)
        else:
            initial_time = start_time
        
        for model_name in self.initial_values:
            if model_name in self.profiles:
                self.profiles[model_name].insert(0, (initial_time, self.initial_values[model_name]))
        
        # Process events in order
        for time, event_type, activity, effect in events:
            model_name = effect.model_name
            
            # Ensure this model is registered
            if model_name not in self._current_values:
                self.register_model(model_name)
            
            # Apply any active rates up to this time
            self._apply_active_rates(time)
            
            # Apply the effect
            if event_type == 'start' or event_type == 'end':
                # Impulse: instantaneous change
                if effect.effect_type == EffectType.IMPULSE:
                    # Add point just before the jump (infinitesimally earlier) with old value
                    pre_time = time - timedelta(microseconds=1)
                    self.add_profile_point(model_name, pre_time, self._current_values[model_name])
                    # Now add the jump, clamped to bounds
                    self._current_values[model_name] = self._clamp_value(
                        model_name,
                        self._current_values[model_name] + effect.value
                    )
                    self.add_profile_point(model_name, time, self._current_values[model_name])
                    
            elif event_type == 'step_start':
                # Stepped: track this activity's step value and combine according to mode
                # Add point just before the change
                pre_time = time - timedelta(microseconds=1)
                self.add_profile_point(model_name, pre_time, self._current_values[model_name])
                
                # Add this activity's step to the active list
                self._active_steps[model_name].append((activity, effect.value))

                # Recalculate current value based on combination mode, clamped to bounds
                self._current_values[model_name] = self._clamp_value(
                    model_name,
                    self._combine_stepped_values(model_name)
                )
                self.add_profile_point(model_name, time, self._current_values[model_name])
                    
            elif event_type == 'step_end':
                # Stepped: remove this activity's step value and recalculate
                # Add point just before the change
                pre_time = time - timedelta(microseconds=1)
                self.add_profile_point(model_name, pre_time, self._current_values[model_name])
                
                # Remove this activity's step from the active list
                self._active_steps[model_name] = [
                    (a, v) for a, v in self._active_steps[model_name] if a != activity
                ]

                # Recalculate current value based on remaining active steps, clamped to bounds
                self._current_values[model_name] = self._clamp_value(
                    model_name,
                    self._combine_stepped_values(model_name)
                )
                self.add_profile_point(model_name, time, self._current_values[model_name])
                    
            elif event_type == 'rate_start':
                # Start applying a constant rate
                # Add a profile point at this time to mark when the rate starts
                self.add_profile_point(model_name, time, self._current_values[model_name])
                
                # Check for EXCLUSIVE mode conflicts
                mode = self._combination_modes.get(model_name, CombinationMode.ADD)
                if mode == CombinationMode.EXCLUSIVE and len(self._active_rates[model_name]) > 0:
                    existing_activities = [a.name if hasattr(a, 'name') else str(a) 
                                         for a, _ in self._active_rates[model_name]]
                    raise ValueError(
                        f"Model '{model_name}' has EXCLUSIVE combination mode, but multiple "
                        f"activities are trying to affect it simultaneously. "
                        f"Existing: {existing_activities}, New: {activity.name if hasattr(activity, 'name') else str(activity)}"
                    )
                
                # Add this activity's rate to the list
                self._active_rates[model_name].append((activity, effect.value))
                    
            elif event_type == 'rate_end':
                # Stop applying a constant rate
                # Remove this activity's rate from the list
                self._active_rates[model_name] = [
                    (a, r) for a, r in self._active_rates[model_name] if a != activity
                ]
        
        # Apply rates to end time if specified
        if end_time:
            self._apply_active_rates(end_time)
            # Add final point for all models at end_time to complete the profile
            for model_name in self._current_values:
                if model_name in self.profiles:
                    profile = self.profiles[model_name]
                    if profile and profile[-1][0] < end_time:
                        # Add final point with current value
                        self.add_profile_point(model_name, end_time, self._current_values[model_name])
            
    def _combine_stepped_values(self, model_name: str) -> float:
        """Combine active STEPPED effect values according to the model's combination mode.
        
        Args:
            model_name: Name of the model to combine values for
            
        Returns:
            The combined value based on active steps and combination mode
        """
        if model_name not in self._active_steps:
            return self.initial_values.get(model_name, 0.0)
        
        step_list = self._active_steps[model_name]
        if not step_list:
            # No active steps, return to initial value
            return self.initial_values.get(model_name, 0.0)
        
        # Get combination mode for this model
        mode = self._combination_modes.get(model_name, CombinationMode.ADD)
        values = [v for _, v in step_list]
        
        if mode == CombinationMode.ADD:
            # ADD mode: sum all active step values
            try:
                return self.initial_values.get(model_name, 0.0) + sum(values)
            except Exception as e:
                import pdb; pdb.set_trace()
        elif mode == CombinationMode.MAX:
            # MAX mode: take the maximum of all active step values
            return max(values)
        elif mode == CombinationMode.MIN:
            # MIN mode: take the minimum of all active step values
            return min(values)
        elif mode == CombinationMode.EXCLUSIVE:
            # EXCLUSIVE mode: only one step allowed at a time
            if len(values) > 1:
                activities = [a.name if hasattr(a, 'name') else str(a) for a, _ in step_list]
                raise ValueError(
                    f"Model '{model_name}' has EXCLUSIVE combination mode, but multiple "
                    f"activities have STEPPED effects on it simultaneously: {activities}"
                )
            return values[0]
        else:
            # Default to ADD
            return self.initial_values.get(model_name, 0.0) + sum(values)

    def _clamp_value(self, model_name: str, value: float) -> float:
        """Clamp a value to its registered min/max bounds.

        This enforces physical constraints during computation, ensuring values
        stay within realistic ranges (e.g., battery charge >= 0, data storage >= 0).

        Args:
            model_name: Name of the model
            value: The value to clamp

        Returns:
            The clamped value within [min_value, max_value]
        """
        # Apply minimum bound if specified
        if model_name in self._min_values:
            value = max(value, self._min_values[model_name])

        # Apply maximum bound if specified
        if model_name in self._max_values:
            value = min(value, self._max_values[model_name])

        return value

    def _apply_active_rates(self, to_time: datetime):
        """Apply all active constant rates up to the specified time.
        
        Combines multiple simultaneous rates according to the model's combination mode.
        
        Args:
            to_time: Time to apply rates until
        """
        for model_name, rate_list in self._active_rates.items():
            if not rate_list:  # Empty list means no active rates
                continue
                
            # Get last profile point
            profile = self.profiles[model_name]
            if not profile:
                continue
                
            last_time, last_value = profile[-1]
            
            # Skip if we've already computed to this time
            if last_time >= to_time:
                continue
            
            # Combine rates according to combination mode
            mode = self._combination_modes.get(model_name, CombinationMode.ADD)
            rates = [r for _, r in rate_list]
            
            if mode == CombinationMode.ADD:
                combined_rate = sum(rates)
            elif mode == CombinationMode.MAX:
                combined_rate = max(rates)
            elif mode == CombinationMode.MIN:
                combined_rate = min(rates)
            elif mode == CombinationMode.EXCLUSIVE:
                # Should have been caught earlier, but handle it here too
                if len(rates) > 1:
                    raise ValueError(f"Model '{model_name}' has EXCLUSIVE mode but has {len(rates)} active rates")
                combined_rate = rates[0]
            else:
                combined_rate = sum(rates)  # Default to ADD
            
            # Compute change, clamped to bounds
            dt = (to_time - last_time).total_seconds()
            delta = combined_rate * dt
            new_value = self._clamp_value(model_name, last_value + delta)

            # Update current value and add profile point
            self._current_values[model_name] = new_value
            self.add_profile_point(model_name, to_time, new_value)
            
    def check_constraint(self, constraint, time: datetime) -> bool:
        """Check if a ModeledValueConstraint is satisfied at a given time.
        
        Args:
            constraint: A ModeledValueConstraint to check
            time: The time at which to check the constraint
            
        Returns:
            True if the constraint is satisfied, False otherwise
        """
        value = self.get_value_at_time(constraint.model_name, time)
        if value is None:
            # Model not tracked, assume constraint is violated
            return False
        
        # Evaluate comparison
        if constraint.comparison == '>':
            return value > constraint.threshold
        elif constraint.comparison == '>=':
            return value >= constraint.threshold
        elif constraint.comparison == '<':
            return value < constraint.threshold
        elif constraint.comparison == '<=':
            return value <= constraint.threshold
        elif constraint.comparison == '==':
            return value == constraint.threshold
        elif constraint.comparison == '!=':
            return value != constraint.threshold
        else:
            raise ValueError(f"Unknown comparison operator: {constraint.comparison}")
            
    def get_constraint_violations(self, activity, check_descendants: bool = True) -> List[Tuple[Any, datetime, str]]:
        """Find all ModeledValueConstraint violations for an activity.
        
        Args:
            activity: The activity to check
            check_descendants: If True, also check constraints on child activities
            
        Returns:
            List of tuples (activity, time, message) for each violation
        """
        violations = []
        
        def check_activity(act):
            if not hasattr(act, 'constraints') or not act.constraints:
                return
                
            for constraint in act.constraints:
                # Only check ModeledValueConstraints
                if constraint.__class__.__name__ != 'ModeledValueConstraint':
                    continue
                
                # Check at activity start time
                if not self.check_constraint(constraint, act.begin_time):
                    value = self.get_value_at_time(constraint.model_name, act.begin_time)
                    message = (f"Constraint violated: {constraint.model_name} = {value} "
                             f"does not satisfy {constraint.comparison} {constraint.threshold}")
                    violations.append((act, act.begin_time, message))
        
        # Check this activity
        check_activity(activity)
        
        # Check descendants if requested
        if check_descendants and hasattr(activity, 'activities') and activity.activities:
            for child in activity.activities:
                violations.extend(self.get_constraint_violations(child, check_descendants=True))
        
        return violations
    
    def plot(self, 
             model_names: Optional[List[str]] = None,
             title: str = "Modeled Values Over Time",
             figure_height: Optional[int] = None,
             figure_width: Optional[int] = None,
             background_color: str = '#fcfcfc',
             axis_line_color: str = '#555555',
             **kwargs):
        """Plot the modeled value profiles over time using tts_dtat.
        
        Args:
            model_names: List of model names to plot. If None, plots all models.
            title: Title for the plot
            figure_height: Height of figure in pixels (auto-calculated if None)
            figure_width: Width of figure in pixels
            background_color: Background color for the plot
            axis_line_color: Color for axis lines
            
        Returns:
            plotly.graph_objects.Figure: The plotly figure object
            
        Raises:
            ImportError: If tts_dtat is not installed
            
        Examples:
            >>> scheduler.compute_model({'battery_charge': 100.0, 'data_volume': 0.0})
            >>> fig = scheduler.modeled_values.plot()
            >>> fig.show()
            
            >>> # Plot specific models
            >>> fig = scheduler.modeled_values.plot(['battery_charge', 'data_volume'])
            >>> fig.write_html('model_plot.html')
        """
        
        # Determine which models to plot
        if model_names is None:
            model_names = list(self.profiles.keys())
        else:
            # Validate model names
            for name in model_names:
                if name not in self.profiles:
                    raise ValueError(f"Model '{name}' not found in profiles")
        
        if not model_names:
            raise ValueError("No models to plot")
        
        # Convert profiles to pandas DataFrame in dtat format
        # The dtat format expects columns: ['scet', 'name', 'value']
        data_rows = []
        
        for model_name in model_names:
            profile = self.profiles[model_name]
            
            if not profile:
                # If no profile points, use initial value at a dummy time
                initial_val = self.initial_values.get(model_name, 0.0)
                # Use epoch if no profile data
                dummy_time = datetime(1970, 1, 1, 0, 0, 0)
                data_rows.append({
                    'scet': dummy_time,
                    'name': model_name,
                    'value': initial_val
                })
            else:
                # Add all profile points
                for time, value in profile:
                    data_rows.append({
                        'scet': time,
                        'name': model_name,
                        'value': value
                    })
        
        # Create DataFrame
        df = pd.DataFrame(data_rows)
        
        # Ensure proper column order
        df = df[['scet', 'name', 'value']]
        
        # Sort by time
        df = df.sort_values('scet')
        
        # Create y_vars structure for make_stacked_graph
        # Each model gets its own subplot
        y_vars = [[model_name] for model_name in model_names]
        
        # Use make_stacked_graph from tts_dtat
        # Use default linear interpolation - this is correct for:
        # - CONSTANT_RATE effects (shows gradual change as sloped line)
        # - IMPULSE effects (shows as near-vertical line, acceptable)
        # - STEPPED effects (shows as diagonal transitions, acceptable)
        graph, _, _, _ = dtat_plot.make_stacked_graph(
            data=df,
            y_vars=y_vars,
            x_var='scet',
            figure_title=title,
            figure_height=figure_height,
            figure_width=figure_width,
            background_color=background_color,
            axis_line_color=axis_line_color,
            plot_lines=True,
            doy=True,  # Format dates nicely
            **kwargs
        )
        
        return graph
