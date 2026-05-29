class IndividualWaitRule:
    name = "individual"

    def score(self, bus, station, simulation_state):
        current_time = simulation_state["current_time"]
        arrival_time = bus.open_charge["arrived_at"]
        return -max(0, current_time - arrival_time)


class OperatorFleetDelayRule:
    name = "operator"

    def score(self, bus, station, simulation_state):
        operator_backlog = simulation_state["operator_backlog_counts"].get(bus.operator, 0)
        return operator_backlog * simulation_state["charging_time_minutes"] * 10


class NetworkTotalDelayRule:
    name = "overall"

    def score(self, bus, station, simulation_state):
        current_time = simulation_state["current_time"]
        charging_time = simulation_state["charging_time_minutes"]
        remaining_buses = [
            waiting_bus
            for waiting_bus in station.waiting_buses
            if waiting_bus.bus_id != bus.bus_id
        ]
        return sum(
            max(0, current_time + charging_time - waiting_bus.open_charge["arrived_at"])
            for waiting_bus in remaining_buses
        )


RULE_REGISTRY = {
    "individual": IndividualWaitRule,
    "operator": OperatorFleetDelayRule,
    "overall": NetworkTotalDelayRule,
}


def build_active_rules(weight_config):
    rules = []
    for rule_name, weight in weight_config.items():
        if weight == 0:
            continue
        rule_class = RULE_REGISTRY[rule_name]
        rules.append((weight, rule_class()))
    return rules
