
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from collections import deque


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="OS Scheduling Simulator",
    page_icon="💻",
    layout="wide"
)


# ============================================================
# SCHEDULING ALGORITHMS
# ============================================================

def calculate_metrics(processes, timeline):
    results = []

    for process in processes:
        pid = process["PID"]
        arrival = process["Arrival"]
        burst = process["Burst"]

        completion = process["Completion"]
        turnaround = completion - arrival
        waiting = turnaround - burst

        results.append({
            "PID": pid,
            "Arrival Time": arrival,
            "Burst Time": burst,
            "Priority": process["Priority"],
            "Completion Time": completion,
            "Turnaround Time": turnaround,
            "Waiting Time": waiting
        })

    df = pd.DataFrame(results)

    total_time = max(
        (segment["End"] for segment in timeline),
        default=0
    )

    busy_time = sum(
        segment["End"] - segment["Start"]
        for segment in timeline
        if segment["PID"] != "Idle"
    )

    cpu_utilization = (
        busy_time / total_time * 100
        if total_time > 0
        else 0
    )

    throughput = (
        len(processes) / total_time
        if total_time > 0
        else 0
    )

    return df, cpu_utilization, throughput


def add_segment(timeline, pid, start, end):
    if end <= start:
        return

    if timeline and timeline[-1]["PID"] == pid:
        if timeline[-1]["End"] == start:
            timeline[-1]["End"] = end
            return

    timeline.append({
        "PID": pid,
        "Start": start,
        "End": end
    })


def fcfs(processes):
    processes = sorted(
        processes,
        key=lambda p: (p["Arrival"], p["PID"])
    )

    timeline = []
    current_time = 0

    for process in processes:
        if current_time < process["Arrival"]:
            add_segment(
                timeline,
                "Idle",
                current_time,
                process["Arrival"]
            )
            current_time = process["Arrival"]

        start = current_time
        current_time += process["Burst"]

        process["Completion"] = current_time

        add_segment(
            timeline,
            process["PID"],
            start,
            current_time
        )

    return processes, timeline


def sjf_non_preemptive(processes):
    remaining = processes.copy()
    timeline = []
    current_time = 0

    while remaining:
        available = [
            p for p in remaining
            if p["Arrival"] <= current_time
        ]

        if not available:
            next_arrival = min(
                p["Arrival"] for p in remaining
            )

            add_segment(
                timeline,
                "Idle",
                current_time,
                next_arrival
            )

            current_time = next_arrival
            continue

        selected = min(
            available,
            key=lambda p: (p["Burst"], p["Arrival"], p["PID"])
        )

        start = current_time
        current_time += selected["Burst"]

        selected["Completion"] = current_time

        add_segment(
            timeline,
            selected["PID"],
            start,
            current_time
        )

        remaining.remove(selected)

    return processes, timeline


def srtf(processes):
    remaining_time = {
        p["PID"]: p["Burst"]
        for p in processes
    }

    timeline = []
    current_time = 0
    completed = 0
    total = len(processes)

    while completed < total:
        available = [
            p for p in processes
            if p["Arrival"] <= current_time
            and remaining_time[p["PID"]] > 0
        ]

        if not available:
            next_arrival = min(
                p["Arrival"]
                for p in processes
                if remaining_time[p["PID"]] > 0
            )

            add_segment(
                timeline,
                "Idle",
                current_time,
                next_arrival
            )

            current_time = next_arrival
            continue

        selected = min(
            available,
            key=lambda p: (
                remaining_time[p["PID"]],
                p["Arrival"],
                p["PID"]
            )
        )

        pid = selected["PID"]

        add_segment(
            timeline,
            pid,
            current_time,
            current_time + 1
        )

        remaining_time[pid] -= 1
        current_time += 1

        if remaining_time[pid] == 0:
            selected["Completion"] = current_time
            completed += 1

    return processes, timeline


