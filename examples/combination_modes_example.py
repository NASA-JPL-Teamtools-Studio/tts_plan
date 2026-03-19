"""
Example demonstrating different combination modes for modeled values.

This shows how to use ADD, MAX, MIN, and EXCLUSIVE modes to control
how multiple simultaneous effects are combined.
"""

from datetime import datetime, timedelta
from tts_plan.activity import Activity
from tts_plan.modeled_values import (
    ModeledValues, EffectType, EffectTiming, CombinationMode
)


class SimpleActivity(Activity):
    """Simple activity for demonstration."""
    TYPE = "SimpleActivity"
    NAME = "Simple"
    DESCRIPTION = "Simple activity"


def example_add_mode():
    """Example: ADD mode for power drain (default behavior)."""
    print("=" * 60)
    print("ADD MODE: Multiple power drains sum together")
    print("=" * 60)
    
    mv = ModeledValues()
    # ADD is the default, but we'll be explicit
    mv.register_model('battery_charge', initial_value=100.0, 
                     combination_mode=CombinationMode.ADD)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Instrument A draws 2 W
    instrument_a = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=2),
        name="Instrument A"
    )
    instrument_a.add_effect('battery_charge', EffectType.CONSTANT_RATE, 
                           EffectTiming.DURING, -2.0)
    
    # Instrument B draws 3 W, overlaps for 1 hour
    instrument_b = SimpleActivity(
        begin_time=base_time + timedelta(hours=1),
        duration=timedelta(hours=2),
        name="Instrument B"
    )
    instrument_b.add_effect('battery_charge', EffectType.CONSTANT_RATE, 
                           EffectTiming.DURING, -3.0)
    
    mv.compute_profile_from_activities(
        [instrument_a, instrument_b],
        base_time,
        base_time + timedelta(hours=4)
    )
    
    # Check values at key times
    print(f"\nInitial: {mv.get_value_at_time('battery_charge', base_time):.1f} units")
    print(f"After 1h (A only, -2/s): {mv.get_value_at_time('battery_charge', base_time + timedelta(hours=1)):.1f} units")
    print(f"After 1.5h (A+B, -2+-3=-5/s): {mv.get_value_at_time('battery_charge', base_time + timedelta(hours=1.5)):.1f} units")
    print(f"After 2h (A+B): {mv.get_value_at_time('battery_charge', base_time + timedelta(hours=2)):.1f} units")
    print(f"After 3h (B only, -3/s): {mv.get_value_at_time('battery_charge', base_time + timedelta(hours=3)):.1f} units")
    print("\n✓ Drains ADD together during overlap\n")


def example_max_mode():
    """Example: MAX mode for risk levels."""
    print("=" * 60)
    print("MAX MODE: Take maximum risk from overlapping zones")
    print("=" * 60)
    
    mv = ModeledValues()
    mv.register_model('radiation_risk', initial_value=0.0, 
                     combination_mode=CombinationMode.MAX)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Low radiation zone
    low_zone = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=3),
        name="Low Radiation Zone"
    )
    low_zone.add_effect('radiation_risk', EffectType.CONSTANT_RATE, 
                       EffectTiming.DURING, 1.0)  # Risk increases slowly
    
    # High radiation zone (overlaps)
    high_zone = SimpleActivity(
        begin_time=base_time + timedelta(hours=1),
        duration=timedelta(hours=2),
        name="High Radiation Zone"
    )
    high_zone.add_effect('radiation_risk', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, 5.0)  # Risk increases quickly
    
    mv.compute_profile_from_activities(
        [low_zone, high_zone],
        base_time,
        base_time + timedelta(hours=4)
    )
    
    print(f"\nInitial: {mv.get_value_at_time('radiation_risk', base_time):.1f} units")
    print(f"After 1h (low zone, +1/s): {mv.get_value_at_time('radiation_risk', base_time + timedelta(hours=1)):.1f} units")
    print(f"After 2h (MAX(1,5)=5/s): {mv.get_value_at_time('radiation_risk', base_time + timedelta(hours=2)):.1f} units")
    print(f"After 3h (low zone again): {mv.get_value_at_time('radiation_risk', base_time + timedelta(hours=3)):.1f} units")
    print("\n✓ Takes MAXIMUM risk rate during overlap\n")


