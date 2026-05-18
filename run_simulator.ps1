# Build the Docker image
Write-Host "Building the Docker image..."
docker build -t scheduler-sim .

# Run default CLI simulation
Write-Host "Running basic simulation..."
docker run --name os-sim-basic --rm scheduler-sim --cli

# Run with CPU and Memory Constraints
Write-Host "Running constrained simulation (1 CPU core, 512MB RAM)..."
docker run --name os-sim-constrained --cpus="1.0" --memory="512m" --rm scheduler-sim --cli
