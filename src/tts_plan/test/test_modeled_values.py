"""
Unit tests for the modeled values system (pytest style).

This module tests the modeling functionality for tracking state variables
over time as activities execute, including:
- Effect types (constant rate, impulse, stepped)
- Effect timing (at start, during, at end)
- Profile computation from activity effects
- ModeledValueConstraint validation
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from tts_plan.activity import Activity
from tts_plan.scheduler import Scheduler
from tts_plan.modeled_values import (
    ModeledValues, Effect, EffectType, EffectTiming
)


from tts_html_utils.core.compiler import HtmlCompiler
from tts_html_utils.core.components.plot import PlotBase
from tts_html_utils.core.components.text import Heading1, Heading2, Paragraph
from tts_html_utils.core.components.misc import Div


class SimpleActivity(Activity):
    """Simple concrete activity class for testing."""
    TYPE = "SimpleActivity"
    NAME = "Simple Activity"
    DESCRIPTION = "A simple activity for testing"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class TestScheduler(Scheduler):
    """Simple test scheduler."""
    MISSION = "TEST"
    
    def build_schedule(self):
        """Not implemented for testing."""
        pass


# Fixtures
@pytest.fixture
def base_time():
    """Return a base time for creating activities."""
    return datetime(2026, 1, 1, 10, 0, 0)


@pytest.fixture
def modeled_values():
    """Return a ModeledValues instance with some registered models."""
    mv = ModeledValues()
    mv.register_model('battery_charge', initial_value=100.0)
    mv.register_model('data_volume', initial_value=0.0)
    return mv


@pytest.fixture
def test_scheduler(base_time):
    """Return a test scheduler with start and end times."""
    return TestScheduler(
        start_time=base_time,
        end_time=base_time + timedelta(hours=5)
    )


# Helper function to create HTML test outputs
def save_plot_to_html(fig, test_name, description=""):
    """Save a plot to an HTML file in test_files/modeled_values."""
    
    # Create output directory
    test_dir = Path(__file__).parent / "test_files" / "modeled_values"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create HTML compiler
    compiler = HtmlCompiler(title=f"Modeled Values Test: {test_name}")
    
    # Add title and description
    compiler.add_body_component(Heading1(test_name))
    if description:
        compiler.add_body_component(Paragraph(description))
    
    # Add the plot
    compiler.add_body_component(PlotBase(fig=fig, include_plotlyjs=True))
    
    # Render to file
    output_path = test_dir / f"{test_name}.html"
    compiler.render_to_file(str(output_path))
    print(f"\n  → Test plot saved to: {output_path}")


# Basic ModeledValues tests
def test_register_model(modeled_values):
    """Test registering a new modeled value."""
    modeled_values.register_model('temperature', initial_value=20.0)
    
    assert 'temperature' in modeled_values.initial_values
    assert modeled_values.initial_values['temperature'] == 20.0


def test_get_value_at_time_initial(modeled_values, base_time):
    """Test getting initial value when no profile points exist."""
    value = modeled_values.get_value_at_time('battery_charge', base_time)
    assert value == 100.0


def test_add_profile_point(modeled_values, base_time):
    """Test adding a profile point."""
    time1 = base_time + timedelta(minutes=30)
    modeled_values.add_profile_point('battery_charge', time1, 95.0)
    
    value = modeled_values.get_value_at_time('battery_charge', time1)
    assert value == 95.0


def test_profile_step_interpolation(modeled_values, base_time):
    """Test that values use step-wise interpolation (hold last value)."""
    time1 = base_time
    time2 = base_time + timedelta(hours=1)
    
    modeled_values.add_profile_point('battery_charge', time1, 100.0)
    modeled_values.add_profile_point('battery_charge', time2, 80.0)
    
    # Check value halfway between points
    time_mid = base_time + timedelta(minutes=30)
    value = modeled_values.get_value_at_time('battery_charge', time_mid)
    
    # Should use step-wise interpolation: hold value at t1 until t2
    assert value == pytest.approx(100.0)


# Effect tests
def test_add_effect_to_activity(base_time):
    """Test adding an effect to an activity."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Test Activity"
    )
    
    effect = activity.add_effect(
        'battery_charge',
        EffectType.CONSTANT_RATE,
        EffectTiming.DURING,
        -5.0
    )
    
    assert len(activity.effects) == 1
    assert effect.model_name == 'battery_charge'
    assert effect.value == -5.0


