# Scheduling Simulator Analysis & Monitoring Guide

This guide provides instructions on how to run, monitor, and analyze the Docker-containerized OS Scheduling Simulator using standard Linux tools.

## 1. Building and Running the Simulator

### A. Building the Docker Image
Before running the containerized versions, you must build the Docker image from the provided `Dockerfile`. Run the following command in the project root:
```bash
docker build -t scheduler-sim .
```

### B. Running the Docker CLI Simulator
Because running graphical interfaces (like Tkinter) out of a Docker container requires complex X11 display forwarding, the Docker image is specifically designed to run the **headless CLI version** of the simulator.

**Basic Unconstrained Run:**
```bash
docker run --name os-sim-basic --rm scheduler-sim --cli
```

**Resource-Constrained Run (1 CPU, 512MB RAM):**
```bash
docker run --name os-sim-constrained --cpus="1.0" --memory="512m" --rm scheduler-sim --cli
```
*(Note: We've also provided a `run_simulator.ps1` script for Windows users, which automatically executes the build and run commands for you.)*

### C. Running the Graphical Simulator (Native)
If you want to use the full visual dashboard with the themes, Gantt charts, and memory maps, you should run the simulator natively using Python on your host machine:
```bash
python scheduling_simulator.py
```

---

## 2. Linux Monitoring Tools
While the containers are running (they remain alive after the simulation finishes so you can inspect them), you can use the following commands on your host Linux system or WSL2.

### A. `docker stats`
This is the most straightforward way to see the effects of resource constraints.
```bash
docker stats
```
**What to look for:**
- Compare `os-sim-basic` vs `os-sim-constrained`.
- The `MEM USAGE / LIMIT` column for the constrained container will show a hard limit of `512MiB`.
- The `CPU %` will be capped around `100.00%` (1 core) for the constrained container, whereas the unconstrained one may spike higher if the host has multiple cores.

### B. `top` and `htop`
You can run `top` or `htop` inside the container or on the host.
To run it inside the container:
```bash
docker exec -it os-sim-constrained top
# or
docker exec -it os-sim-constrained htop
```
**What to look for:**
- Observe the memory pressure and CPU utilization.
- Notice how the python process consumes resources. If the simulator is constrained to 1 CPU, you will see it maxing out that single core.

### C. `ps`
To see the processes running inside the container:
```bash
```bash
docker exec -it os-sim-constrained ps aux
```

---

## 3. Data Exporting and Workload Portability

The simulator supports comprehensive data portability, allowing you to run controlled experiments across different algorithms and compare their results cleanly.

### Exporting Final Metrics
Once a simulation finishes in the GUI, you can click **"Export Metrics"** in the Performance Dashboard. This will dump all computed final states, including:
- Average Turnaround Time and Waiting Time.
- CPU and Memory Utilization percentages.
- Exact Wait / Completion bounds for every process execution segment from the Gantt block chart.
You can export this as standard `.csv` or `.json` for further statistical analysis in Excel, Pandas, or Jupyter Notebooks.

### Import/Export JSON Workloads
For reproducible results, use the **Workload Presets & Portability** sidebar card to save your specific process workloads (including priorities, nice values, periods, memory constraints, and I/O status) as `.json` files. You can subsequently import them during separate runs or across different machines to guarantee absolute parity.

---

## 4. Process Isolation & PID Namespaces
Docker uses Linux namespaces to provide isolation. 

### Demonstrating PID Namespaces
When you run `ps aux` inside the container, you will see that the `python scheduling_simulator.py` process has **PID 1**.
```bash
docker exec -it os-sim-constrained ps aux
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root         1  0.5  0.2  45672 23456 ?        Ss   12:00   0:02 python scheduling_simulator.py --cli
```

However, if you run `ps aux | grep python` on your **Linux Host machine**, you will see the exact same process running with a completely different PID (e.g., PID 14592).

**Why?**
The container is running in its own **PID Namespace**. Inside the container, it believes it is the root process (PID 1). The host machine sees it as just another process in the global namespace. This isolation prevents processes inside the container from seeing or interfering with processes outside the container or in other containers.

### Multi-Instance Isolation
If you run two containers:
```bash
docker run -d --name sim1 scheduler-sim --cli
docker run -d --name sim2 scheduler-sim --cli
```
Both will report their internal Python process as **PID 1**. They are completely isolated from each other in both memory and process space, effectively demonstrating OS-level virtualization.
