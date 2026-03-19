"""
Unit tests for combination modes in the modeled values system.

Tests how multiple simultaneous effects on the same model are combined
using different combination modes (ADD, MAX, MIN, EXCLUSIVE).
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from tts_plan.activity import Activity
from tts_plan.modeled_values import (
    ModeledValues, Effect, EffectType, EffectTiming, CombinationMode
)

try:
    from tts_html_utils.core.compiler import HtmlCompiler
    from tts_html_utils.core.components.plot import PlotBase
    from tts_html_utils.core.components.text import Heading1, Heading2, Paragraph
    HTML_UTILS_AVAILABLE = True
except ImportError:
    HTML_UTILS_AVAILABLE = False


class SimpleActivity(Activity):
    """Simple concrete activity class for testing."""
    TYPE = "SimpleActivity"
    NAME = "Simple Activity"
    DESCRIPTION = "A simple activity for testing"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


@pytest.fixture
def base_time():
    """Return a standard base time for tests."""
    return datetime(2026, 1, 1, 10, 0, 0)


# Helper function to create HTML test outputs
def save_plot_to_html(fig, test_name, description=""):
    """Save a plot to an HTML file in test_files/combination_modes."""
    if not HTML_UTILS_AVAILABLE:
        return
    
    # Create output directory
    test_dir = Path(__file__).parent / "test_files" / "combination_modes"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create HTML compiler
    compiler = HtmlCompiler(title=f"Combination Modes Test: {test_name}")
    
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


# ADD mode tests (default)
def test_add_mode_multiple_drains(base_time):
    """Test ADD mode with multiple activities draining the same resource."""
    mv = ModeledValues()
    mv.register_model('battery_charge', initial_value=100.0, 
                     combination_mode=CombinationMode.ADD)
    
    # Two activities with overlapping battery drains
    activity1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=2),
        name="Activity 1"
    )
    activity1.add_effect('battery_charge', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, -2.0)
    
    activity2 = SimpleActivity(
        begin_time=base_time + timedelta(hours=1),
        duration=timedelta(hours=2),
        name="Activity 2"
    )
    activity2.add_effect('battery_charge', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, -3.0)
    
    mv.compute_profile_from_activities(
        [activity1, activity2],
        base_time,
        base_time + timedelta(hours=4)
    )
    
    # At 1 hour: only activity1 running at -2/s for 3600s
    value_at_1h = mv.get_value_at_time('battery_charge', base_time + timedelta(hours=1))
    assert value_at_1h == pytest.approx(100.0 - 2.0 * 3600)
    
    # At 2 hours: both activities running at -2 + -3 = -5/s
    # From 0-1h: drained 2*3600 = 7200
    # From 1-2h: drained 5*3600 = 18000
    # Total: 100 - 7200 - 18000 = 74800
    value_at_2h = mv.get_value_at_time('battery_charge', base_time + timedelta(hours=2))
    assert value_at_2h == pytest.approx(100.0 - 7200 - 18000)
    
    # Plot
    fig = mv.plot(model_names=['battery_charge'],
                  title="ADD Mode - Multiple Battery Drains")
    save_plot_to_html(fig, "test_add_mode",
                     "Two overlapping activities drain battery. Rates add: -2 W/s + -3 W/s = -5 W/s during overlap.")


# MAX mode tests
def test_max_mode_keepout_zones(base_time):
    """Test MAX mode for keepout zones where we take the maximum risk."""
    mv = ModeledValues()
    mv.register_model('keepout_risk', initial_value=0.0, 
                     combination_mode=CombinationMode.MAX)
    
    # Two activities with different risk levels
    activity1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=2),
        name="Low Risk Zone"
    )
    activity1.add_effect('keepout_risk', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, 2.0)  # Risk increases at 2/s
    
    activity2 = SimpleActivity(
        begin_time=base_time + timedelta(hours=1),
        duration=timedelta(hours=2),
        name="High Risk Zone"
    )
    activity2.add_effect('keepout_risk', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, 5.0)  # Risk increases at 5/s
    
    mv.compute_profile_from_activities(
        [activity1, activity2],
        base_time,
        base_time + timedelta(hours=4)
    )
    
    # At 2 hours: activity1 ends (event time with profile point)
    # From 0-1h: rate = 2.0, delta = 2.0 * 3600 = 7200
    # From 1-2h: rate = max(2.0, 5.0) = 5.0, delta = 5.0 * 3600 = 18000
    # Total: 0 + 7200 + 18000 = 25200
    value_at_2h = mv.get_value_at_time('keepout_risk', base_time + timedelta(hours=2))
    assert value_at_2h == pytest.approx(7200 + 18000)
    
    # Plot
    fig = mv.plot(model_names=['keepout_risk'],
                  title="MAX Mode - Keepout Risk")
    save_plot_to_html(fig, "test_max_mode",
                     "Two overlapping keepout zones. During overlap, uses MAX rate: max(2, 5) = 5.")


# MIN mode tests
def test_min_mode_efficiency(base_time):
    """Test MIN mode for efficiency where we take the minimum (bottleneck)."""
    mv = ModeledValues()
    mv.register_model('throughput', initial_value=0.0, 
                     combination_mode=CombinationMode.MIN)
    
    # Two activities with different throughput rates
    activity1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=2),
        name="Fast Process"
    )
    activity1.add_effect('throughput', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, 10.0)
    
    activity2 = SimpleActivity(
        begin_time=base_time + timedelta(hours=1),
        duration=timedelta(hours=2),
        name="Slow Process"
    )
    activity2.add_effect('throughput', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, 3.0)  # Bottleneck
    
    mv.compute_profile_from_activities(
        [activity1, activity2],
        base_time,
        base_time + timedelta(hours=4)
    )
    
    # At 2 hours: activity1 ends (event time with profile point)
    # From 0-1h: rate = 10.0, delta = 10.0 * 3600 = 36000
    # From 1-2h: rate = min(10.0, 3.0) = 3.0, delta = 3.0 * 3600 = 10800
    # Total: 0 + 36000 + 10800 = 46800
    value_at_2h = mv.get_value_at_time('throughput', base_time + timedelta(hours=2))
    assert value_at_2h == pytest.approx(36000 + 10800)
    
    # Plot
    fig = mv.plot(model_names=['throughput'],
                  title="MIN Mode - Throughput Bottleneck")
    save_plot_to_html(fig, "test_min_mode",
                     "Two overlapping processes. During overlap, uses MIN rate (bottleneck): min(10, 3) = 3.")


# EXCLUSIVE mode tests
def test_exclusive_mode_on_off_state(base_time):
    """Test EXCLUSIVE mode for on/off states where only one effect is allowed."""
    mv = ModeledValues()
    mv.register_model('power_state', initial_value=0.0, 
                     combination_mode=CombinationMode.EXCLUSIVE)
    
    # Single activity turning something on
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Power On"
    )
    activity.add_effect('power_state', EffectType.STEPPED, 
                       EffectTiming.DURING, 1.0)
    
    mv.compute_profile_from_activities(
        [activity],
        base_time,
        base_time + timedelta(hours=2)
    )
    
    # Should be 1.0 during activity, 0.0 outside
    value_during = mv.get_value_at_time('power_state', base_time + timedelta(minutes=30))
    assert value_during == pytest.approx(1.0)
    
    value_after = mv.get_value_at_time('power_state', base_time + timedelta(hours=1.5))
    assert value_after == pytest.approx(0.0)
    
    # Plot
    fig = mv.plot(model_names=['power_state'],
                  title="EXCLUSIVE Mode - Power On/Off State")
    save_plot_to_html(fig, "test_exclusive_mode",
                     "Single activity controls power state. EXCLUSIVE mode ensures only one effect at a time.")


def test_exclusive_mode_conflict(base_time):
    """Test that EXCLUSIVE mode raises error when multiple effects overlap."""
    mv = ModeledValues()
    mv.register_model('instrument_mode', initial_value=0.0, 
                     combination_mode=CombinationMode.EXCLUSIVE)
    
    # Two overlapping activities trying to control the same instrument
    activity1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=2),
        name="Imaging Mode"
    )
    activity1.add_effect('instrument_mode', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, 1.0)
    
    activity2 = SimpleActivity(
        begin_time=base_time + timedelta(hours=1),
        duration=timedelta(hours=2),
        name="Spectroscopy Mode"
    )
    activity2.add_effect('instrument_mode', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, 2.0)
    
    # Should raise ValueError due to conflict
    with pytest.raises(ValueError, match="EXCLUSIVE.*multiple"):
        mv.compute_profile_from_activities(
            [activity1, activity2],
            base_time,
            base_time + timedelta(hours=4)
        )


def test_add_mode_is_default(base_time):
    """Test that ADD mode is the default when not specified."""
    mv = ModeledValues()
    # Don't specify combination_mode - should default to ADD
    mv.register_model('battery_charge', initial_value=100.0)
    
    # Two overlapping drains
    activity1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Activity 1"
    )
    activity1.add_effect('battery_charge', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, -2.0)
    
    activity2 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Activity 2"
    )
    activity2.add_effect('battery_charge', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, -3.0)
    
    mv.compute_profile_from_activities(
        [activity1, activity2],
        base_time,
        base_time + timedelta(hours=2)
    )
    
    # Should add rates: -2 + -3 = -5 per second for 3600 seconds
    value_at_1h = mv.get_value_at_time('battery_charge', base_time + timedelta(hours=1))
    assert value_at_1h == pytest.approx(100.0 - 5.0 * 3600)