def priority_non_preemptive(processes):
    remaining = processes.copy()
    timeline = []
    current_time = 0

    while remaining:
        available = [
            p for p in remaining
            if p["Arrival"] <= current_time
        ]

        if not available:
            next_arrival = min(
                p["Arrival"] for p in remaining
            )

            add_segment(
                timeline,
                "Idle",
                current_time,
                next_arrival
            )

            current_time = next_arrival
            continue

        selected = min(
            available,
            key=lambda p: (
                p["Priority"],
                p["Arrival"],
                p["PID"]
            )
        )

        start = current_time
        current_time += selected["Burst"]

        selected["Completion"] = current_time

        add_segment(
            timeline,
            selected["PID"],
            start,
            current_time
        )

        remaining.remove(selected)

    return processes, timeline


def priority_preemptive(processes):
    remaining_time = {
        p["PID"]: p["Burst"]
        for p in processes
    }

    timeline = []
    current_time = 0
    completed = 0
    total = len(processes)

    while completed < total:
        available = [
            p for p in processes
            if p["Arrival"] <= current_time
            and remaining_time[p["PID"]] > 0
        ]

        if not available:
            next_arrival = min(
                p["Arrival"]
                for p in processes
                if remaining_time[p["PID"]] > 0
            )

            add_segment(
                timeline,
                "Idle",
                current_time,
                next_arrival
            )

            current_time = next_arrival
            continue

        selected = min(
            available,
            key=lambda p: (
                p["Priority"],
                p["Arrival"],
                p["PID"]
            )
        )

        pid = selected["PID"]

        add_segment(
            timeline,
            pid,
            current_time,
            current_time + 1
        )

        remaining_time[pid] -= 1
        current_time += 1

        if remaining_time[pid] == 0:
            selected["Completion"] = current_time
            completed += 1

    return processes, timeline


def round_robin(processes, quantum):
    processes = sorted(
        processes,
        key=lambda p: (p["Arrival"], p["PID"])
    )

    remaining_time = {
        p["PID"]: p["Burst"]
        for p in processes
    }

    timeline = []
    ready_queue = deque()

    current_time = 0
    index = 0
    completed = 0
    total = len(processes)

    while completed < total:

        while (
            index < total
            and processes[index]["Arrival"] <= current_time
        ):
            ready_queue.append(processes[index])
            index += 1

        if not ready_queue:
            if index < total:
                next_arrival = processes[index]["Arrival"]

                add_segment(
                    timeline,
                    "Idle",
                    current_time,
                    next_arrival
                )

                current_time = next_arrival
                continue

        process = ready_queue.popleft()
        pid = process["PID"]

        execution_time = min(
            quantum,
            remaining_time[pid]
        )

        start = current_time
        current_time += execution_time

        remaining_time[pid] -= execution_time

        add_segment(
            timeline,
            pid,
            start,
            current_time
        )

        while (
            index < total
            and processes[index]["Arrival"] <= current_time
        ):
            ready_queue.append(processes[index])
            index += 1

        if remaining_time[pid] > 0:
            ready_queue.append(process)
        else:
            process["Completion"] = current_time
            completed += 1

    return processes, timeline


# ============================================================
# GANTT CHART
# ============================================================

def draw_gantt_chart(timeline):
    if not timeline:
        st.warning("No scheduling timeline available.")
        return

    fig, ax = plt.subplots(figsize=(12, 3))

    for segment in timeline:
        start = segment["Start"]
        end = segment["End"]
        pid = segment["PID"]

        width = end - start

        ax.barh(
            0,
            width,
            left=start,
            height=0.5,
            edgecolor="black"
        )

        ax.text(
            start + width / 2,
            0,
            pid,
            ha="center",
            va="center",
            fontsize=10
        )

        ax.text(
            start,
            -0.4,
            str(start),
            ha="center"
        )

    final_time = timeline[-1]["End"]

    ax.text(
        final_time,
        -0.4,
        str(final_time),
        ha="center"
    )

    ax.set_yticks([])
    ax.set_xlabel("Time")
    ax.set_title("CPU Scheduling Gantt Chart")

    ax.set_xlim(0, final_time)
    ax.grid(axis="x", linestyle="--", alpha=0.4)

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ============================================================
# STREAMLIT INTERFACE
# ============================================================

st.title("💻 OS Scheduling Simulator")

st.markdown(
    """
    Simulate and compare CPU scheduling algorithms.

    Configure processes, select an algorithm, and visualize
    the execution order using a Gantt chart.
    """
)

st.divider()

# Sidebar configuration

st.sidebar.header("Simulation Settings")

