
# Raspberry Pi PWM Fan Controller

This project provides a simple PWM fan controller for the Raspberry Pi, running in a Docker container.

Gemini was used heavily to develop this and is created specifically for Raspberry PI 5. Any other version of the RPI may need changes for this to work. 

The purpose of the prometheus endpoint is that I already have a script that publishes the ambient temperature in a box outside, where the PI is located. And this is a fan that sucks air into the box to regulate the ambient temperature. Thus I did not want to use the CPU temperature in this case.

## Prerequisites

This project uses the `lgpio` library to handle GPIO pins on Raspberry Pi 5. The included Dockerfile handles the installation of all necessary dependencies.

Ensure your user has permissions to access GPIO. When using the provided `docker-compose.yml`, this is handled by running the container in `privileged` mode.

## Configuration

The fan controller is configured using environment variables in the `docker-compose.yml` file.

| Variable | Description | Default |
|---|---|---|
| `STATIC_DUTY_CYCLE` | Set a static fan speed (0-100). If this is set, the temperature-based control is disabled. | (none) |
| `TEMP_ON_THRESHOLD` | The CPU temperature (°C) at which to turn the fan on. | `65` |
| `TEMP_OFF_THRESHOLD` | The CPU temperature (°C) at which to turn the fan off. | `55` |
| `UPDATE_INTERVAL` | The interval in seconds at which to check the CPU temperature. | `60` |
| `PWM_GPIO` | The GPIO pin connected to the fan's PWM control wire. | `18` |
| `PWM_FREQUENCY` | The PWM frequency in Hz. Most fans work well with a wide range of frequencies. A value of `100` Hz is a safe default. | `100` |
| `PROMETHEUS_ENDPOINT` | The URL of a Prometheus exporter endpoint to fetch a temperature metric from. If set, this will be used instead of the CPU temperature. | (none) |
| `PROMETHEUS_METRIC_NAME` | The name of the metric to fetch from the Prometheus endpoint. | (none) |
| `THRESHOLD_ON_DUTY_CYCLE` | The fan speed (0-100) to set when the temperature exceeds `TEMP_ON_THRESHOLD`. | `100` |
| `THRESHOLD_OFF_DUTY_CYCLE` | The fan speed (0-100) to set when the temperature drops below `TEMP_OFF_THRESHOLD`. | `20` |

### Heating Configuration

| Variable | Description | Default |
|---|---|---|
| `HEATING_ENABLED` | Enable the heating functionality. | `false` |
| `HEATING_GPIO` | The GPIO pin connected to the heating element's control relay/switch. | `0` |
| `HEATING_ON_THRESHOLD` | The temperature (°C) at which to turn the heating on. | `0` |
| `HEATING_OFF_THRESHOLD` | The temperature (°C) at which to turn the heating off. | `0` |

Note: On my Noctua NF-A6x25 PWM fan if setting low values on duty cycle it wil start/stop. Around duty cycle 6-8 it seems to stop needing to do that, so I use duty cycle 8 as my THRESHOLD_ON_DUTY_CYCLE. I prefer to not stop the fan if I can avoid it, to keep air moving. 

## Running the Controller

1.  Connect your PWM fan to the configured GPIO pin.
2.  Clone this repository to your Raspberry Pi.
3.  Navigate to the project directory.
4.  Run command that will build the Docker image and run the controller in the background.

    ```bash
    docker-compose up -d
    ```


### Other commands

To view the logs, run:

```bash
docker-compose logs -f
```

To stop the controller, run:

```bash
docker-compose down
```
