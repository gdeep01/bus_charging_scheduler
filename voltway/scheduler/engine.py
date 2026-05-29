from dataclasses import dataclass, field
from heapq import heappop, heappush
from itertools import combinations

from scheduler.rules import build_active_rules
from scheduler.station import ChargingStation


EVENT_PRIORITY = {
    "charging_ends": 0,
    "bus_arrives_station": 1,
    "charging_starts": 2,
    "bus_departs": 3,
}


@dataclass(order=True)
class Event:
    time_minutes: int
    event_priority: int
    sequence: int
    event_type: str = field(compare=False)
    bus_id: str = field(compare=False)
    station_name: str | None = field(default=None, compare=False)


@dataclass
class BusState:
    bus_id: str
    operator: str
    direction: str
    route_id: str
    departure_time: int
    route_stations: list[str]
    segment_distances: list[int]
    battery_range_km: int
    priority: int = 0
    route_index: int = 0
    remaining_range_km: int = 0
    charge_plan: list[str] = field(default_factory=list)
    charge_sessions: list[dict] = field(default_factory=list)
    open_charge: dict | None = None
    final_arrival_time: int | None = None
    accumulated_wait: int = 0

    def __post_init__(self):
        self.remaining_range_km = self.battery_range_km

    @property
    def current_station(self):
        return self.route_stations[self.route_index]

    def has_reached_destination(self):
        return self.route_index == len(self.route_stations) - 1

    def needs_charge_here(self):
        return self.current_station in self.charge_plan

    def next_segment_distance(self):
        return self.segment_distances[self.route_index]


class RuleEngine:
    def __init__(self, weight_config):
        self.rules = build_active_rules(weight_config)

    def choose_next_bus(self, station, simulation_state):
        return station.choose_next_bus(self.rules, simulation_state)