algorithm = st.sidebar.selectbox(
    "Scheduling Algorithm",
    [
        "FCFS",
        "SJF (Non-preemptive)",
        "SRTF (Preemptive SJF)",
        "Priority (Non-preemptive)",
        "Priority (Preemptive)",
        "Round Robin"
    ]
)

num_processes = st.sidebar.number_input(
    "Number of Processes",
    min_value=1,
    max_value=20,
    value=4,
    step=1
)

quantum = 2

if algorithm == "Round Robin":
    quantum = st.sidebar.number_input(
        "Time Quantum",
        min_value=1,
        max_value=100,
        value=2
    )

st.subheader("Process Input")

st.caption(
    "For Priority Scheduling, a smaller priority number "
    "represents a higher priority."
)

# Input table

input_data = []

for i in range(int(num_processes)):
    input_data.append({
        "PID": f"P{i + 1}",
        "Arrival": 0,
        "Burst": 5,
        "Priority": 1
    })

input_df = pd.DataFrame(input_data)

edited_df = st.data_editor(
    input_df,
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "PID": st.column_config.TextColumn(
            "Process ID",
            disabled=True
        ),
        "Arrival": st.column_config.NumberColumn(
            "Arrival Time",
            min_value=0,
            step=1
        ),
        "Burst": st.column_config.NumberColumn(
            "Burst Time",
            min_value=1,
            step=1
        ),
        "Priority": st.column_config.NumberColumn(
            "Priority",
            min_value=1,
            step=1
        )
    }
)

st.divider()

# Run simulation

if st.button("▶ Run Simulation", type="primary"):

    processes = edited_df.to_dict("records")

    # Validate inputs

    valid = True

    for process in processes:
        if process["Arrival"] < 0:
            st.error("Arrival time cannot be negative.")
            valid = False

        if process["Burst"] <= 0:
            st.error("Burst time must be greater than zero.")
            valid = False

        if process["Priority"] < 1:
            st.error("Priority must be at least 1.")
            valid = False

    if valid:

        if algorithm == "FCFS":
            scheduled, timeline = fcfs(processes)

        elif algorithm == "SJF (Non-preemptive)":
            scheduled, timeline = sjf_non_preemptive(processes)

        elif algorithm == "SRTF (Preemptive SJF)":
            scheduled, timeline = srtf(processes)

        elif algorithm == "Priority (Non-preemptive)":
            scheduled, timeline = priority_non_preemptive(processes)

        elif algorithm == "Priority (Preemptive)":
            scheduled, timeline = priority_preemptive(processes)

        elif algorithm == "Round Robin":
            scheduled, timeline = round_robin(
                processes,
                int(quantum)
            )

        results_df, cpu_utilization, throughput = (
            calculate_metrics(scheduled, timeline)
        )

        st.session_state["results"] = results_df
        st.session_state["timeline"] = timeline
        st.session_state["cpu_utilization"] = cpu_utilization
        st.session_state["throughput"] = throughput
        st.session_state["algorithm"] = algorithm


# ============================================================
# RESULTS
# ============================================================

if "results" in st.session_state:

    st.subheader("Simulation Results")

    results_df = st.session_state["results"]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Average Waiting Time",
        f"{results_df['Waiting Time'].mean():.2f}"
    )

    col2.metric(
        "Average Turnaround Time",
        f"{results_df['Turnaround Time'].mean():.2f}"
    )

    col3.metric(
        "CPU Utilization",
        f"{st.session_state['cpu_utilization']:.2f}%"
    )

    col4.metric(
        "Throughput",
        f"{st.session_state['throughput']:.3f}"
    )

    st.divider()

    st.subheader("Gantt Chart")

    draw_gantt_chart(
        st.session_state["timeline"]
    )

    st.divider()

    st.subheader("Process Scheduling Table")

    st.dataframe(
        results_df,
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Execution Timeline")

    timeline_df = pd.DataFrame(
        st.session_state["timeline"]
    )

    st.dataframe(
        timeline_df,
        use_container_width=True,
        hide_index=True
    )

    # Download results

    csv = results_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download Results as CSV",
        data=csv,
        file_name="scheduling_results.csv",
        mime="text/csv"
    )

    st.success(
        f"Simulation completed using "
        f"{st.session_state['algorithm']}."
    )
