# Bus Charging Scheduler Architecture

## Scheduling Approach

Bus Charging Scheduler uses cost-based priority scheduling with pluggable rules because charger contention is not a single objective problem. A bus may deserve priority because it has waited too long, because its operator is falling behind, or because the whole network benefits from moving it first. Those are different business ideas, so they should be expressed as separate rule classes rather than hardcoded branches.

Every queue decision uses the same formula:

```text
score = (w_individual * individual_wait_penalty)
      + (w_operator * operator_fleet_delay)
      + (w_overall * network_total_delay)
```

The engine does not know what individual, operator, or overall means. It asks active rule objects for scores, multiplies by YAML weights, and gives the charger to the lowest total score. This makes policy tuning a data change and policy expansion a new rule class.

## Why Discrete Event Simulation

This problem is naturally event-driven. Buses depart, arrive, start charging, finish charging, and depart again. A fixed time-step simulation would repeatedly inspect the world when nothing is happening. An optimization-only model would make it harder to show the actual operational timeline reviewers need.

Bus Charging Scheduler uses `heapq` as a priority queue of events:

```text
bus_departs
bus_arrives_station
charging_starts
charging_ends
```

Events are processed in chronological order. Each station owns its waiting queue and charger count. This keeps the simulation deterministic, inspectable, and easy to extend to more buses or more chargers.

## Greedy Lookahead Station Selection

A valid charging plan is not enough. On this route a Bengaluru to Kochi bus can typically use either `A + C` or `B + D`; the reverse direction has symmetric choices. Always choosing the nearest valid stations would push many buses into the same inner stations and create avoidable queues.

Bus Charging Scheduler first generates all battery-valid charging plans for each bus. It then scores each plan against projected station occupancy from earlier planned buses. A plan is penalized when a station is expected to be busy near the bus's projected arrival time, especially within a 90-minute contention window. The chosen plan is then reserved in the projection before planning the next bus.

This is intentionally greedy rather than globally optimal. It is fast, explainable in an interview, and captures the operational win: route buses away from predicted bottlenecks before they become queues. Avoided waiting is cheaper than perfectly resolving a queue after every bus has already arrived.

## Data Structure

Each scenario YAML is the system boundary. A new scenario should describe the world without Python edits.

`schema_version`: Version marker for future migrations.

`scenario`: Human-facing metadata.

`routes`: List of route definitions. Buses reference routes by `route_id`, so a scenario can carry multiple routes that share station configs. Each route has:

`id`: Stable identifier referenced by buses.

`stations`: Ordered station names including origin and destination.

`segments_km`: Distances between adjacent stations.

`directions`: Human-readable direction labels used by buses.

`stations`: Station configuration keyed by station name. Each station has:

`chargers`: Number of chargers. The engine already reads this, so `B: {chargers: 2}` works without code changes.

`time_of_use_costs`: Reserved schedule for electricity price windows.

`physical_constants`: Battery range, charge duration, and speed.

`weights`: Rule weights by registered rule name.

`operators`: Operator identifiers.

`future_constraints`: Structured placeholders for driver shifts, shared station groups, and dynamic segment distances.

`buses`: Bus inputs. Each bus has `id`, `operator`, `direction`, `departure_time`, `priority`, and `route_id`.

## Anticipated Future Changes

Multiple chargers per station: Already handled through `stations.<name>.chargers`; station dispatch loops until all chargers are occupied.

Priority buses: Already represented by `buses[].priority`; add a `PriorityBusRule` and a YAML weight.

Electricity cost by time of day: Already represented by `stations.<name>.time_of_use_costs`; add an electricity-cost rule that reads the station field.

Driver shift constraints: Already has `future_constraints.driver_shifts`; add a rule that penalizes plans pushing a bus outside its shift window.

Multiple routes sharing stations: `routes` is a list and stations are keyed globally by name. Buses carry `route_id`, and the engine builds each bus's station order from that route.

More operators: Add entries under `operators` and reference them from buses. The current operator rule uses operator strings dynamically.

Dynamic segment distances: `future_constraints.dynamic_segment_distances` can carry time-window overrides for segment lengths; a future travel-time function can read those overrides.

Real-time bus delays: Add an updated departure time or a live delay field to a bus record. The simulation already treats departure time as data.

## Change a Weight

```yaml
weights:
  individual: 1.0
  operator: 2.0
  overall: 1.0
```

The scheduler loads this into `RuleEngine`, which builds active rules from `RULE_REGISTRY` and applies weights at decision time.

## Add a Rule

```python
class PriorityBusRule:
    name = "priority"

    def score(self, bus, station, simulation_state):
        return -100 if bus.priority > 0 else 0


RULE_REGISTRY = {
    "individual": IndividualWaitRule,
    "operator": OperatorFleetDelayRule,
    "overall": NetworkTotalDelayRule,
    "priority": PriorityBusRule,
}
```

Enable it in a scenario:

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
  priority: 1.0
```

No engine changes are needed because the engine loops over active registered rules.

## Assumptions

All buses start full, and every charge fills to full.

Travel speed is constant at 60 km/h, so 100 km takes 100 minutes.

Station service time is exactly 25 minutes and includes plug-in and release time.

The scheduler may choose more than two charges, but the lookahead plan cost penalizes extra charges so it only does so when useful.

When several events happen at the same minute, charging completions are processed before arrivals, then queue dispatch runs. This lets a bus arriving exactly when a charger frees use that charger without an artificial one-minute delay.

Rule scores may be negative when a rule is expressing urgency. The combined score is still a cost: lower means serving that bus now leaves less unresolved operational pain.
