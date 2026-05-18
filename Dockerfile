# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install Tkinter and X11 dependencies (for GUI if needed)
# Also install procps for tools like top, ps
RUN apt-get update && apt-get install -y \
    python3-tk \
    x11-apps \
    procps \
    htop \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Run scheduling_simulator.py when the container launches
# By default, run the CLI version to avoid X11 configuration issues for basic testing
ENTRYPOINT ["python", "scheduling_simulator.py"]
CMD ["--cli"]
