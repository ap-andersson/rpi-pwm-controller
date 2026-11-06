import os
import time
import signal
import logging
import lgpio
import requests

log = logging.getLogger("pwm")

# Configuration
PWM_GPIO = int(os.getenv("PWM_GPIO", 18))
PWM_FREQUENCY = int(os.getenv("PWM_FREQUENCY", 100))
STATIC_DUTY_CYCLE = os.getenv("STATIC_DUTY_CYCLE")
TEMP_ON_THRESHOLD = float(os.getenv("TEMP_ON_THRESHOLD", 60.0))
TEMP_OFF_THRESHOLD = float(os.getenv("TEMP_OFF_THRESHOLD", 50.0))
TEMP_FILE = os.getenv("TEMP_FILE", "/sys/class/thermal/thermal_zone0/temp")
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 60))
PROMETHEUS_ENDPOINT = os.getenv("PROMETHEUS_ENDPOINT")
PROMETHEUS_METRIC_NAME = os.getenv("PROMETHEUS_METRIC_NAME")
THRESHOLD_ON_DUTY_CYCLE = float(os.getenv("THRESHOLD_ON_DUTY_CYCLE", 100.0))
THRESHOLD_OFF_DUTY_CYCLE = float(os.getenv("THRESHOLD_OFF_DUTY_CYCLE", 20.0))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Failsafe: what to do when the temperature source stops answering
FAILSAFE_AFTER_FAILURES = int(os.getenv("FAILSAFE_AFTER_FAILURES", 3))
FAILSAFE_CPU_TEMP = float(os.getenv("FAILSAFE_CPU_TEMP", 70.0))

# Heating specific settings
HEATING_ENABLED = os.getenv("HEATING_ENABLED", "false").lower() == "true"
HEATING_ON_THRESHOLD = float(os.getenv("HEATING_ON_THRESHOLD", 0.0))
HEATING_OFF_THRESHOLD = float(os.getenv("HEATING_OFF_THRESHOLD", 0.0))
HEATING_GPIO = int(os.getenv("HEATING_GPIO", 0))

if not 0 <= THRESHOLD_ON_DUTY_CYCLE <= 100:
    raise ValueError("THRESHOLD_ON_DUTY_CYCLE must be between 0 and 100")

if not 0 <= THRESHOLD_OFF_DUTY_CYCLE <= 100:
    raise ValueError("THRESHOLD_OFF_DUTY_CYCLE must be between 0 and 100")

# Global state
h = None  # lgpio handle
high_speed_mode = False
current_duty_cycle = 0.0
heating_on = False
failsafe_active = False
consecutive_failures = 0
claimed_pins = []


def get_prometheus_temperature():
    """Fetches temperature from a Prometheus endpoint."""
    try:
        response = requests.get(PROMETHEUS_ENDPOINT, timeout=5)
        response.raise_for_status()
        for line in response.text.splitlines():
            if line.startswith(PROMETHEUS_METRIC_NAME):
                parts = line.split()
                if len(parts) >= 2:
                    return float(parts[1])
        log.warning("Metric '%s' not found in Prometheus endpoint.", PROMETHEUS_METRIC_NAME)
        return None
    except (requests.RequestException, ValueError) as e:
        log.warning("Error getting temperature from Prometheus: %s", e)
        return None


def get_cpu_temperature():
    """Reads the CPU temperature from the thermal zone file."""
    try:
        with open(TEMP_FILE, "r") as f:
            temp_str = f.read()
        return float(temp_str) / 1000.0
    except (IOError, ValueError) as e:
        log.warning("Error reading CPU temperature: %s", e)
        return None


def get_temperature():
    """Gets the temperature from the primary source.

    That is the Prometheus metric when one is configured, otherwise the CPU
    sensor. There is deliberately no silent fallback from Prometheus to the CPU:
    they measure different things, and substituting a ~30C SoC reading for an
    ambient one would run the fan and disable the heating on bad data. When the
    primary source fails, the failsafe takes over instead.
    """
    if PROMETHEUS_ENDPOINT and PROMETHEUS_METRIC_NAME:
        return get_prometheus_temperature()
    return get_cpu_temperature()