def test_remove_effect(base_time):
    """Test removing effects from an activity."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1)
    )
    
    activity.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -5.0)
    activity.add_effect('data_volume', EffectType.IMPULSE, EffectTiming.AT_END, 100.0)
    
    assert len(activity.effects) == 2
    
    activity.remove_effect('battery_charge')
    assert len(activity.effects) == 1
    assert activity.effects[0].model_name == 'data_volume'


# Constant rate effect tests
def test_constant_rate_effect_during_activity(modeled_values, base_time):
    """Test constant rate effect applied during an activity."""
    # Create activity with -5 W/s drain during execution
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(seconds=10),
        name="Power Drain Activity"
    )
    activity.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -5.0)
    
    # Compute profile
    modeled_values.compute_profile_from_activities(
        [activity],
        base_time,
        base_time + timedelta(hours=1)
    )
    
    # Check value at activity end (should have lost 5*10 = 50)
    value_at_end = modeled_values.get_value_at_time('battery_charge', activity.end_time)
    assert value_at_end == pytest.approx(50.0)

    fig = modeled_values.plot(model_names=['battery_charge'],
                              title="Constant Rate Effect During Activity")
    save_plot_to_html(fig, "test_constant_rate_effect_during_activity",
                     "Power drain activity (-5 W/s) during 10 seconds.")


def test_multiple_constant_rate_effects(modeled_values, base_time):
    """Test multiple overlapping constant rate effects."""
    # Two activities with overlapping drains
    activity1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(seconds=20),
        name="Activity 1"
    )
    activity1.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -2.0)
    
    activity2 = SimpleActivity(
        begin_time=base_time + timedelta(seconds=10),
        duration=timedelta(seconds=20),
        name="Activity 2"
    )
    activity2.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -3.0)
    
    # Compute profile
    modeled_values.compute_profile_from_activities(
        [activity1, activity2],
        base_time,
        base_time + timedelta(hours=1)
    )
    
    # At t=10s: only activity1 running, lost 2*10 = 20
    value_at_10s = modeled_values.get_value_at_time('battery_charge', base_time + timedelta(seconds=10))
    assert value_at_10s == pytest.approx(80.0)
    
    # At t=20s: both running for 10s, lost 20 + (2+3)*10 = 70
    value_at_20s = modeled_values.get_value_at_time('battery_charge', base_time + timedelta(seconds=20))
    assert value_at_20s == pytest.approx(30.0)
    
    # At t=30s: only activity2 running for final 10s, lost 70 + 3*10 = 100
    value_at_30s = modeled_values.get_value_at_time('battery_charge', base_time + timedelta(seconds=30))
    assert value_at_30s == pytest.approx(0.0)
    
    # Plot the battery charge profile
    fig = modeled_values.plot(model_names=['battery_charge'],
                              title="Multiple Overlapping Constant Rate Effects")
    save_plot_to_html(fig, "test_multiple_constant_rate_effects",
                     "Two activities with overlapping battery drains: Activity 1 (-2 units/s for 20s) and Activity 2 (-3 units/s for 20s, starting at t=10s).")


# Impulse effect tests
def test_impulse_effect_at_start(modeled_values, base_time):
    """Test impulse effect applied at activity start."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Impulse Start Activity"
    )
    activity.add_effect('data_volume', EffectType.IMPULSE, EffectTiming.AT_START, 50.0)
    
    modeled_values.compute_profile_from_activities(
        [activity],
        base_time,
        base_time + timedelta(hours=2)
    )
    
    # Value should jump at start
    value_at_start = modeled_values.get_value_at_time('data_volume', activity.begin_time)
    assert value_at_start == pytest.approx(50.0)
    
    # Plot the data volume profile
    fig = modeled_values.plot(model_names=['data_volume'],
                              title="Impulse Effect at Activity Start")
    save_plot_to_html(fig, "test_impulse_effect_at_start",
                     "Data volume jumps by +50 units instantaneously at activity start.")


