# Device Parameter Control in Ableton MCP

This document provides a comprehensive overview of the device parameter control capabilities implemented in the Ableton MCP system.

## Table of Contents

1. [Overview](#overview)
2. [Core Functions](#core-functions)
3. [EQ Eight Specific Functions](#eq-eight-specific-functions)
4. [Parameter Naming Conventions](#parameter-naming-conventions)
5. [Value Normalization](#value-normalization)
6. [Usage Examples](#usage-examples)
7. [Testing](#testing)
8. [Future Enhancements](#future-enhancements)

## Overview

The device parameter control implementation allows for precise control of parameters for any device in Ableton Live through the MCP system. It provides both generic functions that work with any device and specialized functions for common devices like the EQ Eight.

The implementation follows a hybrid approach:
- Generic functions for discovering and controlling parameters on any device
- Specialized functions for common operations on specific devices
- Value normalization utilities for converting between human-readable values and Ableton's internal normalized values

## Core Functions

### In Remote Script (`AbletonMCP_Remote_Script/__init__.py`)

#### `_get_device_parameters(self, track_index, device_index)`
Retrieves all parameters for a specified device on a track.

- **Parameters:**
  - `track_index`: Index of the track containing the device
  - `device_index`: Index of the device on the track
- **Returns:** Dictionary containing device information and a list of parameters with their properties (name, value, min, max, etc.)

#### `_set_device_parameter(self, track_index, device_index, parameter_name=None, parameter_index=None, value=None)`
Sets a device parameter by name or index.

- **Parameters:**
  - `track_index`: Index of the track containing the device
  - `device_index`: Index of the device on the track
  - `parameter_name`: Name of the parameter to set (optional if parameter_index is provided)
  - `parameter_index`: Index of the parameter to set (optional if parameter_name is provided)
  - `value`: Value to set the parameter to
- **Returns:** Dictionary containing the result of the operation

### In MCP Server (`MCP_Server/server.py`)

#### `get_device_parameters(ctx, track_index, device_index)`
Exposes the Remote Script's `_get_device_parameters` function to the MCP API.

- **Parameters:**
  - `ctx`: Context object
  - `track_index`: Index of the track containing the device
  - `device_index`: Index of the device on the track
- **Returns:** JSON response containing device information and parameters

#### `set_device_parameter(ctx, track_index, device_index, parameter_name=None, parameter_index=None, value=None)`
Exposes the Remote Script's `_set_device_parameter` function to the MCP API.

- **Parameters:**
  - `ctx`: Context object
  - `track_index`: Index of the track containing the device
  - `device_index`: Index of the device on the track
  - `parameter_name`: Name of the parameter to set (optional if parameter_index is provided)
  - `parameter_index`: Index of the parameter to set (optional if parameter_name is provided)
  - `value`: Value to set the parameter to
- **Returns:** JSON response containing the result of the operation

## EQ Eight Specific Functions

### In Remote Script (`AbletonMCP_Remote_Script/__init__.py`)

#### `_set_eq_band(self, track_index, device_index, band_index, frequency=None, gain=None, q=None, filter_type=None)`
Sets parameters for a specific band in an EQ Eight device.

- **Parameters:**
  - `track_index`: Index of the track containing the EQ Eight
  - `device_index`: Index of the EQ Eight device on the track
  - `band_index`: Index of the band to modify (0-7)
  - `frequency`: Frequency in Hz (optional)
  - `gain`: Gain in dB (optional)
  - `q`: Q factor (optional)
  - `filter_type`: Filter type (optional)
- **Returns:** Dictionary containing the result of the operation

#### `_set_eq_global(self, track_index, device_index, scale=None)`
Sets global parameters for an EQ Eight device.

- **Parameters:**
  - `track_index`: Index of the track containing the EQ Eight
  - `device_index`: Index of the EQ Eight device on the track
  - `scale`: Scale value (optional)
- **Returns:** Dictionary containing the result of the operation

#### `_apply_eq_preset(self, track_index, device_index, preset_name)`
Applies a preset to an EQ Eight device.

- **Parameters:**
  - `track_index`: Index of the track containing the EQ Eight
  - `device_index`: Index of the EQ Eight device on the track
  - `preset_name`: Name of the preset to apply
- **Returns:** Dictionary containing the result of the operation

### In MCP Server (`MCP_Server/server.py`)

#### `set_eq_band(ctx, track_index, device_index, band_index, frequency=None, gain=None, q=None, filter_type=None)`
Exposes the Remote Script's `_set_eq_band` function to the MCP API.

#### `set_eq_global(ctx, track_index, device_index, scale=None)`
Exposes the Remote Script's `_set_eq_global` function to the MCP API.

#### `apply_eq_preset(ctx, track_index, device_index, preset_name)`
Exposes the Remote Script's `_apply_eq_preset` function to the MCP API.

## Parameter Naming Conventions

Understanding the parameter naming conventions in Ableton Live is crucial for using the device parameter control functions effectively.

### EQ Eight Parameter Names

EQ Eight parameters follow a specific naming pattern:

- Band parameters: `{band_number} {parameter_name} A`
  - Examples: `1 Frequency A`, `3 Gain A`, `5 Resonance A`, `7 Filter Type A`
- Band enable/disable: `{band_number} Filter On A`
  - Example: `2 Filter On A`
- Global parameters: Simple names like `Scale`

### Other Devices

Each device has its own parameter naming convention. Use the `get_device_parameters` function to discover the available parameters for a specific device.

## Value Normalization

Many parameters in Ableton Live use normalized values (0-1) internally, which need to be converted to/from human-readable values.

### Frequency Normalization

EQ Eight frequency values range from approximately 20Hz to 20kHz on a logarithmic scale. The conversion functions are:

```python
def frequency_to_normalized(freq_hz):
    """Convert frequency in Hz to normalized value (0-1)."""
    log_min = math.log10(20)  # 20 Hz
    log_max = math.log10(20000)  # 20 kHz
    log_freq = math.log10(max(20, min(20000, freq_hz)))  # Clamp to valid range
    return (log_freq - log_min) / (log_max - log_min)

def normalized_to_frequency(normalized_value):
    """Convert normalized value (0-1) to frequency in Hz."""
    log_min = math.log10(20)  # 20 Hz
    log_max = math.log10(20000)  # 20 kHz
    log_freq = normalized_value * (log_max - log_min) + log_min
    return round(10 ** log_freq)
```

### Q Factor Normalization

EQ Eight Q values range from approximately 0.1 to 10. The conversion functions are:

```python
def q_to_normalized(q_value):
    """Convert Q value to normalized value (0-1)."""
    return min(1.0, max(0.0, q_value / 10.0))

def normalized_to_q(normalized_value):
    """Convert normalized value (0-1) to Q value."""
    return round(normalized_value * 10, 2)
```

## Usage Examples

### Getting Device Parameters

```python
# Get all parameters for the first device on the first track
result = send_command("get_device_parameters", {
    "track_index": 0,
    "device_index": 0
})

# Print parameter names and values
for param in result["result"]["parameters"]:
    print(f"{param['name']}: {param['value']}")
```

### Setting a Device Parameter by Name

```python
# Set the "Threshold" parameter of a Compressor
result = send_command("set_device_parameter", {
    "track_index": 0,
    "device_index": 0,
    "parameter_name": "Threshold",
    "value": -20.0  # -20 dB
})
```

### Setting an EQ Band Parameter

```python
# Set the frequency of band 3 to 1000 Hz
result = send_command("set_eq_band", {
    "track_index": 0,
    "device_index": 0,
    "band_index": 2,  # 0-based index, so this is band 3
    "frequency": 1000  # 1000 Hz
})
```

### Applying an EQ Preset

```python
# Apply the "Low Cut" preset
result = send_command("apply_eq_preset", {
    "track_index": 0,
    "device_index": 0,
    "preset_name": "Low Cut"
})
```

## Testing

We've developed comprehensive test scripts to verify the functionality of the device parameter control implementation:

### `precise_eq_test.py`

Tests precise parameter control for the EQ Eight device, including:
- Frequency control across multiple bands
- Gain control
- Q factor control
- Filter type switching
- Global scale parameter

### `audio_effects_test.py`

Tests parameter control for various audio effects to ensure the generic approach works across different devices:
- Compressor
- Reverb
- Auto Filter
- Delay

## Future Enhancements

Potential future enhancements to the device parameter control implementation:

1. **More Specialized Functions**: Create specialized functions for other common devices like Compressor, Reverb, etc.

2. **Higher-Level API**: Develop a higher-level API that abstracts away parameter normalization for all devices.

3. **Parameter Presets**: Implement a system for saving and loading parameter presets for any device.

4. **More Accurate Normalization**: Improve the accuracy of the normalization functions for frequency, Q, and other parameters.

5. **Parameter Automation**: Add support for automating parameters over time.

6. **Parameter Mapping**: Create a mapping system to link parameters between different devices or to external controllers.
