from pathlib import Path

import yaml


REQUIRED_TOP_LEVEL_FIELDS = {
    "scenario",
    "routes",
    "stations",
    "physical_constants",
    "weights",
    "buses",
}


def load_scenario(path):
    scenario_path = Path(path)
    with scenario_path.open("r", encoding="utf-8") as scenario_file:
        scenario = yaml.safe_load(scenario_file)
    validate_scenario(scenario, scenario_path)
    return scenario


def list_scenario_files(scenarios_dir):
    return sorted(Path(scenarios_dir).glob("scenario_*.yaml"))


def validate_scenario(scenario, scenario_path):
    missing_fields = REQUIRED_TOP_LEVEL_FIELDS - set(scenario)
    if missing_fields:
        raise ValueError(f"{scenario_path.name} is missing fields: {sorted(missing_fields)}")

    if not scenario["routes"]:
        raise ValueError(f"{scenario_path.name} must define at least one route")

    routes_by_id = {route["id"]: route for route in scenario["routes"]}
    for route in scenario["routes"]:
        if len(route["segments_km"]) != len(route["stations"]) - 1:
            raise ValueError(f"{scenario_path.name} route segments must connect every station pair")

        for station_name in route["stations"][1:-1]:
            if station_name not in scenario["stations"]:
                raise ValueError(f"{scenario_path.name} is missing station config for {station_name}")

    for bus in scenario["buses"]:
        if bus["route_id"] not in routes_by_id:
            raise ValueError(f"{bus['id']} references unknown route {bus['route_id']}")
        known_directions = set(routes_by_id[bus["route_id"]]["directions"].values())
        if bus["direction"] not in known_directions:
            raise ValueError(f"{bus['id']} has unknown direction {bus['direction']}")
