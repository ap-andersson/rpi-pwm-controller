
# Raspberry Pi PWM Fan Controller

This project provides a simple PWM fan controller for the Raspberry Pi, running in a Docker container.

## Prerequisites

This project uses the modern `gpiod` command-line tools, which are the official way to handle GPIO on recent versions of Raspberry Pi OS. The included Dockerfile handles the installation of all necessary dependencies.

Ensure your user has permissions to access GPIO. When using the provided `docker-compose.yml`, this is handled by running the container in `privileged` mode.

## Configuration

The fan controller is configured using environment variables in the `docker-compose.yml` file.

| Variable | Description | Default |
|---|---|---|
| `STATIC_DUTY_CYCLE` | Set a static fan speed (0-100). If this is set, the temperature-based control is disabled. | (none) |
| `TEMP_ON_THRESHOLD` | The CPU temperature (°C) at which to turn the fan on. | `65` |
| `TEMP_OFF_THRESHOLD` | The CPU temperature (°C) at which to turn the fan off. | `55` |
| `UPDATE_INTERVAL` | The interval in seconds at which to check the CPU temperature. | `5` |
| `PWM_GPIO` | The GPIO pin connected to the fan's PWM control wire. | `18` |
| `PWM_FREQUENCY` | The PWM frequency in Hz. Most fans work well with a wide range of frequencies. A value of `100` Hz is a safe default. | `100` |
| `PROMETHEUS_ENDPOINT` | The URL of a Prometheus exporter endpoint to fetch a temperature metric from. If set, this will be used instead of the CPU temperature. | (none) |
| `PROMETHEUS_METRIC_NAME` | The name of the metric to fetch from the Prometheus endpoint. | (none) |
| `THRESHOLD_ON_DUTY_CYCLE` | The fan speed (0-100) to set when the temperature exceeds `TEMP_ON_THRESHOLD`. | `100` |
| `THRESHOLD_OFF_DUTY_CYCLE` | The fan speed (0-100) to set when the temperature drops below `TEMP_OFF_THRESHOLD`. | `IDLE_DUTY_CYCLE` |

Note: On my Noctua NF-A6x25 PWM fan if setting low values on duty cycle it wil start/stop. Around duty cycle 6-8 it seems to stop needing to do that, so I use duty cycle 8 as my THRESHOLD_ON_DUTY_CYCLE. I prefer to not stop the fan if I can avoid it, to keep air moving. 

## Running the Controller

1.  Connect your PWM fan to the configured GPIO pin.
2.  Clone this repository to your Raspberry Pi.
3.  Navigate to the project directory.
4.  Run the following command:

    ```bash
    docker-compose up -d
    ```

This will build the Docker image and run the controller in the background.

To view the logs, run:

```bash
docker-compose logs -f
```

To stop the controller, run:

```bash
docker-compose down
```
