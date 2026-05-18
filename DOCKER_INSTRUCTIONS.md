# Docker Instructions for CPU Scheduling Simulator

This guide provides step-by-step instructions for building and running the **SchedulingSimulator** in a Docker container.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Building the Docker Image](#building-the-docker-image)
3. [Running the Simulator](#running-the-simulator)
4. [Container Modes](#container-modes)
5. [Monitoring Containers](#monitoring-containers)
6. [Data Export & Results](#data-export--results)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Docker Desktop** installed and running on your system
- Windows 10/11 Pro, Enterprise, or Education (for Docker Desktop with WSL2)
- At least 2GB of free disk space for the container image
- Python 3.9+ (for the application itself)

### Install Docker Desktop

1. Download from [docker.com](https://www.docker.com/products/docker-desktop)
2. Run the installer and follow the setup wizard
3. Enable WSL2 integration (recommended for Windows)
4. Verify installation:
   ```bash
   docker --version
   docker run hello-world
   ```

---

## Building the Docker Image

The project includes a `Dockerfile` that sets up the complete environment for the SchedulingSimulator.

### Step 1: Navigate to Project Directory

```bash
cd D:\div1osccp
```

### Step 2: Build the Image

```bash
docker build -t scheduler-sim .
```

**What this does:**
- Reads the `Dockerfile` in the current directory
- Installs all dependencies from `requirements.txt`
- Sets up Python environment
- Tags the image as `scheduler-sim`

### Step 3: Verify the Build

```bash
docker images
```

You should see `scheduler-sim` in the list with the image ID and size.

---

## Running the Simulator

The SchedulingSimulator supports multiple run modes through the Docker container.

### Basic CLI Mode (Headless)

Run the simulator without GUI (ideal for automated testing and CI/CD):

```bash
docker run --name os-sim-basic --rm scheduler-sim --cli
```

**Output:** The container will run the simulation and output results to stdout.

### Resource-Constrained Run

Run with limited CPU and memory to test the scheduler's behavior under resource constraints:

```bash
docker run --name os-sim-constrained --cpus="1.0" --memory="512m" --rm scheduler-sim --cli
```

**Parameters:**
- `--cpus="1.0"` — Limit to 1 CPU core
- `--memory="512m"` — Limit to 512MB RAM
- `--name os-sim-constrained` — Container name for reference
- `--rm` — Automatically remove container after exit

### Custom Configuration Run

Run with specific environment variables or configuration:

```bash
docker run --name os-sim-custom -e CONFIG_FILE=config.json --rm scheduler-sim --cli
```

### Interactive Shell (For Debugging)

Enter the container with an interactive shell:

```bash
docker run --name os-sim-debug -it --rm scheduler-sim /bin/bash
```

Inside the container, you can:
- Run the simulator manually: `python scheduling_simulator.py --cli`
- Inspect files: `ls -la`
- Check Python version: `python --version`
- Run tests: `python test_scheduler.py`

---

## Container Modes

The SchedulingSimulator supports multiple execution modes:

### 1. CLI Mode (Headless)
```bash
docker run --rm scheduler-sim --cli
```
- No GUI required
- Ideal for Docker/cloud environments
- Outputs results to console
- Fastest execution

### 2. GUI Mode (Native Only)
```bash
python scheduling_simulator.py
```
- Requires X11 display forwarding (complex with Docker)
- Use native Python execution instead for GUI features
- Recommended: Run natively on your host system

### 3. Batch Processing Mode
```bash
docker run --rm -v D:\div1osccp\results:/app/results scheduler-sim --cli --output-dir results
```
- Saves results to mounted volume
- Ideal for running multiple simulations
- Results persist after container exits

---

## Monitoring Containers

While containers are running, monitor their resource usage and behavior.

### View Running Containers

```bash
docker ps
```

### View All Containers (including stopped)

```bash
docker ps -a
```

### Monitor Real-Time Resource Usage

```bash
docker stats
```

Shows:
- CPU percentage and limit
- Memory usage and limit
- Network I/O
- Block I/O

### View Container Logs

```bash
docker logs container-name
```

Example:
```bash
docker logs os-sim-basic
```

### Execute Commands Inside Running Container

```bash
docker exec -it container-name command
```

Examples:
```bash
# Run top/htop
docker exec -it os-sim-constrained top

# Check processes
docker exec -it os-sim-constrained ps aux

# View file contents
docker exec -it os-sim-constrained cat config.json
```

### Inspect Container Details

```bash
docker inspect container-name
```

Returns detailed JSON output including:
- Resource limits
- Environment variables
- Volumes mounted
- Network settings

---

## Data Export & Results

### Mount Local Directory for Output

Persist simulation results to your host system:

```bash
docker run --name os-sim-export -v D:\div1osccp\results:/app/results --rm scheduler-sim --cli --export results/output.json
```

**Directory Mapping:**
- `D:\div1osccp\results` (Windows host) → `/app/results` (container)
- Files written to `/app/results` inside container appear in `D:\div1osccp\results` on host

### Copy Files from Container After Exit

```bash
# Create container but don't auto-remove
docker run --name os-sim-keep scheduler-sim --cli

# Copy results to host
docker cp os-sim-keep:/app/results/metrics.csv D:\div1osccp\results\

# Clean up
docker rm os-sim-keep
```

### Export Metrics as CSV/JSON

Inside the container or after running:
```bash
# Export simulation metrics
python scheduling_simulator.py --cli --export metrics.json
```

---

## Process Isolation & PID Namespaces

Docker provides OS-level isolation through Linux namespaces.

### View PID Inside Container

```bash
docker exec os-sim-basic ps aux
```

Output shows Python process with **PID 1** inside the container.

### View PID on Host

```bash
# Windows: Use Task Manager or
tasklist | findstr python
```

The same process has a **different PID** on the host, demonstrating namespace isolation.

### Multi-Instance Isolation

Run two separate instances completely isolated:

```bash
docker run -d --name sim1 scheduler-sim --cli
docker run -d --name sim2 scheduler-sim --cli
```

Both have internal PID 1, but are isolated from each other and the host.

---

## Troubleshooting

### Docker Daemon Not Running

**Error:** `Cannot connect to Docker daemon`

**Solution:**
1. Start Docker Desktop from Windows Start menu
2. Wait for the system tray icon to show it's running
3. Retry your docker command

### Port Already in Use

**Error:** `bind: address already in use`

**Solution:**
```bash
# Find container using the port
docker ps

# Stop the container
docker stop container-name

# Or use different port mapping
docker run -p 8001:8000 --rm scheduler-sim
```

### Out of Disk Space

**Error:** `no space left on device`

**Solution:**
```bash
# Clean up unused images, containers, volumes
docker system prune -a

# Or remove specific image
docker rmi scheduler-sim
```

### Container Exits Immediately

**Solution:** Check logs for errors
```bash
docker logs container-name
docker logs --tail 50 container-name  # Last 50 lines
```

### Permission Denied

**Windows:** Run Command Prompt or PowerShell as Administrator

**Linux/Mac:**
```bash
sudo docker run --rm scheduler-sim --cli
# Or add user to docker group
sudo usermod -aG docker $USER
```

### Performance Issues

**Solution:** Increase Docker resource limits
1. Open Docker Desktop settings
2. Go to Resources
3. Increase CPU cores and memory allocation
4. Click Apply & Restart

---

## Common Docker Commands Reference

```bash
# Image Management
docker build -t scheduler-sim .              # Build image
docker images                                 # List images
docker rmi scheduler-sim                     # Remove image

# Container Management
docker run --rm scheduler-sim --cli          # Run container
docker ps                                    # List running containers
docker ps -a                                 # List all containers
docker start container-name                  # Start stopped container
docker stop container-name                   # Stop running container
docker rm container-name                     # Remove container

# Inspection & Debugging
docker logs container-name                   # View logs
docker stats                                 # Real-time resource usage
docker exec -it container-name /bin/bash    # Interactive shell
docker inspect container-name                # Detailed container info

# Cleanup
docker system prune                          # Remove unused resources
docker system prune -a                       # Remove all unused resources
```

---

## Advanced: Docker Compose (Multiple Containers)

Create a `docker-compose.yml` to run multiple simulators with different configurations:

```yaml
version: '3.8'

services:
  sim-basic:
    build: .
    container_name: os-sim-basic
    command: python scheduling_simulator.py --cli
    environment:
      - ALGORITHM=FCFS
    volumes:
      - ./results:/app/results

  sim-constrained:
    build: .
    container_name: os-sim-constrained
    command: python scheduling_simulator.py --cli
    cpus: "1.0"
    mem_limit: 512m
    environment:
      - ALGORITHM=ROUND_ROBIN
    volumes:
      - ./results:/app/results

  sim-adaptive:
    build: .
    container_name: os-sim-adaptive
    command: python scheduling_simulator.py --cli
    cpus: "2.0"
    mem_limit: 1g
    environment:
      - ALGORITHM=CFS
    volumes:
      - ./results:/app/results
```

Run all services:
```bash
docker-compose up
```

Stop all services:
```bash
docker-compose down
```

---

## Performance Metrics

When running the SchedulingSimulator in Docker, monitor these metrics:

| Metric | Command | What to Look For |
|--------|---------|------------------|
| CPU Usage | `docker stats` | Should be limited to `--cpus` value |
| Memory Usage | `docker stats` | Should not exceed `--memory` limit |
| Execution Time | Check logs | Time to complete simulation |
| Page Faults | Simulation output | Virtual memory performance |
| Context Switches | `docker exec htop` | Process scheduling efficiency |

---

## Next Steps

1. **Build the image:** `docker build -t scheduler-sim .`
2. **Run a test:** `docker run --rm scheduler-sim --cli`
3. **Monitor:** `docker stats` (in another terminal)
4. **Export results:** Use `-v` flag to mount volumes
5. **Compare algorithms:** Run with different environment variables
6. **Scale:** Use Docker Compose for multi-instance experiments

For more details on the SchedulingSimulator itself, see [Analysis_Guide.md](Analysis_Guide.md).

---

**Last Updated:** May 2026
**Docker Version:** 4.0+
**Python Version:** 3.9+
