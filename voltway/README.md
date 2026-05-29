# Bus Charging Scheduler

Bus Charging Scheduler is a Python + Streamlit app for electric bus charging stops on the Bengaluru to Kochi route. It reads scenario YAML files, chooses charge stops with bottleneck-aware lookahead, and resolves charger queues through a pluggable cost-based rule engine.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Run the commands from the `voltway/` directory.

## Change a Weight

Weights live in each scenario YAML under the `weights` field.

Before:

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
```

After, to make operator-level fleet delay twice as important:

```yaml
weights:
  individual: 1.0
  operator: 2.0
  overall: 1.0
```

No Python code changes are needed. The engine reads these values when the scenario is loaded.

## Add a New Rule

Add a rule class to `scheduler/rules.py`. The only contract is a `score(bus, station, simulation_state) -> float` method. Lower total score wins the charger.

```python
class PriorityBusRule:
    name = "priority"

    def score(self, bus, station, simulation_state):
        return -100 if bus.priority > 0 else 0
```

Register it in `RULE_REGISTRY`:

```python
RULE_REGISTRY = {
    "individual": IndividualWaitRule,
    "operator": OperatorFleetDelayRule,
    "overall": NetworkTotalDelayRule,
    "priority": PriorityBusRule,
}
```

Then enable it from YAML:

```yaml
weights:
  individual: 1.0
  operator: 1.0
  overall: 1.0
  priority: 1.0
```

`engine.py` does not change. It loops over whatever registered rules are active in the scenario weights.
