# Bus Charging Scheduler

Bus Charging Scheduler is a Python and Streamlit application that schedules electric bus charging stops on the Bengaluru to Kochi route. It reads scenario YAML files, chooses charging stations for each bus, simulates charger queues, and shows the resulting per-bus and per-station timelines.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Change a Weight

Weights are stored in each scenario file under `weights`.

Before:

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
```

After, with operator balancing doubled:

```yaml
weights:
  individual: 1.0
  operator: 2.0
  overall: 1.0
```

No Python change is needed. The scheduler loads these values from the selected YAML file.

## Add a New Rule

Add the rule class in `bus_charging_scheduler/scheduler/rules.py`:

```python
class PriorityBusRule:
    name = "priority"

    def score(self, bus, station, simulation_state):
        return -100 if bus.priority > 0 else 0
```

Register it in `RULE_REGISTRY` in the same file:

```python
RULE_REGISTRY = {
    "individual": IndividualWaitRule,
    "operator": OperatorFleetDelayRule,
    "overall": NetworkTotalDelayRule,
    "priority": PriorityBusRule,
}
```

Enable it in a scenario YAML:

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
  priority: 1.0
```

The engine does not need to change. It loops over the active rules built from `RULE_REGISTRY`.

## Assumptions

All buses start with a full battery.

A full battery gives 240 km of range.

Every charging session fills the bus to full.

Every charging session takes exactly 25 minutes.

All buses travel at 60 km/h.

The route is linear and buses do not backtrack.

Origins and destinations do not have chargers in the simulation. Only A, B, C, and D are charging stations.

If multiple buses are waiting at a station, the charger goes to the bus with the lowest weighted rule score.

The station selection step is greedy. It uses projected station pressure to avoid likely bottlenecks, but it does not solve a global optimization problem.
