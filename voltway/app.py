from pathlib import Path

import pandas as pd
import streamlit as st

from scheduler.engine import ChargingScheduler
from utils.loader import list_scenario_files, load_scenario


APP_TITLE = "Bus Charging Scheduler"
WAIT_WARNING_THRESHOLD_MINUTES = 15
WAIT_CRITICAL_THRESHOLD_MINUTES = 30

st.set_page_config(page_title=APP_TITLE, layout="wide")

SCENARIO_DIR = Path(__file__).parent / "scenarios"
OPERATOR_COLORS = {
    "kpn": "background-color: rgba(86, 156, 214, 0.22)",
    "freshbus": "background-color: rgba(78, 201, 176, 0.22)",
    "flixbus": "background-color: rgba(206, 145, 120, 0.24)",
}
SCENARIO_DESCRIPTIONS = {
    "Scenario 1": "Baseline case - buses spaced evenly, minimal contention expected.",
    "Scenario 2": "Tight cluster departure - heavy early contention at inner stations.",
    "Scenario 3": "Uneven traffic - 10 buses one way, only 4 the other.",
    "Scenario 4": "KPN dominates with operator weight doubled - watch how priority shifts.",
    "Scenario 5": "All 20 buses in 72 minutes - maximum possible contention.",
}


@st.cache_data
def load_all_scenarios():
    scenarios = {}
    for scenario_file in list_scenario_files(SCENARIO_DIR):
        scenario = load_scenario(scenario_file)
        label = f"{scenario['scenario']['id']} - {scenario['scenario']['name']}"
        scenarios[label] = scenario
    return scenarios


@st.cache_data
def run_scheduler(scenario):
    return ChargingScheduler(scenario).run()


def style_operator_cells(value):
    return OPERATOR_COLORS.get(str(value).lower(), "")


def style_wait_cells(value):
    wait_minutes = extract_wait_minutes(value)
    if wait_minutes > WAIT_CRITICAL_THRESHOLD_MINUTES:
        return "background-color: rgba(248, 81, 73, 0.34); color: #ffd7d7"
    if wait_minutes > WAIT_WARNING_THRESHOLD_MINUTES:
        return "background-color: rgba(210, 153, 34, 0.25)"
    return ""


def extract_wait_minutes(value):
    if isinstance(value, str):
        waits = []
        for part in value.replace("|", " ").split():
            if part.isdigit():
                waits.append(int(part))
        return max(waits, default=0)
    return 0


def operator_styled_table(rows):
    table = pd.DataFrame(rows)
    return table.style.map(style_operator_cells, subset=["Operator"])


def bus_timetable_style(rows):
    table = pd.DataFrame(rows)
    return (
        table.style
        .map(style_operator_cells, subset=["Operator"])
        .map(style_wait_cells, subset=["Total wait time"])
    )


def station_table_style(rows):
    table = pd.DataFrame(rows)
    return (
        table.style
        .map(style_operator_cells, subset=["Operator"])
        .map(style_wait_cells, subset=["Waited"])
    )


def bus_detail_style(rows):
    table = pd.DataFrame(rows)
    return table.style.map(style_wait_cells, subset=["Waited"])


def station_summary_style(rows):
    table = pd.DataFrame(rows)
    return table.style.map(style_wait_cells, subset=["Longest wait"])


def total_wait_minutes(result):
    total_wait = 0
    for station_sessions in result["stations"].values():
        for session in station_sessions:
            total_wait += extract_wait_minutes(session["Waited"])
    return total_wait


def worst_wait_minutes(result):
    waits = []
    for station_sessions in result["stations"].values():
        for session in station_sessions:
            waits.append(extract_wait_minutes(session["Waited"]))
    return max(waits, default=0)


def bus_summary_rows(result):
    rows = []
    for bus in result["buses"]:
        total_wait = total_bus_wait_minutes(bus)
        rows.append({
            "Bus ID": bus["Bus ID"],
            "Operator": bus["Operator"],
            "Direction": bus["Direction"],
            "Stations used": bus["Stations charged at"],
            "Total wait time": f"{total_wait} min",
            "Final arrival time": bus["Final arrival time at destination"],
        })
    return rows


def total_bus_wait_minutes(bus):
    return sum(
        extract_wait_minutes(wait_text)
        for wait_text in timeline_values(bus["Wait time at each station"]).values()
    )


def bus_detail_rows(bus):
    stations = split_timeline(bus["Stations charged at"], " -> ")
    arrivals = timeline_values(bus["Arrival time at each station"])
    waits = timeline_values(bus["Wait time at each station"])
    starts = timeline_values(bus["Charge start time"])
    ends = timeline_values(bus["Charge end time"])
    return [
        {
            "Station": station,
            "Arrived at": arrivals.get(station, ""),
            "Waited": waits.get(station, ""),
            "Charge start": starts.get(station, ""),
            "Charge end": ends.get(station, ""),
        }
        for station in stations
    ]


def station_summary_rows(result):
    return [
        {
            "Station": station_name,
            "Total buses served": len(sessions),
            "Longest wait": f"{max([extract_wait_minutes(session['Waited']) for session in sessions], default=0)} min",
        }
        for station_name, sessions in result["stations"].items()
    ]


def split_timeline(value, separator):
    if not value:
        return []
    return [part.strip() for part in value.split(separator)]


def timeline_values(value):
    values = {}
    for part in split_timeline(value, "|"):
        if ":" not in part:
            continue
        station, detail = part.split(":", 1)
        values[station.strip()] = detail.strip()
    return values


st.title(APP_TITLE)

scenarios = load_all_scenarios()
selected_label = st.selectbox("Scenario", list(scenarios.keys()))
selected_scenario = scenarios[selected_label]
st.write(SCENARIO_DESCRIPTIONS[selected_scenario["scenario"]["id"]])

st.header("Scenario Input")
bus_rows = [
    {
        "Bus ID": bus["id"],
        "Operator": bus["operator"],
        "Direction": bus["direction"],
        "Departure time": bus["departure_time"],
    }
    for bus in selected_scenario["buses"]
]
st.dataframe(operator_styled_table(bus_rows), width="stretch", hide_index=True)

result = run_scheduler(selected_scenario)
total_wait = total_wait_minutes(result)
worst_wait = worst_wait_minutes(result)

metric_columns = st.columns(3)
metric_columns[0].metric("Total buses scheduled", len(result["buses"]))
metric_columns[1].metric("Total network wait time", f"{total_wait} min")
metric_columns[2].metric("Longest single wait", f"{worst_wait} min")

st.header("Scheduler Output")
bus_tab, station_tab = st.tabs(["Per-bus timetable", "Per-station view"])

with bus_tab:
    st.dataframe(bus_timetable_style(bus_summary_rows(result)), width="stretch", hide_index=True)
    for bus in result["buses"]:
        with st.expander(f"{bus['Bus ID']} details"):
            st.dataframe(bus_detail_style(bus_detail_rows(bus)), width="stretch", hide_index=True)

with station_tab:
    st.dataframe(station_summary_style(station_summary_rows(result)), width="stretch", hide_index=True)
    for station_name, sessions in result["stations"].items():
        st.subheader(station_name)
        with st.expander("Show full queue"):
            st.dataframe(station_table_style(sessions), width="stretch", hide_index=True)
