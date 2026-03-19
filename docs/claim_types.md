# Claim Types: EXCLUSIVE vs AVOIDANCE

## Overview

The tts_plan activity system now supports two types of resource claims: **EXCLUSIVE** and **AVOIDANCE**. This allows you to model scenarios where multiple activities need to avoid a resource without conflicting with each other.

## Motivation

Consider this scenario:
- Activity C uses the SHARAD instrument (makes an EXCLUSIVE claim)
- Activities A and B both need to avoid SHARAD (but don't use it themselves)

Previously, the only way to model this was to have A and B both claim SHARAD, but this caused A and B to conflict with each other - which is incorrect since they can both run simultaneously as long as neither overlaps with C.

## ClaimType Enum

```python
from tts_plan.activity import ClaimType

class ClaimType(Enum):
    EXCLUSIVE = auto()  # Conflicts with any other claim (default behavior)
    AVOIDANCE = auto()   # Only conflicts with EXCLUSIVE claims
```

## Conflict Matrix

| Activity 1 | Activity 2 | Result |
|------------|------------|--------|
| EXCLUSIVE  | EXCLUSIVE  | ✗ CONFLICT |
| EXCLUSIVE  | AVOIDANCE  | ✗ CONFLICT |
| AVOIDANCE  | EXCLUSIVE  | ✗ CONFLICT |
| AVOIDANCE  | AVOIDANCE  | ✓ NO CONFLICT |

## Usage

### Basic Example

```python
from tts_plan.activity import Activity, ClaimType

# Activity that USES a resource (traditional EXCLUSIVE claim)
activity_c = SomeActivity(
    begin_time=start_time,
    duration=timedelta(hours=1),
    name="Uses SHARAD"
)
activity_c.add_claim('SHARAD', claim_type=ClaimType.EXCLUSIVE)

# Activities that AVOID a resource (new AVOIDANCE claim)
activity_a = SomeActivity(
    begin_time=start_time + timedelta(minutes=20),
    duration=timedelta(hours=1),
    name="Avoids SHARAD"
)
activity_a.add_claim('SHARAD', claim_type=ClaimType.AVOIDANCE)

activity_b = SomeActivity(
    begin_time=start_time + timedelta(minutes=40),
    duration=timedelta(hours=1),
    name="Also Avoids SHARAD"
)
activity_b.add_claim('SHARAD', claim_type=ClaimType.AVOIDANCE)

# Results:
# - A conflicts with C ✗
# - B conflicts with C ✗
# - A does NOT conflict with B ✓
```

### Default Behavior

For backward compatibility, `ClaimType.EXCLUSIVE` is the default:

```python
# These are equivalent:
activity.add_claim('RESOURCE_X')
activity.add_claim('RESOURCE_X', claim_type=ClaimType.EXCLUSIVE)
```

### Mixed Claims

An activity can have different claim types on different resources:

```python
activity = SomeActivity(...)
activity.add_claim('RESOURCE_X', claim_type=ClaimType.EXCLUSIVE)  # Must have exclusive access
activity.add_claim('RESOURCE_Y', claim_type=ClaimType.AVOIDANCE)  # Must avoid but doesn't use
```

## Implementation Details

### Claim Class

The `Claim` class now includes a `claim_type` attribute:

```python
class Claim:
    def __init__(self, resource: Union[Enum, str], 
                 claim_type: ClaimType = ClaimType.EXCLUSIVE,
                 metadata: Optional[Dict[str, Any]] = None):
        self.resource = resource
        self.claim_type = claim_type
        self.metadata = metadata or {}
```

### Conflict Detection

The conflict detection algorithm in `Activity.get_conflicts_with()` checks claim types:

```python
for self_claim in self_desc.claims:
    for other_claim in other_desc.claims:
        if self_claim.resource != other_claim.resource:
            continue
        
        # Only conflict if at least one claim is EXCLUSIVE
        if (self_claim.claim_type == ClaimType.EXCLUSIVE or 
            other_claim.claim_type == ClaimType.EXCLUSIVE):
            conflicting_resources.add(self_claim.resource)
```

## Use Cases

### 1. Instrument Avoidance
Activities that need to avoid an instrument without using it (e.g., off-nadir observations that conflict with nadir instruments).

### 2. Thermal Constraints
Multiple activities that need to avoid thermal-intensive operations, but don't conflict with each other.

### 3. Keepout Zones
Multiple science observations that must avoid certain spacecraft states or configurations.

### 4. Shared Resources
Resources that can be "monitored" by multiple activities but only "controlled" by one.

## Testing

Comprehensive tests are available in `test_claim_types.py`:
- `test_exclusive_claims_conflict`: Traditional behavior
- `test_exclusive_and_avoidance_conflict`: EXCLUSIVE vs AVOIDANCE
- `test_avoidance_claims_do_not_conflict`: AVOIDANCE vs AVOIDANCE
- `test_three_activity_scenario`: The motivating use case
- `test_default_claim_type_is_exclusive`: Backward compatibility
- `test_mixed_claims_on_same_activity`: Multiple claim types per activity

## Migration Guide

Existing code will continue to work without changes since EXCLUSIVE is the default claim type. To adopt AVOIDANCE claims:

1. Identify activities that avoid resources without using them
2. Change their claims to use `ClaimType.AVOIDANCE`:
   ```python
   # Before:
   activity.add_claim('SHARAD')
   
   # After (if this activity avoids SHARAD but doesn't use it):
   activity.add_claim('SHARAD', claim_type=ClaimType.AVOIDANCE)
   ```

## Future Enhancements

Potential future extensions to the claim type system:
- **SHARED**: Multiple activities can share access (e.g., read-only resources)
- **PRIORITY**: Claims with different priority levels
- **CONDITIONAL**: Claims that depend on activity state or configuration
