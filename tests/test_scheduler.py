import copy
import signal
import sys
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "voltway"
sys.path.insert(0, str(APP_ROOT))

from scheduler.engine import ChargingScheduler, parse_time_to_minutes
from utils.loader import load_scenario


SCENARIO_DIR = APP_ROOT / "scenarios"
ROUTE_STATIONS = ["Bengaluru", "A", "B", "C", "D", "Kochi"]
SEGMENT_DISTANCES = [100, 120, 100, 120, 100]


EXPECTED_BUSES = {
    "scenario_1.yaml": [
        ("bus-BK-01", "kpn", "Bengaluru→Kochi", "19:00"),
        ("bus-BK-02", "freshbus", "Bengaluru→Kochi", "19:15"),
        ("bus-BK-03", "flixbus", "Bengaluru→Kochi", "19:30"),
        ("bus-BK-04", "kpn", "Bengaluru→Kochi", "19:45"),
        ("bus-BK-05", "freshbus", "Bengaluru→Kochi", "20:00"),
        ("bus-BK-06", "flixbus", "Bengaluru→Kochi", "20:15"),
        ("bus-BK-07", "kpn", "Bengaluru→Kochi", "20:30"),
        ("bus-BK-08", "freshbus", "Bengaluru→Kochi", "20:45"),
        ("bus-BK-09", "flixbus", "Bengaluru→Kochi", "21:00"),
        ("bus-BK-10", "kpn", "Bengaluru→Kochi", "21:15"),
        ("bus-KB-01", "freshbus", "Kochi→Bengaluru", "19:00"),
        ("bus-KB-02", "flixbus", "Kochi→Bengaluru", "19:15"),
        ("bus-KB-03", "kpn", "Kochi→Bengaluru", "19:30"),
        ("bus-KB-04", "freshbus", "Kochi→Bengaluru", "19:45"),
        ("bus-KB-05", "flixbus", "Kochi→Bengaluru", "20:00"),
        ("bus-KB-06", "kpn", "Kochi→Bengaluru", "20:15"),
        ("bus-KB-07", "freshbus", "Kochi→Bengaluru", "20:30"),
        ("bus-KB-08", "flixbus", "Kochi→Bengaluru", "20:45"),
        ("bus-KB-09", "kpn", "Kochi→Bengaluru", "21:00"),
        ("bus-KB-10", "freshbus", "Kochi→Bengaluru", "21:15"),
    ],
    "scenario_2.yaml": [
        ("bus-BK-01", "kpn", "Bengaluru→Kochi", "19:00"),
        ("bus-BK-02", "freshbus", "Bengaluru→Kochi", "19:08"),
        ("bus-BK-03", "flixbus", "Bengaluru→Kochi", "19:16"),
        ("bus-BK-04", "kpn", "Bengaluru→Kochi", "19:24"),
        ("bus-BK-05", "freshbus", "Bengaluru→Kochi", "19:32"),
        ("bus-BK-06", "flixbus", "Bengaluru→Kochi", "19:40"),
        ("bus-BK-07", "kpn", "Bengaluru→Kochi", "19:48"),
        ("bus-BK-08", "freshbus", "Bengaluru→Kochi", "20:03"),
        ("bus-BK-09", "flixbus", "Bengaluru→Kochi", "20:18"),
        ("bus-BK-10", "kpn", "Bengaluru→Kochi", "20:33"),
        ("bus-KB-01", "freshbus", "Kochi→Bengaluru", "19:00"),
        ("bus-KB-02", "flixbus", "Kochi→Bengaluru", "19:08"),
        ("bus-KB-03", "kpn", "Kochi→Bengaluru", "19:16"),
        ("bus-KB-04", "freshbus", "Kochi→Bengaluru", "19:24"),
        ("bus-KB-05", "flixbus", "Kochi→Bengaluru", "19:32"),
        ("bus-KB-06", "kpn", "Kochi→Bengaluru", "19:40"),
        ("bus-KB-07", "freshbus", "Kochi→Bengaluru", "19:48"),
        ("bus-KB-08", "flixbus", "Kochi→Bengaluru", "20:03"),
        ("bus-KB-09", "kpn", "Kochi→Bengaluru", "20:18"),
        ("bus-KB-10", "freshbus", "Kochi→Bengaluru", "20:33"),
    ],
    "scenario_3.yaml": [
        ("bus-BK-01", "kpn", "Bengaluru→Kochi", "19:00"),
        ("bus-BK-02", "freshbus", "Bengaluru→Kochi", "19:15"),
        ("bus-BK-03", "flixbus", "Bengaluru→Kochi", "19:30"),
        ("bus-BK-04", "kpn", "Bengaluru→Kochi", "19:45"),
        ("bus-BK-05", "freshbus", "Bengaluru→Kochi", "20:00"),
        ("bus-BK-06", "flixbus", "Bengaluru→Kochi", "20:15"),
        ("bus-BK-07", "kpn", "Bengaluru→Kochi", "20:30"),
        ("bus-BK-08", "freshbus", "Bengaluru→Kochi", "20:45"),
        ("bus-BK-09", "flixbus", "Bengaluru→Kochi", "21:00"),
        ("bus-BK-10", "kpn", "Bengaluru→Kochi", "21:15"),
        ("bus-KB-01", "freshbus", "Kochi→Bengaluru", "19:00"),
        ("bus-KB-02", "flixbus", "Kochi→Bengaluru", "19:35"),
        ("bus-KB-03", "kpn", "Kochi→Bengaluru", "20:10"),
        ("bus-KB-04", "freshbus", "Kochi→Bengaluru", "20:45"),
    ],
    "scenario_4.yaml": [
        ("bus-BK-01", "kpn", "Bengaluru→Kochi", "19:00"),
        ("bus-BK-02", "kpn", "Bengaluru→Kochi", "19:15"),
        ("bus-BK-03", "kpn", "Bengaluru→Kochi", "19:30"),
        ("bus-BK-04", "kpn", "Bengaluru→Kochi", "19:45"),
        ("bus-BK-05", "kpn", "Bengaluru→Kochi", "20:00"),
        ("bus-BK-06", "kpn", "Bengaluru→Kochi", "20:15"),
        ("bus-BK-07", "kpn", "Bengaluru→Kochi", "20:30"),
        ("bus-BK-08", "kpn", "Bengaluru→Kochi", "20:45"),
        ("bus-BK-09", "freshbus", "Bengaluru→Kochi", "21:00"),
        ("bus-BK-10", "flixbus", "Bengaluru→Kochi", "21:15"),
        ("bus-KB-01", "freshbus", "Kochi→Bengaluru", "19:00"),
        ("bus-KB-02", "flixbus", "Kochi→Bengaluru", "19:15"),
        ("bus-KB-03", "kpn", "Kochi→Bengaluru", "19:30"),
        ("bus-KB-04", "freshbus", "Kochi→Bengaluru", "19:45"),
        ("bus-KB-05", "flixbus", "Kochi→Bengaluru", "20:00"),
        ("bus-KB-06", "kpn", "Kochi→Bengaluru", "20:15"),
        ("bus-KB-07", "freshbus", "Kochi→Bengaluru", "20:30"),
        ("bus-KB-08", "flixbus", "Kochi→Bengaluru", "20:45"),
        ("bus-KB-09", "kpn", "Kochi→Bengaluru", "21:00"),
        ("bus-KB-10", "freshbus", "Kochi→Bengaluru", "21:15"),
    ],
    "scenario_5.yaml": [
        ("bus-BK-01", "kpn", "Bengaluru→Kochi", "19:00"),
        ("bus-BK-02", "freshbus", "Bengaluru→Kochi", "19:08"),
        ("bus-BK-03", "flixbus", "Bengaluru→Kochi", "19:16"),
        ("bus-BK-04", "kpn", "Bengaluru→Kochi", "19:24"),
        ("bus-BK-05", "freshbus", "Bengaluru→Kochi", "19:32"),
        ("bus-BK-06", "flixbus", "Bengaluru→Kochi", "19:40"),
        ("bus-BK-07", "kpn", "Bengaluru→Kochi", "19:48"),
        ("bus-BK-08", "freshbus", "Bengaluru→Kochi", "19:56"),
        ("bus-BK-09", "flixbus", "Bengaluru→Kochi", "20:04"),
        ("bus-BK-10", "kpn", "Bengaluru→Kochi", "20:12"),
        ("bus-KB-01", "freshbus", "Kochi→Bengaluru", "19:00"),
        ("bus-KB-02", "flixbus", "Kochi→Bengaluru", "19:08"),
        ("bus-KB-03", "kpn", "Kochi→Bengaluru", "19:16"),
        ("bus-KB-04", "freshbus", "Kochi→Bengaluru", "19:24"),
        ("bus-KB-05", "flixbus", "Kochi→Bengaluru", "19:32"),
        ("bus-KB-06", "kpn", "Kochi→Bengaluru", "19:40"),
        ("bus-KB-07", "freshbus", "Kochi→Bengaluru", "19:48"),
        ("bus-KB-08", "flixbus", "Kochi→Bengaluru", "19:56"),
        ("bus-KB-09", "kpn", "Kochi→Bengaluru", "20:04"),
        ("bus-KB-10", "freshbus", "Kochi→Bengaluru", "20:12"),
    ],
}


