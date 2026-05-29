class ChargingStation:
    def __init__(self, name, charger_count):
        self.name = name
        self.charger_count = charger_count
        self.busy_chargers = 0
        self.waiting_buses = []
        self.completed_sessions = []

    def enqueue(self, bus):
        self.waiting_buses.append(bus)

    def has_open_charger(self):
        return self.busy_chargers < self.charger_count

    def reserve_charger(self):
        self.busy_chargers += 1

    def release_charger(self):
        self.busy_chargers -= 1

    def choose_next_bus(self, rules, simulation_state):
        scored_buses = []
        for bus in self.waiting_buses:
            rule_score = sum(
                weight * rule.score(bus, self, simulation_state)
                for weight, rule in rules
            )
            scored_buses.append((rule_score, bus.open_charge["arrived_at"], bus.bus_id, bus))

        scored_buses.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
        chosen_bus = scored_buses[0][3]
        self.waiting_buses.remove(chosen_bus)
        return chosen_bus