def set_fan_speed(duty_cycle):
    """Sets the fan speed using PWM."""
    global h, current_duty_cycle
    # Ensure duty cycle is within 0-100 range
    duty_cycle = max(0, min(100, duty_cycle))
    current_duty_cycle = duty_cycle

    if h:
        try:
            lgpio.tx_pwm(h, PWM_GPIO, PWM_FREQUENCY, duty_cycle)
        except Exception as e:
            log.error("Error setting fan speed: %s", e)


def handle_static_mode():
    """Handles the static fan speed mode."""
    try:
        duty_cycle = float(STATIC_DUTY_CYCLE)
        if not 0 <= duty_cycle <= 100:
            raise ValueError("Duty cycle must be between 0 and 100")
        log.info("Setting static duty cycle to %s%%", duty_cycle)
        set_fan_speed(duty_cycle)
    except (ValueError, TypeError) as e:
        log.error("Invalid STATIC_DUTY_CYCLE: %s", e)
        cleanup()
        exit(1)


def handle_threshold_mode(temp):
    """Handles the temperature-based threshold mode."""
    global high_speed_mode
    if temp is not None:
        if temp > TEMP_ON_THRESHOLD and not high_speed_mode:
            log.info(
                "Temperature (%.2f°C) exceeded ON threshold (%s°C). Setting fan to %s%%.",
                temp, TEMP_ON_THRESHOLD, THRESHOLD_ON_DUTY_CYCLE,
            )
            set_fan_speed(THRESHOLD_ON_DUTY_CYCLE)
            high_speed_mode = True
        elif temp < TEMP_OFF_THRESHOLD and high_speed_mode:
            log.info(
                "Temperature (%.2f°C) below OFF threshold (%s°C). Setting fan to %s%%.",
                temp, TEMP_OFF_THRESHOLD, THRESHOLD_OFF_DUTY_CYCLE,
            )
            set_fan_speed(THRESHOLD_OFF_DUTY_CYCLE)
            high_speed_mode = False


def handle_heating_mode(temp):
    """Handles the temperature-based heating mode."""
    global heating_on
    if not HEATING_ENABLED:
        return False

    if temp is not None:
        if temp < HEATING_ON_THRESHOLD and not heating_on:
            log.info(
                "Temperature (%.2f°C) below heating ON threshold (%s°C). Turning heating ON.",
                temp, HEATING_ON_THRESHOLD,
            )
            lgpio.gpio_write(h, HEATING_GPIO, 1)
            heating_on = True
        elif temp > HEATING_OFF_THRESHOLD and heating_on:
            log.info(
                "Temperature (%.2f°C) above heating OFF threshold (%s°C). Turning heating OFF.",
                temp, HEATING_OFF_THRESHOLD,
            )
            lgpio.gpio_write(h, HEATING_GPIO, 0)
            heating_on = False


def enter_failsafe():
    """Puts the controller into a safe state after repeated failed readings.

    Heating is switched off unconditionally: a heater left running on stale data
    is the worst outcome. The fan is then driven from the CPU temperature alone,
    so a hot Pi still gets cooled, but a cold box does not get a fan pulling
    outside air in on the strength of a reading we no longer have.
    """
    global failsafe_active, high_speed_mode, heating_on

    first_entry = not failsafe_active
    failsafe_active = True

    if first_entry:
        log.error(
            "Temperature source failed %d times in a row; entering failsafe.",
            consecutive_failures,
        )

    if HEATING_ENABLED and heating_on:
        log.warning("Failsafe: turning heating OFF.")
        lgpio.gpio_write(h, HEATING_GPIO, 0)
        heating_on = False

    if STATIC_DUTY_CYCLE is not None:
        return  # static mode owns the fan, leave it alone

    cpu_temp = get_cpu_temperature()
    if cpu_temp is None:
        target = THRESHOLD_ON_DUTY_CYCLE
        target_high = True
        reason = "CPU temperature unreadable, assuming hot"
    elif cpu_temp > FAILSAFE_CPU_TEMP:
        target = THRESHOLD_ON_DUTY_CYCLE
        target_high = True
        reason = f"CPU at {cpu_temp:.2f}°C, above FAILSAFE_CPU_TEMP ({FAILSAFE_CPU_TEMP}°C)"
    else:
        target = THRESHOLD_OFF_DUTY_CYCLE
        target_high = False
        reason = f"CPU at {cpu_temp:.2f}°C, below FAILSAFE_CPU_TEMP ({FAILSAFE_CPU_TEMP}°C)"

    if first_entry or target != current_duty_cycle:
        log.warning("Failsafe: %s. Setting fan to %s%%.", reason, target)
    set_fan_speed(target)
    high_speed_mode = target_high