def scenario_paths():
    return [SCENARIO_DIR / name for name in sorted(EXPECTED_BUSES)]


def load_all_scenarios():
    return [(path.name, load_scenario(path)) for path in scenario_paths()]


def run_scenario(scenario):
    return ChargingScheduler(copy.deepcopy(scenario)).run()


def parse_timeline(value):
    entries = {}
    if not value:
        return entries
    for part in value.split("|"):
        station, detail = part.split(":", 1)
        entries[station.strip()] = detail.strip()
    return entries


def parse_station_list(value):
    if not value:
        return []
    return [station.strip() for station in value.split("->")]


def minutes(value):
    return parse_time_to_minutes(value.strip())


def wait_minutes(value):
    return int(value.replace("min", "").strip())


def elapsed_minutes(start, end):
    duration = minutes(end) - minutes(start)
    if duration < 0:
        duration += 24 * 60
    return duration


def distance_between(stations):
    indices = [ROUTE_STATIONS.index(station) for station in stations]
    start = min(indices)
    end = max(indices)
    return sum(SEGMENT_DISTANCES[start:end])


def bus_lookup(scenario):
    return {bus["id"]: bus for bus in scenario["buses"]}


def total_network_wait(result):
    return sum(
        wait_minutes(session["Waited"])
        for sessions in result["stations"].values()
        for session in sessions
    )


