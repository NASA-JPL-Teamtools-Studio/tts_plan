"""
Example demonstrating the simplified claims system.

Claims are now boolean - an activity either claims a resource or it doesn't.
For quantitative resource tracking (e.g., power consumption, data volume),
use ModeledValues instead.
"""

from datetime import datetime, timedelta
from enum import Enum, auto
from tts_plan.activity import Activity, Claim


class MyClaimables(Enum):
    """Example claimable resources for a mission."""
    INSTRUMENT_A = auto()
    INSTRUMENT_B = auto()
    TRANSMITTER = auto()
    CPU = auto()
    HIGH_GAIN_ANTENNA = auto()


class SimpleActivity(Activity):
    """Simple activity for demonstration."""
    TYPE = "SimpleActivity"
    NAME = "Simple"
    DESCRIPTION = "Simple activity"


def example_basic_claims():
    """Basic claim usage."""
    print("=" * 60)
    print("BASIC CLAIMS")
    print("=" * 60)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    # Create an activity and add claims
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Science Observation"
    )
    
    # Add claims - just specify the resource
    activity.add_claim(MyClaimables.INSTRUMENT_A)
    activity.add_claim(MyClaimables.CPU)
    
    print(f"\nActivity: {activity.name}")
    print(f"Claims: {activity.claims}")
    print(f"Number of claims: {len(activity.claims)}")
    
    # Access claim resources
    for claim in activity.claims:
        print(f"  - {claim.resource}")
    
    print("\n✓ Simple boolean claims\n")


def example_claims_with_metadata():
    """Claims with optional metadata."""
    print("=" * 60)
    print("CLAIMS WITH METADATA")
    print("=" * 60)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Data Downlink"
    )
    
    # Add claims with metadata for additional context
    activity.add_claim(MyClaimables.TRANSMITTER, 
                      metadata={"band": "X-band", "rate": "high"})
    activity.add_claim(MyClaimables.HIGH_GAIN_ANTENNA,
                      metadata={"pointing": "Earth"})
    
    print(f"\nActivity: {activity.name}")
    
    for claim in activity.claims:
        print(f"  Resource: {claim.resource}")
        if claim.metadata:
            print(f"    Metadata: {claim.metadata}")
    
    print("\n✓ Claims can have optional metadata\n")


def example_removing_claims():
    """Removing claims from an activity."""
    print("=" * 60)
    print("REMOVING CLAIMS")
    print("=" * 60)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Flexible Activity"
    )
    
    # Add multiple claims
    activity.add_claim(MyClaimables.INSTRUMENT_A)
    activity.add_claim(MyClaimables.INSTRUMENT_B)
    activity.add_claim(MyClaimables.CPU)
    
    print(f"\nInitial claims ({len(activity.claims)}):")
    for claim in activity.claims:
        print(f"  - {claim.resource}")
    
    # Remove a specific claim
    activity.remove_claim(MyClaimables.INSTRUMENT_B)
    
    print(f"\nAfter removing INSTRUMENT_B ({len(activity.claims)}):")
    for claim in activity.claims:
        print(f"  - {claim.resource}")
    
    print("\n✓ Claims can be removed\n")


def example_duplicate_prevention():
    """Adding the same claim multiple times."""
    print("=" * 60)
    print("DUPLICATE PREVENTION")
    print("=" * 60)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Test Activity"
    )
    
    # Try to add the same claim multiple times
    activity.add_claim(MyClaimables.CPU)
    activity.add_claim(MyClaimables.CPU)
    activity.add_claim(MyClaimables.CPU)
    
    print(f"\nAdded CPU claim 3 times")
    print(f"Actual number of claims: {len(activity.claims)}")
    print(f"Claims: {[claim.resource for claim in activity.claims]}")
    
    print("\n✓ Duplicate claims are automatically prevented\n")


def example_quantitative_tracking():
    """For quantitative tracking, use ModeledValues."""
    print("=" * 60)
    print("QUANTITATIVE TRACKING")
    print("=" * 60)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0)
    
    activity = SimpleActivity(
        begin_time=base_time,
        duration=timedelta(hours=1),
        name="Power-Hungry Activity"
    )
    
    # Claim says "this activity uses the CPU"
    activity.add_claim(MyClaimables.CPU)
    
    # Effect says "this activity drains battery at -10 W"
    # This would require ModeledValues to be imported
    # activity.add_effect('battery_power', EffectType.CONSTANT_RATE, 
    #                    EffectTiming.DURING, -10.0)
    
    print("\nFor quantitative resource tracking:")
    print("  ✓ Use Claims for boolean resource allocation")
    print("  ✓ Use ModeledValues.add_effect() for amounts/rates")
    print("\nExample:")
    print("  activity.add_claim(MyClaimables.CPU)  # Boolean: CPU is claimed")
    print("  activity.add_effect('battery_power', EffectType.CONSTANT_RATE,")
    print("                     EffectTiming.DURING, -10.0)  # Rate: -10 W drain")
    print()


if __name__ == "__main__":
    example_basic_claims()
    example_claims_with_metadata()
    example_removing_claims()
    example_duplicate_prevention()
    example_quantitative_tracking()
    
    print("=" * 60)
    print("All claims examples completed!")
    print("=" * 60)
