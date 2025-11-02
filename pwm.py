import os
import time
import signal
import lgpio
import requests

# Configuration
PWM_GPIO = int(os.getenv("PWM_GPIO", 18))
PWM_FREQUENCY = int(os.getenv("PWM_FREQUENCY", 100))
STATIC_DUTY_CYCLE = os.getenv("STATIC_DUTY_CYCLE")
TEMP_ON_THRESHOLD = float(os.getenv("TEMP_ON_THRESHOLD", 60.0))
TEMP_OFF_THRESHOLD = float(os.getenv("TEMP_OFF_THRESHOLD", 50.0))
IDLE_DUTY_CYCLE = float(os.getenv("IDLE_DUTY_CYCLE", 0.0))
TEMP_FILE = os.getenv("TEMP_FILE", "/sys/class/thermal/thermal_zone0/temp")
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 5))
PROMETHEUS_ENDPOINT = os.getenv("PROMETHEUS_ENDPOINT")
PROMETHEUS_METRIC_NAME = os.getenv("PROMETHEUS_METRIC_NAME")
THRESHOLD_ON_DUTY_CYCLE = float(os.getenv("THRESHOLD_ON_DUTY_CYCLE", 100.0))
THRESHOLD_OFF_DUTY_CYCLE = float(os.getenv("THRESHOLD_OFF_DUTY_CYCLE", IDLE_DUTY_CYCLE))

if not 0 <= IDLE_DUTY_CYCLE <= 100:
    raise ValueError("IDLE_DUTY_CYCLE must be between 0 and 100")

if not 0 <= THRESHOLD_ON_DUTY_CYCLE <= 100:
    raise ValueError("THRESHOLD_ON_DUTY_CYCLE must be between 0 and 100")

if not 0 <= THRESHOLD_OFF_DUTY_CYCLE <= 100:
    raise ValueError("THRESHOLD_OFF_DUTY_CYCLE must be between 0 and 100")

# Global state
h = None  # lgpio handle
high_speed_mode = False

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
        print(f"Metric '{PROMETHEUS_METRIC_NAME}' not found in Prometheus endpoint.")
        return None
    except (requests.RequestException, ValueError) as e:
        print(f"Error getting temperature from Prometheus: {e}")
        return None


def get_temperature():
    """Gets the temperature from Prometheus if configured, otherwise from the CPU."""
    if PROMETHEUS_ENDPOINT and PROMETHEUS_METRIC_NAME:
        temp = get_prometheus_temperature()
        if temp is not None:
            return temp
        print("Falling back to CPU temperature.")

    try:
        with open(TEMP_FILE, "r") as f:
            temp_str = f.read()
        return float(temp_str) / 1000.0
    except (IOError, ValueError) as e:
        print(f"Error reading CPU temperature: {e}")
        return None

def set_fan_speed(duty_cycle):
    """Sets the fan speed using PWM."""
    global h
    # Ensure duty cycle is within 0-100 range
    duty_cycle = max(0, min(100, duty_cycle))
    
    if h:
        try:
            lgpio.tx_pwm(h, PWM_GPIO, PWM_FREQUENCY, duty_cycle)
        except Exception as e:
            print(f"Error setting fan speed: {e}")

def handle_static_mode():
    """Handles the static fan speed mode."""
    try:
        duty_cycle = float(STATIC_DUTY_CYCLE)
        if not 0 <= duty_cycle <= 100:
            raise ValueError("Duty cycle must be between 0 and 100")
        print(f"Setting static duty cycle to {duty_cycle}%")
        set_fan_speed(duty_cycle)
        # Keep the script running
        while True:
            time.sleep(1)
    except (ValueError, TypeError) as e:
        print(f"Invalid STATIC_DUTY_CYCLE: {e}")
        cleanup()
        exit(1)

def handle_threshold_mode():
    """Handles the temperature-based threshold mode."""
    global high_speed_mode
    temp = get_temperature()
    if temp is not None:
        print(f"Current temperature: {temp:.2f}°C")
        if temp > TEMP_ON_THRESHOLD and not high_speed_mode:
            print(f"Temperature ({temp:.2f}°C) exceeded ON threshold ({TEMP_ON_THRESHOLD}°C). Setting fan to {THRESHOLD_ON_DUTY_CYCLE}%.")
            set_fan_speed(THRESHOLD_ON_DUTY_CYCLE)
            high_speed_mode = True
        elif temp < TEMP_OFF_THRESHOLD and high_speed_mode:
            print(f"Temperature ({temp:.2f}°C) below OFF threshold ({TEMP_OFF_THRESHOLD}°C). Setting fan to {THRESHOLD_OFF_DUTY_CYCLE}%.")
            set_fan_speed(THRESHOLD_OFF_DUTY_CYCLE)
            high_speed_mode = False

def setup():
    """Sets up the GPIO pin and PWM."""
    global h
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, PWM_GPIO)
        print("GPIO setup complete.")
    except Exception as e:
        print(f"Error setting up GPIO: {e}")
        exit(1)


def cleanup(signum=None, frame=None):
    """Cleans up GPIO resources."""
    print("Shutting down gracefully...")
    if h:
        set_fan_speed(0)
        lgpio.gpio_free(h, PWM_GPIO)
        lgpio.gpiochip_close(h)
    exit(0)

def initialize_threshold_mode():
    """Sets the initial fan speed for threshold mode."""
    global high_speed_mode
    temp = get_temperature()
    if temp and temp > TEMP_ON_THRESHOLD:
        print(f"Initial temperature is high, starting fan at {THRESHOLD_ON_DUTY_CYCLE}%.")
        set_fan_speed(THRESHOLD_ON_DUTY_CYCLE)
        high_speed_mode = True
    else:
        print(f"Setting fan to {THRESHOLD_OFF_DUTY_CYCLE}%.")
        set_fan_speed(THRESHOLD_OFF_DUTY_CYCLE)

def main():
    """Main function."""
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    setup()

    if STATIC_DUTY_CYCLE is not None:
        handle_static_mode()
    else:
        print("Starting temperature-based fan control.")
        initialize_threshold_mode()
        while True:
            handle_threshold_mode()
            time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    main()