def test_impulse_effect_at_end(modeled_values, base_time):
    """Test impulse effect applied at activity end."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Impulse End Activity"
    )
    activity.add_effect('data_volume', EffectType.IMPULSE, EffectTiming.AT_END, 100.0)
    
    modeled_values.compute_profile_from_activities(
        [activity],
        base_time,
        base_time + timedelta(hours=2)
    )
    
    # Value should stay at 0 until end
    value_before_end = modeled_values.get_value_at_time('data_volume', 
                                                        activity.end_time - timedelta(seconds=1))
    assert value_before_end == pytest.approx(0.0)
    
    # Value should jump at end
    value_at_end = modeled_values.get_value_at_time('data_volume', activity.end_time)
    assert value_at_end == pytest.approx(100.0)
    
    # Plot the data volume profile
    fig = modeled_values.plot(model_names=['data_volume'],
                              title="Impulse Effect at Activity End")
    save_plot_to_html(fig, "test_impulse_effect_at_end",
                     "Data volume stays at 0 during activity, then jumps by +100 units at activity end.")


# Stepped effect tests
def test_stepped_effect(modeled_values, base_time):
    """Test stepped effect (value jumps during activity then returns)."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Stepped Activity"
    )
    # Power consumption steps up by 50W during activity
    activity.add_effect('power_consumption', EffectType.STEPPED, EffectTiming.DURING, 50.0)
    
    modeled_values.register_model('power_consumption', initial_value=10.0)
    modeled_values.compute_profile_from_activities(
        [activity],
        base_time,
        base_time + timedelta(hours=2)
    )
    
    # Value should jump to 60 at start
    value_at_start = modeled_values.get_value_at_time('power_consumption', activity.begin_time)
    assert value_at_start == pytest.approx(60.0)
    
    # Value should stay at 60 during activity
    value_during = modeled_values.get_value_at_time('power_consumption', 
                                                    base_time + timedelta(minutes=30))
    assert value_during == pytest.approx(60.0)
    
    # Value should return to 10 at end
    value_at_end = modeled_values.get_value_at_time('power_consumption', activity.end_time)
    assert value_at_end == pytest.approx(10.0)
    
    # Plot the power consumption profile
    fig = modeled_values.plot(model_names=['power_consumption'],
                              title="Stepped Effect During Activity")
    save_plot_to_html(fig, "test_stepped_effect",
                     "Power consumption steps from 10W to 60W at activity start, stays constant during activity, then returns to 10W at activity end.")


# Child activity effect tests
def test_child_activity_effects(modeled_values, base_time):
    """Test that effects from child activities are processed."""
    parent = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=2),
        name="Parent"
    )
    
    child = SimpleActivity(
        begin_time=base_time + timedelta(minutes=30),
        duration=timedelta(minutes=30),
        name="Child"
    )
    child.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -10.0)
    parent.add_child(child)
    
    modeled_values.compute_profile_from_activities(
        [parent],
        base_time,
        base_time + timedelta(hours=3)
    )
    
    # Should have drain during child activity (30 minutes = 1800 seconds)
    value_at_child_end = modeled_values.get_value_at_time('battery_charge', child.end_time)
    assert value_at_child_end == pytest.approx(100.0 - 10.0 * 1800)
    
    # Plot the battery charge profile
    fig = modeled_values.plot(model_names=['battery_charge'],
                              title="Child Activity Effects")
    save_plot_to_html(fig, "test_child_activity_effects",
                     "Parent activity has a child activity that drains battery at -10 units/s for 30 minutes, starting 30 minutes after parent begins.")


# Constraint checking tests
def test_check_constraint_satisfied(modeled_values, base_time):
    """Test checking a constraint that is satisfied."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1)
    )
    constraint = activity.add_model_constraint('battery_charge', 50.0, '>')
    
    modeled_values.add_profile_point('battery_charge', base_time, 100.0)
    
    assert modeled_values.check_constraint(constraint, base_time) is True


def test_check_constraint_violated(modeled_values, base_time):
    """Test checking a constraint that is violated."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1)
    )
    constraint = activity.add_model_constraint('battery_charge', 50.0, '>')
    
    modeled_values.add_profile_point('battery_charge', base_time, 30.0)
    
    assert modeled_values.check_constraint(constraint, base_time) is False


