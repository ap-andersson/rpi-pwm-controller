
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
| `TEMP_ON_THRESHOLD` | The temperature (°C) at which to turn the fan on. | `60` |
| `TEMP_OFF_THRESHOLD` | The temperature (°C) at which to turn the fan off. | `50` |
| `UPDATE_INTERVAL` | The interval in seconds at which to check the temperature. | `60` |
| `PWM_GPIO` | The GPIO pin connected to the fan's PWM control wire. | `18` |
| `PWM_FREQUENCY` | The PWM frequency in Hz. Most fans work well with a wide range of frequencies. A value of `100` Hz is a safe default. | `100` |
| `PROMETHEUS_ENDPOINT` | The URL of a Prometheus exporter endpoint to fetch a temperature metric from. If set, this is used instead of the CPU temperature. | (none) |
| `PROMETHEUS_METRIC_NAME` | The name of the metric to fetch from the Prometheus endpoint. | (none) |
| `THRESHOLD_ON_DUTY_CYCLE` | The fan speed (0-100) to set when the temperature exceeds `TEMP_ON_THRESHOLD`. | `100` |
| `THRESHOLD_OFF_DUTY_CYCLE` | The fan speed (0-100) to set when the temperature drops below `TEMP_OFF_THRESHOLD`. | `20` |
| `TEMP_FILE` | Thermal zone file used for the CPU temperature. | `/sys/class/thermal/thermal_zone0/temp` |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` |

### Failsafe Configuration

| Variable | Description | Default |
|---|---|---|
| `FAILSAFE_AFTER_FAILURES` | Number of consecutive failed readings before entering failsafe. | `3` |
| `FAILSAFE_CPU_TEMP` | CPU temperature (°C) above which the fan runs at `THRESHOLD_ON_DUTY_CYCLE` while in failsafe. | `70` |

### Heating Configuration

| Variable | Description | Default |
|---|---|---|
| `HEATING_ENABLED` | Enable the heating functionality. | `false` |
| `HEATING_GPIO` | The GPIO pin connected to the heating element's control relay/switch. | `0` |
| `HEATING_ON_THRESHOLD` | The temperature (°C) at which to turn the heating on. | `0` |
| `HEATING_OFF_THRESHOLD` | The temperature (°C) at which to turn the heating off. | `0` |

Note: On my Noctua NF-A6x25 PWM fan if setting low values on duty cycle it wil start/stop. Around duty cycle 6-8 it seems to stop needing to do that, so I use duty cycle 8 as my THRESHOLD_ON_DUTY_CYCLE. I prefer to not stop the fan if I can avoid it, to keep air moving. 

## Failsafe

When a Prometheus endpoint is configured it is the only temperature source —
there is no silent fallback to the CPU sensor. The two measure different things,
and substituting a ~30 °C SoC reading for an ambient one would run the fan and
disable the heating on data that has nothing to do with the box.

Instead, if the temperature source fails `FAILSAFE_AFTER_FAILURES` times in a
row, the controller enters failsafe:

* **Heating is switched off**, unconditionally. A heater left running on stale
  data is the worst outcome.
* **The fan is driven from the CPU temperature alone**: `THRESHOLD_ON_DUTY_CYCLE`
  if the SoC is above `FAILSAFE_CPU_TEMP`, or if the CPU sensor is also
  unreadable; otherwise `THRESHOLD_OFF_DUTY_CYCLE`. In static mode the fan is
  left alone.

As soon as a reading succeeds again, normal control resumes and the hysteresis
is re-evaluated from the real temperature.

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