def charge_start_signature(result):
    signature = {}
    for station_name, sessions in result["stations"].items():
        for session in sessions:
            signature[(session["Bus ID"], station_name)] = session["Charge start"]
    return signature


class BusChargingSchedulerTests(unittest.TestCase):
    def test_no_bus_exceeds_range_between_charges(self):
        for scenario_name, scenario in load_all_scenarios():
            result = run_scenario(scenario)
            buses = bus_lookup(scenario)
            for bus in result["buses"]:
                source = "Bengaluru" if buses[bus["Bus ID"]]["direction"] == "Bengaluru→Kochi" else "Kochi"
                destination = "Kochi" if source == "Bengaluru" else "Bengaluru"
                stops = [source] + parse_station_list(bus["Stations charged at"]) + [destination]
                for first_station, second_station in zip(stops, stops[1:]):
                    self.assertLessEqual(
                        distance_between([first_station, second_station]),
                        240,
                        f"{scenario_name} {bus['Bus ID']} exceeded range from {first_station} to {second_station}",
                    )

    def test_every_bus_charges_at_least_twice(self):
        for scenario_name, scenario in load_all_scenarios():
            result = run_scenario(scenario)
            for bus in result["buses"]:
                self.assertGreaterEqual(
                    len(parse_station_list(bus["Stations charged at"])),
                    2,
                    f"{scenario_name} {bus['Bus ID']} charged fewer than twice",
                )

    def test_charging_station_order_matches_route_order(self):
        route_order = {"Bengaluru→Kochi": ["A", "B", "C", "D"], "Kochi→Bengaluru": ["D", "C", "B", "A"]}
        for scenario_name, scenario in load_all_scenarios():
            result = run_scenario(scenario)
            buses = bus_lookup(scenario)
            for bus in result["buses"]:
                stations = parse_station_list(bus["Stations charged at"])
                ordered_stations = sorted(stations, key=route_order[buses[bus["Bus ID"]]["direction"]].index)
                self.assertEqual(stations, ordered_stations, f"{scenario_name} {bus['Bus ID']} backtracked")

    def test_no_two_buses_overlap_at_same_station(self):
        for scenario_name, scenario in load_all_scenarios():
            result = run_scenario(scenario)
            for station_name, sessions in result["stations"].items():
                for first_index, first_session in enumerate(sessions):
                    for second_session in sessions[first_index + 1:]:
                        first_start = minutes(first_session["Charge start"])
                        first_end = minutes(first_session["Charge end"])
                        second_start = minutes(second_session["Charge start"])
                        second_end = minutes(second_session["Charge end"])
                        overlaps = first_start < second_end and second_start < first_end
                        self.assertFalse(overlaps, f"{scenario_name} overlap at {station_name}")

    def test_charging_sessions_are_exactly_25_minutes(self):
        for scenario_name, scenario in load_all_scenarios():
            result = run_scenario(scenario)
            for station_name, sessions in result["stations"].items():
                for session in sessions:
                    self.assertEqual(
                        elapsed_minutes(session["Charge start"], session["Charge end"]),
                        25,
                        f"{scenario_name} {station_name} {session['Bus ID']} charge duration was not 25 minutes",
                    )

    def test_all_five_scenarios_run_without_exception(self):
        for scenario_name, scenario in load_all_scenarios():
            try:
                run_scenario(scenario)
            except Exception as error:
                self.fail(f"{scenario_name} raised {error!r}")

    def test_every_bus_final_arrival_is_after_departure(self):
        for scenario_name, scenario in load_all_scenarios():
            result = run_scenario(scenario)
            buses = bus_lookup(scenario)
            for bus in result["buses"]:
                departure = buses[bus["Bus ID"]]["departure_time"]
                self.assertGreater(
                    elapsed_minutes(departure, bus["Final arrival time at destination"]),
                    0,
                    f"{scenario_name} {bus['Bus ID']} did not arrive after departure",
                )

    def test_wait_time_equals_charge_start_minus_arrival_time(self):
        for scenario_name, scenario in load_all_scenarios():
            result = run_scenario(scenario)
            for bus in result["buses"]:
                arrivals = parse_timeline(bus["Arrival time at each station"])
                waits = parse_timeline(bus["Wait time at each station"])
                starts = parse_timeline(bus["Charge start time"])
                for station_name in parse_station_list(bus["Stations charged at"]):
                    self.assertEqual(
                        wait_minutes(waits[station_name]),
                        elapsed_minutes(arrivals[station_name], starts[station_name]),
                        f"{scenario_name} {bus['Bus ID']} wait mismatch at {station_name}",
                    )

    def test_scenario_four_operator_weight_changes_total_network_wait(self):
        scenario_one = load_scenario(SCENARIO_DIR / "scenario_1.yaml")
        scenario_four = load_scenario(SCENARIO_DIR / "scenario_4.yaml")
        self.assertNotEqual(total_network_wait(run_scenario(scenario_one)), total_network_wait(run_scenario(scenario_four)))

    def test_worst_case_scenario_completes_without_deadlock_or_infinite_loop(self):
        scenario = load_scenario(SCENARIO_DIR / "scenario_5.yaml")
        if hasattr(signal, "SIGALRM"):
            def raise_timeout(signum, frame):
                raise TimeoutError("scenario 5 timed out")

            original_handler = signal.signal(signal.SIGALRM, raise_timeout)
            signal.alarm(10)
            try:
                run_scenario(scenario)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, original_handler)
        else:
            start_time = time.monotonic()
            run_scenario(scenario)
            self.assertLess(time.monotonic() - start_time, 10)

    def test_single_bus_scenario_produces_valid_schedule(self):
        scenario = load_scenario(SCENARIO_DIR / "scenario_1.yaml")
        scenario["buses"] = [scenario["buses"][0]]
        result = run_scenario(scenario)
        self.assertEqual(len(result["buses"]), 1)
        self.assertGreaterEqual(len(parse_station_list(result["buses"][0]["Stations charged at"])), 2)

    def test_changing_only_operator_weight_changes_a_contested_charge_start_time(self):
        baseline = load_scenario(SCENARIO_DIR / "scenario_2.yaml")
        changed = copy.deepcopy(baseline)
        changed["weights"]["operator"] = 0.1
        baseline_signature = charge_start_signature(run_scenario(baseline))
        changed_signature = charge_start_signature(run_scenario(changed))
        self.assertTrue(
            any(baseline_signature[key] != changed_signature[key] for key in baseline_signature.keys() & changed_signature.keys())
        )

    def test_all_five_scenario_yaml_files_exist_and_load(self):
        for path in scenario_paths():
            self.assertTrue(path.exists(), f"{path.name} is missing")
            load_scenario(path)

    def test_each_scenario_matches_assignment_brief_bus_inputs(self):
        for scenario_name, scenario in load_all_scenarios():
            actual = [
                (bus["id"], bus["operator"], bus["direction"], bus["departure_time"])
                for bus in scenario["buses"]
            ]
            self.assertEqual(actual, EXPECTED_BUSES[scenario_name])

    def test_scenario_weights_are_present_and_positive_floats(self):
        for scenario_name, scenario in load_all_scenarios():
            self.assertEqual(set(scenario["weights"]), {"individual", "operator", "overall"})
            for rule_name, weight in scenario["weights"].items():
                self.assertIsInstance(weight, float, f"{scenario_name} {rule_name} weight is not a float")
                self.assertGreater(weight, 0.0, f"{scenario_name} {rule_name} weight is not positive")


if __name__ == "__main__":
    unittest.main(verbosity=2)