class ChargingScheduler:
    def __init__(self, scenario):
        self.scenario = scenario
        self.constants = scenario["physical_constants"]
        self.routes = {route["id"]: route for route in scenario["routes"]}
        self.internal_station_names = self._internal_station_names()
        self.rule_engine = RuleEngine(scenario["weights"])
        self.event_sequence = 0
        self.events = []
        self.operator_wait_minutes = {}
        self.stations = self._build_stations()
        self.buses = self._build_buses()

    def run(self):
        self._assign_charge_plans_with_lookahead()
        self._schedule_initial_departures()

        while self.events:
            current_time = self.events[0].time_minutes
            current_events = self._pop_events_at(current_time)
            for event in sorted(current_events, key=lambda item: item.event_priority):
                self._process_event(event)
            self._dispatch_waiting_buses(current_time)

        self._validate_range_constraints()
        return self._build_result()

    def _build_stations(self):
        configured_stations = self.scenario["stations"]
        return {
            name: ChargingStation(name, configured_stations[name]["chargers"])
            for name in self.internal_station_names
        }

    def _build_buses(self):
        buses = {}
        for bus_config in self.scenario["buses"]:
            route = self.routes[bus_config["route_id"]]
            route_stations = self._stations_for_direction(route, bus_config["direction"])
            segment_distances = self._segments_for_direction(route, bus_config["direction"])
            buses[bus_config["id"]] = BusState(
                bus_id=bus_config["id"],
                operator=bus_config["operator"],
                direction=bus_config["direction"],
                route_id=bus_config["route_id"],
                departure_time=parse_time_to_minutes(bus_config["departure_time"]),
                route_stations=route_stations,
                segment_distances=segment_distances,
                battery_range_km=self.constants["battery_range_km"],
                priority=bus_config.get("priority", 0),
            )
        return buses

    def _internal_station_names(self):
        station_names = []
        for route in self.routes.values():
            for station_name in route["stations"][1:-1]:
                if station_name not in station_names:
                    station_names.append(station_name)
        return station_names

    def _stations_for_direction(self, route, direction):
        if direction == route["directions"]["forward"]:
            return list(route["stations"])
        if direction == route["directions"]["reverse"]:
            return list(reversed(route["stations"]))
        raise ValueError(f"Unknown direction: {direction}")

    def _segments_for_direction(self, route, direction):
        if direction == route["directions"]["forward"]:
            return list(route["segments_km"])
        if direction == route["directions"]["reverse"]:
            return list(reversed(route["segments_km"]))
        raise ValueError(f"Unknown direction: {direction}")

    def _assign_charge_plans_with_lookahead(self):
        projected_sessions = {station: [] for station in self.internal_station_names}
        projected_operator_sessions = {station: [] for station in self.internal_station_names}
        for bus in sorted(self.buses.values(), key=lambda item: (item.departure_time, item.bus_id)):
            candidate_plans = self._valid_charge_plans_for_bus(bus)
            ranked_plans = [
                (self._lookahead_plan_cost(bus, plan, projected_sessions, projected_operator_sessions), plan)
                for plan in candidate_plans
            ]
            ranked_plans.sort(key=lambda entry: (entry[0], len(entry[1]), entry[1]))
            bus.charge_plan = list(ranked_plans[0][1])
            self._reserve_projected_sessions(bus, bus.charge_plan, projected_sessions, projected_operator_sessions)

    def _valid_charge_plans_for_bus(self, bus):
        valid_plans = []
        internal_stations = bus.route_stations[1:-1]
        for plan_size in range(2, len(internal_stations) + 1):
            for plan in combinations(internal_stations, plan_size):
                if self._plan_respects_battery_range(bus, plan):
                    valid_plans.append(plan)
        if not valid_plans:
            raise ValueError(f"No valid charging plan found for {bus.bus_id}")
        return valid_plans

    def _plan_respects_battery_range(self, bus, plan):
        distance_since_charge = 0
        planned_charges = set(plan)
        for station_index, distance in enumerate(bus.segment_distances):
            distance_since_charge += distance
            if distance_since_charge > bus.battery_range_km:
                return False
            next_station = bus.route_stations[station_index + 1]
            if next_station in planned_charges:
                distance_since_charge = 0
        return True

    def _lookahead_plan_cost(self, bus, plan, projected_sessions, projected_operator_sessions):
        projected_arrivals = self._project_station_arrivals(bus)
        cost = 0
        operator_weight = self.scenario["weights"].get("operator", 0)
        for station_name in plan:
            arrival_time = projected_arrivals[station_name]
            station_capacity = self.stations[station_name].charger_count
            overlapping_sessions = count_overlapping_sessions(
                projected_sessions[station_name],
                arrival_time,
                self.constants["charging_time_minutes"],
            )
            queued_sessions = max(0, overlapping_sessions - station_capacity + 1)
            cost += queued_sessions * self.constants["charging_time_minutes"]
            cost += self._nearby_session_pressure(projected_sessions[station_name], arrival_time)
            cost += (
                operator_weight
                * self.constants["charging_time_minutes"]
                * 10
                * self._same_operator_pressure(projected_operator_sessions[station_name], bus.operator, arrival_time)
            )
        cost += (len(plan) - 2) * self.constants["charging_time_minutes"]
        return cost

    def _nearby_session_pressure(self, projected_sessions, arrival_time):
        return sum(
            max(0, 90 - abs(arrival_time - start_time)) / 90
            for start_time, end_time in projected_sessions
        )

    def _same_operator_pressure(self, projected_sessions, operator, arrival_time):
        return sum(
            max(0, 90 - abs(arrival_time - start_time)) / 90
            for start_time, end_time, session_operator in projected_sessions
            if session_operator == operator
        )

    def _reserve_projected_sessions(self, bus, plan, projected_sessions, projected_operator_sessions):
        projected_arrivals = self._project_station_arrivals(bus)
        for station_name in plan:
            arrival_time = projected_arrivals[station_name]
            station_sessions = projected_sessions[station_name]
            charger_count = self.stations[station_name].charger_count
            projected_start = earliest_projected_start(
                station_sessions,
                arrival_time,
                self.constants["charging_time_minutes"],
                charger_count,
            )
            station_sessions.append(
                (projected_start, projected_start + self.constants["charging_time_minutes"])
            )
            projected_operator_sessions[station_name].append(
                (projected_start, projected_start + self.constants["charging_time_minutes"], bus.operator)
            )

    def _project_station_arrivals(self, bus):
        arrivals = {}
        elapsed = bus.departure_time
        for index, distance in enumerate(bus.segment_distances):
            elapsed += travel_minutes(distance, self.constants["speed_kmph"])
            arrivals[bus.route_stations[index + 1]] = elapsed
        return arrivals

    def _schedule_initial_departures(self):
        for bus in self.buses.values():
            self._push_event(bus.departure_time, "bus_departs", bus.bus_id, bus.current_station)

    def _push_event(self, time_minutes, event_type, bus_id, station_name=None):
        self.event_sequence += 1
        heappush(
            self.events,
            Event(
                time_minutes=time_minutes,
                event_priority=EVENT_PRIORITY[event_type],
                sequence=self.event_sequence,
                event_type=event_type,
                bus_id=bus_id,
                station_name=station_name,
            ),
        )

    def _pop_events_at(self, current_time):
        events = []
        while self.events and self.events[0].time_minutes == current_time:
            events.append(heappop(self.events))
        return events

    def _process_event(self, event):
        bus = self.buses[event.bus_id]
        if event.event_type == "bus_departs":
            self._handle_bus_departure(bus, event.time_minutes)
        elif event.event_type == "bus_arrives_station":
            self._handle_bus_arrival(bus, event.time_minutes)
        elif event.event_type == "charging_starts":
            self._handle_charging_start(bus, event.time_minutes)
        elif event.event_type == "charging_ends":
            self._handle_charging_end(bus, event.time_minutes)

    def _handle_bus_departure(self, bus, event_time):
        if bus.has_reached_destination():
            return
        distance = bus.next_segment_distance()
        if distance > bus.remaining_range_km:
            raise ValueError(f"{bus.bus_id} cannot travel {distance} km from {bus.current_station}")
        bus.remaining_range_km -= distance
        bus.route_index += 1
        arrival_time = event_time + travel_minutes(distance, self.constants["speed_kmph"])
        self._push_event(arrival_time, "bus_arrives_station", bus.bus_id, bus.current_station)

    def _handle_bus_arrival(self, bus, event_time):
        if bus.has_reached_destination():
            bus.final_arrival_time = event_time
            return
        if bus.needs_charge_here():
            bus.open_charge = {
                "station": bus.current_station,
                "arrived_at": event_time,
                "wait_minutes": 0,
                "charge_start": None,
                "charge_end": None,
            }
            self.stations[bus.current_station].enqueue(bus)
        else:
            self._push_event(event_time, "bus_departs", bus.bus_id, bus.current_station)

    def _handle_charging_start(self, bus, event_time):
        bus.open_charge["charge_start"] = event_time
        bus.open_charge["wait_minutes"] = event_time - bus.open_charge["arrived_at"]
        bus.accumulated_wait += bus.open_charge["wait_minutes"]
        self.operator_wait_minutes[bus.operator] = (
            self.operator_wait_minutes.get(bus.operator, 0) + bus.open_charge["wait_minutes"]
        )
        charge_end = event_time + self.constants["charging_time_minutes"]
        self._push_event(charge_end, "charging_ends", bus.bus_id, bus.current_station)

    def _handle_charging_end(self, bus, event_time):
        station = self.stations[bus.current_station]
        bus.open_charge["charge_end"] = event_time
        bus.charge_sessions.append(bus.open_charge)
        station.completed_sessions.append(bus.open_charge | {
            "bus_id": bus.bus_id,
            "operator": bus.operator,
        })
        bus.open_charge = None
        bus.remaining_range_km = bus.battery_range_km
        station.release_charger()
        self._push_event(event_time, "bus_departs", bus.bus_id, bus.current_station)

    def _dispatch_waiting_buses(self, current_time):
        for station in self.stations.values():
            while station.has_open_charger() and station.waiting_buses:
                simulation_state = {
                    "current_time": current_time,
                    "charging_time_minutes": self.constants["charging_time_minutes"],
                    "operator_wait_minutes": self.operator_wait_minutes,
                    "operator_backlog_counts": self._operator_backlog_counts(),
                    "buses": self.buses,
                    "stations": self.stations,
                }
                next_bus = self.rule_engine.choose_next_bus(station, simulation_state)
                station.reserve_charger()
                self._push_event(current_time, "charging_starts", next_bus.bus_id, station.name)

    def _operator_backlog_counts(self):
        backlog_counts = {}
        for bus in self.buses.values():
            if bus.open_charge is None:
                continue
            backlog_counts[bus.operator] = backlog_counts.get(bus.operator, 0) + 1
        return backlog_counts

    def _validate_range_constraints(self):
        for bus in self.buses.values():
            if not self._plan_respects_battery_range(bus, bus.charge_plan):
                raise ValueError(f"{bus.bus_id} exceeds battery range in final schedule")
            if len(bus.charge_sessions) < 2:
                raise ValueError(f"{bus.bus_id} charged fewer than two times")
            if bus.final_arrival_time is None:
                raise ValueError(f"{bus.bus_id} never reached its destination")

    def _build_result(self):
        return {
            "buses": [self._bus_output(bus) for bus in sorted(self.buses.values(), key=lambda item: item.bus_id)],
            "stations": {
                name: [self._station_session_output(index, session) for index, session in enumerate(station.completed_sessions, start=1)]
                for name, station in self.stations.items()
            },
        }

    def _bus_output(self, bus):
        return {
            "Bus ID": bus.bus_id,
            "Operator": bus.operator,
            "Direction": bus.direction,
            "Stations charged at": " -> ".join(session["station"] for session in bus.charge_sessions),
            "Arrival time at each station": " | ".join(
                f"{session['station']}: {format_minutes(session['arrived_at'])}"
                for session in bus.charge_sessions
            ),
            "Wait time at each station": " | ".join(
                f"{session['station']}: {session['wait_minutes']} min"
                for session in bus.charge_sessions
            ),
            "Charge start time": " | ".join(
                f"{session['station']}: {format_minutes(session['charge_start'])}"
                for session in bus.charge_sessions
            ),
            "Charge end time": " | ".join(
                f"{session['station']}: {format_minutes(session['charge_end'])}"
                for session in bus.charge_sessions
            ),
            "Final arrival time at destination": format_minutes(bus.final_arrival_time),
        }

    def _station_session_output(self, order, session):
        return {
            "Order": order,
            "Bus ID": session["bus_id"],
            "Operator": session["operator"],
            "Arrived at": format_minutes(session["arrived_at"]),
            "Waited": f"{session['wait_minutes']} min",
            "Charge start": format_minutes(session["charge_start"]),
            "Charge end": format_minutes(session["charge_end"]),
        }


def travel_minutes(distance_km, speed_kmph):
    return round(distance_km / speed_kmph * 60)


def parse_time_to_minutes(time_text):
    hours, minutes = [int(part) for part in time_text.split(":")]
    return hours * 60 + minutes


def format_minutes(total_minutes):
    hours = (total_minutes // 60) % 24
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


def count_overlapping_sessions(sessions, arrival_time, charging_time):
    window_end = arrival_time + charging_time
    return sum(start < window_end and end > arrival_time for start, end in sessions)


def earliest_projected_start(sessions, arrival_time, charging_time, charger_count):
    candidate_start = arrival_time
    while True:
        overlap_count = count_overlapping_sessions(sessions, candidate_start, charging_time)
        if overlap_count < charger_count:
            return candidate_start
        candidate_start = min(end for start, end in sessions if start < candidate_start + charging_time and end > candidate_start)
