# Bus Charging Scheduler Architecture

## Scheduling Approach

The scheduler uses cost-based priority scheduling with pluggable rules. Charger allocation is not a pure first-come problem. A bus may deserve priority because it has waited longer than others, because its operator already has several buses delayed, or because serving it now reduces downstream network delay. Those concerns are separate rules, so the scheduler models them separately.

The queue decision uses this shape:

```text
score = (w_individual * individual_wait_penalty)
      + (w_operator * operator_fleet_delay)
      + (w_overall * network_total_delay)
```

Lower score wins the charger. The weights come from the scenario YAML file. The engine does not hardcode the priority policy. It asks each active rule for a score, multiplies that score by the configured weight, and chooses the lowest total score.

FIFO is simple, but it cannot express operator fairness or network-level delay. Round robin can spread access between operators, but it ignores actual arrival times and charger pressure. Greedy nearest-station planning creates avoidable queues at stations that look locally convenient. A weighted rule engine fits better because the operational priorities can change without rewriting the simulation loop.

## Discrete Event Simulation

The simulation is event-driven because the world only changes at specific times: a bus departs, arrives, starts charging, finishes charging, or departs after charging.

The event queue is implemented with `heapq` in `bus_charging_scheduler/scheduler/engine.py`. Events are processed in chronological order. Each station keeps its own waiting queue and charger count.

A fixed time-step simulation would scan the same state repeatedly when nothing changes. A pure optimization model would make it harder to explain the exact timeline in the UI. Discrete event simulation gives a deterministic timeline and maps directly to the operational events reviewers care about.

## Greedy Lookahead Station Selection

Before the event simulation runs, the scheduler chooses charging stations for each bus. It generates every battery-valid charging plan, scores those plans against projected station occupancy, and reserves the selected plan in a projection table.

The relevant code is in:

```text
ChargingScheduler._assign_charge_plans_with_lookahead
ChargingScheduler._lookahead_plan_cost
ChargingScheduler._reserve_projected_sessions
```

The lookahead penalizes plans that arrive near already projected charging sessions. It also includes same-operator pressure, weighted by the scenario's operator weight, so a scenario with many buses from one operator can route some of that operator's buses away from the same bottleneck.

This saves operational cost by avoiding queues before they form. If station B is likely to be contested in 90 minutes, routing a bus through A and C can be cheaper than sending it to B and later resolving a queue.

The method is greedy rather than globally optimal. That is intentional. It is deterministic, easy to inspect, and fast enough for the assignment scenarios while still capturing the main operational tradeoff.

## YAML Data Structure

Each scenario YAML is the input boundary for the scheduler.

`schema_version`: Version of the scenario schema. This gives a place to migrate scenario files later.

`scenario`: Human-readable metadata. It contains the scenario id, name, and description used by the UI.

`routes`: List of route definitions. Each route has an `id`, ordered `stations`, `segments_km`, and direction labels. Buses reference a route through `route_id`, so more than one route can be represented in the same schema.

`stations`: Station configuration keyed by station name. Each station contains `chargers` and `time_of_use_costs`. The scheduler already reads `chargers`.

`physical_constants`: Shared physical settings for the scenario. Current fields are `battery_range_km`, `charging_time_minutes`, and `speed_kmph`.

`weights`: Rule weights keyed by rule name. These values determine how strongly each active rule affects charger allocation and lookahead pressure.

`operators`: Operators present in the scenario. Operator names are not hardcoded in the engine.

`future_constraints`: Structured placeholders for operational constraints that are not enforced yet, such as driver shifts, shared station groups, and dynamic segment distances.

`buses`: Bus inputs. Each bus has `id`, `operator`, `direction`, `departure_time`, `priority`, and `route_id`.

## Future Changes Anticipated

Multiple chargers per station: The field `stations.<station>.chargers` already exists and is used by the station queue. Setting `B: {chargers: 2}` changes capacity through data.

Priority buses: The field `buses[].priority` already exists. A priority rule can read it without changing the scenario schema.

Time-of-use electricity costs: The field `stations.<station>.time_of_use_costs` already exists. A cost rule can read station price windows without changing the scenario schema.

Driver shift constraints: `future_constraints.driver_shifts` can store driver or bus duty windows. A future rule can penalize schedules that exceed those windows without changing the scenario schema.

Multiple routes sharing stations: `routes` is a list and stations are keyed globally by name. A bus already references `route_id`, so additional route definitions can be added through YAML.

More operators: Operators are data, not enums in code. Add a new operator under `operators` and reference it from buses.

Dynamic segment distances: `future_constraints.dynamic_segment_distances` can store time-window distance or duration overrides. The scenario shape can represent this without changing existing fields.

Real-time bus delays: A scenario can update `buses[].departure_time` or add a delay field beside the bus record. Existing bus identity and route references stay stable.

Station maintenance windows: Station availability can be represented under station configuration or future constraints without changing the bus list or route structure.

Shared depots or charger groups: `future_constraints.shared_station_groups` can describe resources shared by multiple named stations without changing route definitions.

## Change a Weight

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
```

Change only the value:

```yaml
weights:
  individual: 1.0
  operator: 2.0
  overall: 1.0
```

The scheduler reads this in `RuleEngine` and applies it to the active rule scores.

## Add a Rule

Add a class in `bus_charging_scheduler/scheduler/rules.py`:

```python
class PriorityBusRule:
    name = "priority"

    def score(self, bus, station, simulation_state):
        return -100 if bus.priority > 0 else 0
```

Register it:

```python
RULE_REGISTRY = {
    "individual": IndividualWaitRule,
    "operator": OperatorFleetDelayRule,
    "overall": NetworkTotalDelayRule,
    "priority": PriorityBusRule,
}
```

Turn it on in YAML:

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
  priority: 1.0
```

No change is needed in `engine.py`.

## Assumptions

All buses start full because the assignment states the initial range is 240 km.

Charging always fills to full because partial charging was not part of the problem statement.

Charging takes exactly 25 minutes because the assignment specifies a fixed session duration.

Travel speed is constant at 60 km/h because traffic, rest breaks, and driver behavior are out of scope.

The route is linear. Buses visit stations in route order and never backtrack.

Only A, B, C, and D are modeled as charging stations. Bengaluru and Kochi are origins or destinations.

A bus may charge more than twice if needed, but the lookahead cost penalizes extra charging stops.

When events happen at the same minute, charging completions are processed before arrivals and dispatch. This avoids an artificial delay when a charger frees exactly as another bus arrives.

Rule scores are costs. Lower total score means the bus is a better candidate for the charger at that moment.