def example_min_mode():
    """Example: MIN mode for throughput bottleneck."""
    print("=" * 60)
    print("MIN MODE: Throughput limited by slowest process")
    print("=" * 60)
    
    mv = ModeledValues()
    mv.register_model('data_processed', initial_value=0.0, 
                     combination_mode=CombinationMode.MIN)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Fast processor
    fast_cpu = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=3),
        name="Fast CPU"
    )
    fast_cpu.add_effect('data_processed', EffectType.CONSTANT_RATE, 
                       EffectTiming.DURING, 100.0)  # 100 MB/s
    
    # Slow disk I/O (bottleneck)
    slow_disk = SimpleActivity(
        begin_time=base_time + timedelta(hours=1),
        duration=timedelta(hours=2),
        name="Slow Disk"
    )
    slow_disk.add_effect('data_processed', EffectType.CONSTANT_RATE, 
                        EffectTiming.DURING, 20.0)  # Only 20 MB/s
    
    mv.compute_profile_from_activities(
        [fast_cpu, slow_disk],
        base_time,
        base_time + timedelta(hours=4)
    )
    
    print(f"\nInitial: {mv.get_value_at_time('data_processed', base_time):.1f} MB")
    print(f"After 1h (CPU only, 100 MB/s): {mv.get_value_at_time('data_processed', base_time + timedelta(hours=1)):.1f} MB")
    print(f"After 2h (MIN(100,20)=20 MB/s): {mv.get_value_at_time('data_processed', base_time + timedelta(hours=2)):.1f} MB")
    print(f"After 3h (CPU only again): {mv.get_value_at_time('data_processed', base_time + timedelta(hours=3)):.1f} MB")
    print("\n✓ Takes MINIMUM rate (bottleneck) during overlap\n")


def example_exclusive_mode():
    """Example: EXCLUSIVE mode for mutually exclusive operations."""
    print("=" * 60)
    print("EXCLUSIVE MODE: Only one effect allowed at a time")
    print("=" * 60)
    
    mv = ModeledValues()
    mv.register_model('transmitter_power', initial_value=0.0, 
                     combination_mode=CombinationMode.EXCLUSIVE)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Transmit at 10 W for 1 hour
    transmit_session_1 = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Transmit Session 1"
    )
    transmit_session_1.add_effect('transmitter_power', EffectType.CONSTANT_RATE, 
                                 EffectTiming.DURING, 0.0)  # Transmitting (use rate to track)
    
    # Transmit again later (no overlap)
    transmit_session_2 = SimpleActivity(
        begin_time=base_time + timedelta(hours=2),
        duration=timedelta(hours=1),
        name="Transmit Session 2"
    )
    transmit_session_2.add_effect('transmitter_power', EffectType.CONSTANT_RATE, 
                                 EffectTiming.DURING, 0.0)
    
    mv.compute_profile_from_activities(
        [transmit_session_1, transmit_session_2],
        base_time,
        base_time + timedelta(hours=4)
    )
    
    print(f"\nInitial: {mv.get_value_at_time('transmitter_power', base_time):.1f} W")
    print(f"At 0.5h (transmitting): {mv.get_value_at_time('transmitter_power', base_time + timedelta(minutes=30)):.1f} W")
    print(f"At 1.5h (idle): {mv.get_value_at_time('transmitter_power', base_time + timedelta(hours=1.5)):.1f} W")
    print(f"At 2.5h (transmitting): {mv.get_value_at_time('transmitter_power', base_time + timedelta(hours=2.5)):.1f} W")
    print("\n✓ Successfully schedules non-overlapping transmissions\n")
    
    # Now try with overlapping effects (should fail)
    print("Attempting overlapping EXCLUSIVE effects...")
    
    conflicting_activity = SimpleActivity(
        begin_time=base_time + timedelta(minutes=30),  # Overlaps with first activity
        duration=timedelta(hours=1),
        name="Conflicting Transmission"
    )
    conflicting_activity.add_effect('transmitter_power', EffectType.CONSTANT_RATE, 
                                   EffectTiming.DURING, 0.0)
    
    try:
        mv2 = ModeledValues()
        mv2.register_model('transmitter_power', initial_value=0.0, 
                          combination_mode=CombinationMode.EXCLUSIVE)
        mv2.compute_profile_from_activities(
            [transmit_session_1, conflicting_activity],
            base_time,
            base_time + timedelta(hours=4)
        )
        print("✗ ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"✓ Correctly raised error: {str(e)[:80]}...\n")


if __name__ == "__main__":
    example_add_mode()
    example_max_mode()
    example_min_mode()
    example_exclusive_mode()
    
    print("=" * 60)
    print("All combination mode examples completed!")
    print("=" * 60)