def test_get_constraint_violations(modeled_values, base_time):
    """Test finding constraint violations for an activity."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Constrained Activity"
    )
    activity.add_model_constraint('battery_charge', 50.0, '>=')
    
    # Set battery below threshold
    modeled_values.add_profile_point('battery_charge', base_time, 30.0)
    
    violations = modeled_values.get_constraint_violations(activity)
    
    assert len(violations) == 1
    assert violations[0][0] == activity
    assert violations[0][1] == base_time


# Scheduler integration tests
def test_scheduler_compute_model(test_scheduler, base_time):
    """Test computing model through scheduler."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Test Activity"
    )
    activity.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -5.0)
    
    test_scheduler.add_activity(activity)
    test_scheduler.compute_model({'battery_charge': 100.0})
    
    # Check that profile was computed
    value_at_end = test_scheduler.modeled_values.get_value_at_time(
        'battery_charge',
        activity.end_time
    )
    assert value_at_end == pytest.approx(100.0 - 5.0 * 3600)
    
    # Plot the battery charge profile
    fig = test_scheduler.modeled_values.plot(model_names=['battery_charge'],
                                             title="Scheduler Compute Model Test")
    save_plot_to_html(fig, "test_scheduler_compute_model",
                     "Testing scheduler.compute_model() with a single activity that drains battery at -5 units/s for 1 hour.")


def test_scheduler_validate_constraints(test_scheduler, base_time):
    """Test validating constraints through scheduler."""
    activity = SimpleActivity(
        begin_time=base_time + timedelta(hours=2),
        duration=timedelta(hours=1),
        name="Constrained Activity"
    )
    activity.add_model_constraint('battery_charge', 50.0, '>=')
    
    # Add draining activity before it
    drain_activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=2),
        name="Drain Activity"
    )
    drain_activity.add_effect('battery_charge', EffectType.CONSTANT_RATE, 
                             EffectTiming.DURING, -10.0)
    
    test_scheduler.add_activity(drain_activity)
    test_scheduler.add_activity(activity)
    
    # Compute model
    test_scheduler.compute_model({'battery_charge': 100.0})
    
    # Validate - should find violation
    violations = test_scheduler.validate_model_constraints()
    
    # Battery will be at 100 - 10*7200 = -71900 (way below 50)
    assert len(violations) >= 1
    
    # Plot the battery charge profile showing the violation
    fig = test_scheduler.modeled_values.plot(model_names=['battery_charge'],
                                             title="Scheduler Validate Constraints - Violation")
    save_plot_to_html(fig, "test_scheduler_validate_constraints",
                     "Drain activity runs for 2 hours at -10 units/s, leaving battery well below the 50-unit constraint threshold for the subsequent activity.")