def leave_failsafe(temp):
    """Returns to normal operation after the temperature source recovers."""
    global failsafe_active
    log.info("Temperature source recovered (%.2f°C); leaving failsafe.", temp)
    failsafe_active = False


def setup():
    """Sets up the GPIO pin and PWM."""
    global h
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, PWM_GPIO)
        claimed_pins.append(PWM_GPIO)
        if HEATING_ENABLED:
            lgpio.gpio_claim_output(h, HEATING_GPIO)
            claimed_pins.append(HEATING_GPIO)
            log.info("Claimed HEATING_GPIO pin")
        log.info("GPIO setup complete.")
    except Exception as e:
        log.error("Error setting up GPIO: %s", e)
        cleanup()
        exit(1)


def cleanup(signum=None, frame=None):
    """Cleans up GPIO resources."""
    log.info("Shutting down gracefully...")
    if h:
        set_fan_speed(THRESHOLD_ON_DUTY_CYCLE)
        if HEATING_ENABLED and HEATING_GPIO in claimed_pins:
            lgpio.gpio_write(h, HEATING_GPIO, 0)
            log.info("Released HEATING_GPIO pin")
        for pin in claimed_pins:
            lgpio.gpio_free(h, pin)
        lgpio.gpiochip_close(h)
        log.info("Set fan speed to THRESHOLD_ON_DUTY_CYCLE (%s)", THRESHOLD_ON_DUTY_CYCLE)
    exit(0)


def initialize_threshold_mode():
    """Sets the initial fan speed for threshold mode."""
    global high_speed_mode
    temp = get_temperature()
    if temp and temp > TEMP_ON_THRESHOLD:
        log.info("Initial temperature is high, starting fan at %s%%.", THRESHOLD_ON_DUTY_CYCLE)
        set_fan_speed(THRESHOLD_ON_DUTY_CYCLE)
        high_speed_mode = True
    else:
        log.info("Setting fan to %s%%.", THRESHOLD_OFF_DUTY_CYCLE)
        set_fan_speed(THRESHOLD_OFF_DUTY_CYCLE)
    if HEATING_ENABLED:
        handle_heating_mode(temp)


def main():
    """Main function."""
    global consecutive_failures

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    setup()

    if STATIC_DUTY_CYCLE is not None:
        log.info("Starting static fan control.")
        handle_static_mode()
    else:
        log.info("Starting temperature-based fan control.")
        initialize_threshold_mode()

    while True:
        temp = get_temperature()

        if temp is not None:
            if failsafe_active:
                leave_failsafe(temp)
            consecutive_failures = 0

            if STATIC_DUTY_CYCLE is None:
                handle_threshold_mode(temp)
            handle_heating_mode(temp)

            log_message = f"Temp: {temp:.2f}°C, Fan: {current_duty_cycle}%"
            if HEATING_ENABLED:
                heating_status = "ON" if heating_on else "OFF"
                log_message += f", Heating: {heating_status}"
            log.info(log_message)

        else:
            consecutive_failures += 1
            if failsafe_active:
                log.warning(
                    "Temperature reading failed (%d consecutive failures, still in failsafe).",
                    consecutive_failures,
                )
            else:
                log.warning(
                    "Temperature reading failed (%d/%d before failsafe).",
                    consecutive_failures, FAILSAFE_AFTER_FAILURES,
                )
            if consecutive_failures >= FAILSAFE_AFTER_FAILURES:
                enter_failsafe()

        time.sleep(UPDATE_INTERVAL)


if __name__ == "__main__":
    main()