def test_scheduler_no_violations(test_scheduler, base_time):
    """Test that valid constraints don't produce violations."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Constrained Activity"
    )
    activity.add_model_constraint('battery_charge', 50.0, '>=')
    
    test_scheduler.add_activity(activity)
    test_scheduler.compute_model({'battery_charge': 100.0})
    
    violations = test_scheduler.validate_model_constraints()
    assert len(violations) == 0
    
    # Plot the battery charge profile showing no violations
    fig = test_scheduler.modeled_values.plot(model_names=['battery_charge'],
                                             title="Scheduler Validate Constraints - No Violations")
    save_plot_to_html(fig, "test_scheduler_no_violations",
                     "Battery starts at 100 units with no draining activities, constraint of >=50 is satisfied throughout.")


def test_complex_scenario(test_scheduler, base_time):
    """Test a complex scenario with multiple activities and effects."""
    # Activity 1: Generates data
    act1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Science Observation"
    )
    act1.add_effect('data_volume', EffectType.IMPULSE, EffectTiming.AT_END, 500.0)
    act1.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -2.0)
    
    # Activity 2: Downlinks data
    act2 = SimpleActivity(
        begin_time=base_time + timedelta(hours=2),
        duration=timedelta(hours=1),
        name="Downlink"
    )
    act2.add_effect('data_volume', EffectType.IMPULSE, EffectTiming.AT_END, -500.0)
    act2.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -5.0)
    act2.add_model_constraint('data_volume', 100.0, '>=')  # Must have data to downlink
    
    # Activity 3: Charging
    act3 = SimpleActivity(
        begin_time=base_time + timedelta(hours=3, minutes=30),
        duration=timedelta(hours=1),
        name="Solar Charging"
    )
    act3.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, 10.0)
    
    test_scheduler.add_activity(act1)
    test_scheduler.add_activity(act2)
    test_scheduler.add_activity(act3)
    
    # Compute model
    test_scheduler.compute_model({
        'battery_charge': 100.0,
        'data_volume': 0.0
    })
    
    # Check data volume profile
    data_after_obs = test_scheduler.modeled_values.get_value_at_time('data_volume', act1.end_time)
    assert data_after_obs == pytest.approx(500.0)
    
    data_after_downlink = test_scheduler.modeled_values.get_value_at_time('data_volume', act2.end_time)
    assert data_after_downlink == pytest.approx(0.0)
    
    # Validate constraints
    violations = test_scheduler.validate_model_constraints()
    assert len(violations) == 0  # Constraint should be satisfied
    
    # Plot both battery charge and data volume profiles
    fig = test_scheduler.modeled_values.plot(model_names=['battery_charge', 'data_volume'],
                                             title="Complex Scenario - Multiple Activities")
    save_plot_to_html(fig, "test_complex_scenario",
                     "Complex scenario: (1) Science observation generates 500 data and drains battery, (2) Downlink removes data and drains battery, (3) Solar charging replenishes battery.")


# Plotting tests
def test_plot_single_model(modeled_values, base_time):
    """Test plotting a single model."""
    # Add some profile points
    modeled_values.add_profile_point('battery_charge', base_time, 100.0)
    modeled_values.add_profile_point('battery_charge', base_time + timedelta(hours=1), 80.0)
    modeled_values.add_profile_point('battery_charge', base_time + timedelta(hours=2), 60.0)
    
    # Create plot
    fig = modeled_values.plot(model_names=['battery_charge'], title="Battery Test")
    
    # Verify figure was created
    assert fig is not None
    assert len(fig.data) == 1  # One trace
    assert fig.data[0].name == 'battery_charge'
    assert len(fig.data[0].x) == 3  # Three data points
    
    # Save to HTML
    save_plot_to_html(fig, "test_plot_single_model",
                     "Testing a single battery charge model with three profile points.")


def test_plot_multiple_models(modeled_values, base_time):
    """Test plotting multiple models."""
    # Add profile points for both models
    modeled_values.add_profile_point('battery_charge', base_time, 100.0)
    modeled_values.add_profile_point('battery_charge', base_time + timedelta(hours=1), 80.0)
    
    modeled_values.add_profile_point('data_volume', base_time, 0.0)
    modeled_values.add_profile_point('data_volume', base_time + timedelta(hours=1), 500.0)
    
    # Create plot
    fig = modeled_values.plot()
    
    # Verify figure was created with multiple subplots
    assert fig is not None
    assert len(fig.data) == 2  # Two traces
    

def test_plot_with_scheduler(test_scheduler, base_time):
    """Test plotting directly from scheduler."""
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Test Activity"
    )
    activity.add_effect('battery_charge', EffectType.CONSTANT_RATE, EffectTiming.DURING, -5.0)
    
    test_scheduler.add_activity(activity)
    test_scheduler.compute_model({'battery_charge': 100.0})
    
    # Create plot
    fig = test_scheduler.modeled_values.plot(title="Scheduler Model Test")
    
    assert fig is not None
    assert fig.layout.title.text == "Scheduler Model Test"
    

def test_plot_empty_profile(modeled_values):
    """Test plotting when profile has no data points."""
    modeled_values.register_model('empty_model', initial_value=50.0)
    
    # Should still create a plot but with minimal data
    fig = modeled_values.plot(model_names=['empty_model'])
    
    assert fig is not None
    assert len(fig.data) == 1
    

def test_plot_invalid_model_name(modeled_values):
    """Test that plotting with invalid model name raises error."""
    with pytest.raises(ValueError, match="Model 'nonexistent' not found"):
        modeled_values.plot(model_names=['nonexistent'])


# Combination mode tests for STEPPED effects
def test_stepped_effect_min_mode(base_time):
    """Test STEPPED effects with MIN combination mode (picks smallest value)."""
    from tts_plan.modeled_values import CombinationMode
    
    mv = ModeledValues()
    mv.register_model('constraint_value', initial_value=0.0, combination_mode=CombinationMode.MIN)
    
    # Two overlapping activities with different constraint values
    activity1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=2),
        name="Wide Constraint"
    )
    activity1.add_effect('constraint_value', EffectType.STEPPED, EffectTiming.DURING, 10.0)
    
    activity2 = SimpleActivity(
        begin_time=base_time + timedelta(minutes=30),
        duration=timedelta(hours=1),
        name="Narrow Constraint"
    )
    activity2.add_effect('constraint_value', EffectType.STEPPED, EffectTiming.DURING, 5.0)
    
    mv.compute_profile_from_activities(
        [activity1, activity2],
        base_time,
        base_time + timedelta(hours=3)
    )
    
    # Before activity2 starts: only activity1, value = 10
    value_before_overlap = mv.get_value_at_time('constraint_value', base_time + timedelta(minutes=15))
    assert value_before_overlap == pytest.approx(10.0)
    
    # During overlap: MIN(10, 5) = 5
    value_during_overlap = mv.get_value_at_time('constraint_value', base_time + timedelta(hours=1))
    assert value_during_overlap == pytest.approx(5.0)
    
    # After activity2 ends: only activity1, value = 10
    value_after_overlap = mv.get_value_at_time('constraint_value', base_time + timedelta(hours=1, minutes=35))
    assert value_after_overlap == pytest.approx(10.0)
    
    # Plot the constraint value profile
    fig = mv.plot(model_names=['constraint_value'],
                  title="STEPPED Effect with MIN Combination Mode")
    save_plot_to_html(fig, "test_stepped_effect_min_mode",
                     "Two overlapping activities with MIN mode: Activity 1 (value=10) and Activity 2 (value=5). During overlap, MIN picks 5.")


def test_stepped_effect_max_mode(base_time):
    """Test STEPPED effects with MAX combination mode (picks largest value)."""
    from tts_plan.modeled_values import CombinationMode
    
    mv = ModeledValues()
    mv.register_model('constraint_value', initial_value=0.0, combination_mode=CombinationMode.MAX)
    
    # Two overlapping activities with different constraint values
    activity1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=2),
        name="Activity 1"
    )
    activity1.add_effect('constraint_value', EffectType.STEPPED, EffectTiming.DURING, -10.0)
    
    activity2 = SimpleActivity(
        begin_time=base_time + timedelta(minutes=30),
        duration=timedelta(hours=1),
        name="Activity 2"
    )
    activity2.add_effect('constraint_value', EffectType.STEPPED, EffectTiming.DURING, -5.0)
    
    mv.compute_profile_from_activities(
        [activity1, activity2],
        base_time,
        base_time + timedelta(hours=3)
    )
    
    # Before activity2 starts: only activity1, value = -10
    value_before_overlap = mv.get_value_at_time('constraint_value', base_time + timedelta(minutes=15))
    assert value_before_overlap == pytest.approx(-10.0)
    
    # During overlap: MAX(-10, -5) = -5 (largest/least negative)
    value_during_overlap = mv.get_value_at_time('constraint_value', base_time + timedelta(hours=1))
    assert value_during_overlap == pytest.approx(-5.0)
    
    # After activity2 ends: only activity1, value = -10
    value_after_overlap = mv.get_value_at_time('constraint_value', base_time + timedelta(hours=1, minutes=35))
    assert value_after_overlap == pytest.approx(-10.0)
    
    # Plot the constraint value profile
    fig = mv.plot(model_names=['constraint_value'],
                  title="STEPPED Effect with MAX Combination Mode")
    save_plot_to_html(fig, "test_stepped_effect_max_mode",
                     "Two overlapping activities with MAX mode: Activity 1 (value=-10) and Activity 2 (value=-5). During overlap, MAX picks -5 (least negative).")
