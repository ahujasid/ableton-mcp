#!/usr/bin/env python3
"""
Precise EQ Testing Script for Ableton MCP.
This script tests precise parameter control for the EQ Eight device.
"""

import socket
import json
import time
import sys
import math

# Connection settings
HOST = "localhost"
PORT = 9877

def print_divider(title=""):
    """Print a divider with an optional title."""
    print("\n" + "=" * 60)
    if title:
        print(f"{title.center(60)}")
    print("=" * 60)

def send_command(command_type, params=None):
    """Send a command to the MCP server and return the result."""
    if params is None:
        params = {}
    
    print(f"Sending command: {command_type}")
    print(f"Parameters: {json.dumps(params, indent=2)}")
    
    try:
        # Create a socket connection
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            # Connect to the server
            sock.connect((HOST, PORT))
            
            # Prepare the command
            command = {
                "type": command_type,
                "params": params
            }
            
            # Send the command
            sock.sendall(json.dumps(command).encode('utf-8'))
            
            # Receive the response
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                
                # Check if we've received a complete JSON response
                try:
                    json.loads(response.decode('utf-8'))
                    break  # If we can parse it, we have a complete response
                except json.JSONDecodeError:
                    continue  # Keep receiving if the JSON is incomplete
            
            # Parse and return the response
            try:
                result = json.loads(response.decode('utf-8'))
                print(f"Response: {json.dumps(result, indent=2)}")
                return result
            except json.JSONDecodeError:
                print(f"Error decoding JSON response: {response.decode('utf-8')}")
                return {"status": "error", "message": "Failed to decode response"}
    except Exception as e:
        print(f"Error sending command: {str(e)}")
        return {"status": "error", "message": str(e)}

def setup_test_environment():
    """Set up the test environment by creating a track and loading an EQ Eight."""
    print_divider("SETTING UP TEST ENVIRONMENT")
    
    # Create a MIDI track
    track_result = send_command("create_midi_track")
    if track_result.get("status") != "success" or "index" not in track_result.get("result", {}):
        print("❌ Failed to create a MIDI track for testing")
        return None, None
    
    track_index = track_result["result"]["index"]
    print(f"✅ Created MIDI track at index {track_index}")
    
    # Rename the track for clarity
    rename_result = send_command("set_track_name", {
        "track_index": track_index,
        "name": "Precise EQ Test Track"
    })
    if rename_result.get("status") == "success":
        print("✅ Renamed track to 'Precise EQ Test Track'")
    
    # Load an EQ Eight onto the track
    eq_result = send_command("load_browser_item", {
        "track_index": track_index,
        "item_uri": "query:AudioFx#EQ%20Eight"
    })
    
    if eq_result.get("status") != "success":
        print(f"❌ Failed to load EQ Eight. Error: {eq_result.get('message', 'Unknown error')}")
        return track_index, None
    
    print("✅ Successfully loaded EQ Eight onto the track")
    
    # Get track info to find the device index
    track_info = send_command("get_track_info", {"track_index": track_index})
    
    if track_info.get("status") != "success" or "devices" not in track_info.get("result", {}):
        print("❌ Failed to get track info")
        return track_index, None
    
    # Find the EQ Eight device
    devices = track_info["result"]["devices"]
    device_index = None
    for device in devices:
        if "EQ Eight" in device.get("name", ""):
            device_index = device.get("index", 0)
            break
    
    if device_index is None:
        print("❌ Could not find EQ Eight device in track")
        return track_index, None
    
    print(f"✅ Found EQ Eight at device index {device_index}")
    
    return track_index, device_index

def frequency_to_normalized(freq_hz):
    """Convert frequency in Hz to normalized value (0-1)."""
    # EQ Eight frequency range is approximately 20Hz to 20kHz on a logarithmic scale
    log_min = math.log10(20)  # 20 Hz
    log_max = math.log10(20000)  # 20 kHz
    log_freq = math.log10(max(20, min(20000, freq_hz)))  # Clamp to valid range
    return (log_freq - log_min) / (log_max - log_min)

def normalized_to_frequency(normalized_value):
    """Convert normalized value (0-1) to frequency in Hz."""
    # EQ Eight frequency range is approximately 20Hz to 20kHz on a logarithmic scale
    log_min = math.log10(20)  # 20 Hz
    log_max = math.log10(20000)  # 20 kHz
    log_freq = normalized_value * (log_max - log_min) + log_min
    return round(10 ** log_freq)

def q_to_normalized(q_value):
    """Convert Q value to normalized value (0-1)."""
    # EQ Eight Q range is approximately 0.1 to 10
    # This is a rough approximation
    return min(1.0, max(0.0, q_value / 10.0))

def normalized_to_q(normalized_value):
    """Convert normalized value (0-1) to Q value."""
    # EQ Eight Q range is approximately 0.1 to 10
    # This is a rough approximation
    return round(normalized_value * 10, 2)

def test_precise_frequency_control(track_index, device_index):
    """Test precise frequency control for EQ bands."""
    print_divider("TESTING PRECISE FREQUENCY CONTROL")
    
    if track_index is None or device_index is None:
        print("❌ Cannot test without track and device indices")
        return False
    
    # Test frequencies across the spectrum
    test_frequencies = [50, 100, 200, 500, 1000, 2000, 5000, 10000]
    
    # Test multiple bands to ensure they all work
    test_bands = [0, 2, 4, 7]  # Bands 1, 3, 5, and 8
    
    all_passed = True
    
    for band_index in test_bands:
        band_number = band_index + 1
        print(f"\n--- Testing Band {band_number} ---")
        
        # Enable the band
        result = send_command("set_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_name": f"{band_number} Filter On A",
            "value": 1  # 1 = On
        })
        
        if result.get("status") != "success":
            print(f"❌ Failed to enable band {band_number}")
            all_passed = False
            continue
        
        print(f"✅ Enabled band {band_number}")
        
        # Set filter type to Bell
        params_result = send_command("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index
        })
        
        filter_type_param = None
        for param in params_result["result"]["parameters"]:
            if param.get("name") == f"{band_number} Filter Type A":
                filter_type_param = param
                break
        
        if filter_type_param is None:
            print(f"❌ Could not find filter type parameter for band {band_number}")
            all_passed = False
            continue
        
        # Find the index of the "Bell" filter type
        filter_type = "Bell"
        filter_type_index = None
        for i, item in enumerate(filter_type_param.get("value_items", [])):
            if item == filter_type:
                filter_type_index = i
                break
        
        if filter_type_index is None:
            print(f"❌ Could not find filter type '{filter_type}' for band {band_number}")
            all_passed = False
            continue
        
        result = send_command("set_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_name": f"{band_number} Filter Type A",
            "value": filter_type_index
        })
        
        if result.get("status") != "success":
            print(f"❌ Failed to set filter type for band {band_number}")
            all_passed = False
            continue
        
        print(f"✅ Set filter type for band {band_number} to {filter_type}")
        
        # Test each frequency
        for freq in test_frequencies:
            normalized_freq = frequency_to_normalized(freq)
            
            result = send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": f"{band_number} Frequency A",
                "value": normalized_freq
            })
            
            if result.get("status") != "success":
                print(f"❌ Failed to set frequency for band {band_number} to {freq} Hz")
                all_passed = False
                continue
            
            # Get the actual normalized value that was set
            actual_normalized = result["result"]["value"]
            # Convert back to frequency
            actual_freq = normalized_to_frequency(actual_normalized)
            
            # Calculate error percentage
            error_pct = abs(actual_freq - freq) / freq * 100
            
            if error_pct < 5:  # Allow 5% error due to rounding and approximation
                print(f"✅ Set frequency for band {band_number} to {freq} Hz (actual: {actual_freq} Hz, error: {error_pct:.2f}%)")
            else:
                print(f"⚠️ Set frequency for band {band_number} to {freq} Hz, but actual value is {actual_freq} Hz (error: {error_pct:.2f}%)")
                all_passed = False
    
    return all_passed

def test_precise_gain_control(track_index, device_index):
    """Test precise gain control for EQ bands."""
    print_divider("TESTING PRECISE GAIN CONTROL")
    
    if track_index is None or device_index is None:
        print("❌ Cannot test without track and device indices")
        return False
    
    # Test gain values
    test_gains = [-12, -6, -3, 0, 3, 6, 12]
    
    # Test multiple bands to ensure they all work
    test_bands = [0, 2, 4, 7]  # Bands 1, 3, 5, and 8
    
    all_passed = True
    
    for band_index in test_bands:
        band_number = band_index + 1
        print(f"\n--- Testing Band {band_number} ---")
        
        # Test each gain value
        for gain in test_gains:
            result = send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": f"{band_number} Gain A",
                "value": gain
            })
            
            if result.get("status") != "success":
                print(f"❌ Failed to set gain for band {band_number} to {gain} dB")
                all_passed = False
                continue
            
            # Get the actual value that was set
            actual_gain = result["result"]["value"]
            
            # Calculate error
            error = abs(actual_gain - gain)
            
            if error < 0.01:  # Allow small error due to floating point precision
                print(f"✅ Set gain for band {band_number} to {gain} dB (actual: {actual_gain} dB)")
            else:
                print(f"⚠️ Set gain for band {band_number} to {gain} dB, but actual value is {actual_gain} dB (error: {error:.2f})")
                all_passed = False
    
    return all_passed

def test_precise_q_control(track_index, device_index):
    """Test precise Q control for EQ bands."""
    print_divider("TESTING PRECISE Q CONTROL")
    
    if track_index is None or device_index is None:
        print("❌ Cannot test without track and device indices")
        return False
    
    # Test Q values
    test_q_values = [0.3, 0.7, 1.0, 2.0, 5.0]
    
    # Test multiple bands to ensure they all work
    test_bands = [0, 2, 4, 7]  # Bands 1, 3, 5, and 8
    
    all_passed = True
    
    for band_index in test_bands:
        band_number = band_index + 1
        print(f"\n--- Testing Band {band_number} ---")
        
        # Test each Q value
        for q in test_q_values:
            normalized_q = q_to_normalized(q)
            
            result = send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": f"{band_number} Resonance A",
                "value": normalized_q
            })
            
            if result.get("status") != "success":
                print(f"❌ Failed to set Q for band {band_number} to {q}")
                all_passed = False
                continue
            
            # Get the actual normalized value that was set
            actual_normalized = result["result"]["value"]
            # Convert back to Q
            actual_q = normalized_to_q(actual_normalized)
            
            # Calculate error percentage
            error_pct = abs(actual_q - q) / q * 100
            
            if error_pct < 10:  # Allow 10% error due to approximation in our conversion
                print(f"✅ Set Q for band {band_number} to {q} (actual: {actual_q}, error: {error_pct:.2f}%)")
            else:
                print(f"⚠️ Set Q for band {band_number} to {q}, but actual value is {actual_q} (error: {error_pct:.2f}%)")
                all_passed = False
    
    return all_passed

def test_filter_types(track_index, device_index):
    """Test setting different filter types."""
    print_divider("TESTING FILTER TYPES")
    
    if track_index is None or device_index is None:
        print("❌ Cannot test without track and device indices")
        return False
    
    # Test multiple bands to ensure they all work
    test_bands = [0, 2, 4, 7]  # Bands 1, 3, 5, and 8
    
    all_passed = True
    
    for band_index in test_bands:
        band_number = band_index + 1
        print(f"\n--- Testing Band {band_number} ---")
        
        # Get filter type parameter to find available options
        params_result = send_command("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index
        })
        
        filter_type_param = None
        for param in params_result["result"]["parameters"]:
            if param.get("name") == f"{band_number} Filter Type A":
                filter_type_param = param
                break
        
        if filter_type_param is None:
            print(f"❌ Could not find filter type parameter for band {band_number}")
            all_passed = False
            continue
        
        filter_types = filter_type_param.get("value_items", [])
        print(f"Available filter types for band {band_number}: {filter_types}")
        
        # Test each filter type
        for i, filter_type in enumerate(filter_types):
            result = send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": f"{band_number} Filter Type A",
                "value": i
            })
            
            if result.get("status") != "success":
                print(f"❌ Failed to set filter type for band {band_number} to {filter_type}")
                all_passed = False
                continue
            
            print(f"✅ Set filter type for band {band_number} to {filter_type}")
    
    return all_passed

def test_scale_parameter(track_index, device_index):
    """Test the Scale parameter."""
    print_divider("TESTING SCALE PARAMETER")
    
    if track_index is None or device_index is None:
        print("❌ Cannot test without track and device indices")
        return False
    
    # Test scale values
    test_scales = [0.5, 0.75, 1.0, 1.5, 2.0]
    
    # Test each scale value
    for scale in test_scales:
        result = send_command("set_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_name": "Scale",
            "value": scale
        })
        
        if result.get("status") != "success":
            print(f"❌ Failed to set Scale to {scale}")
            return False
        
        # Get the actual value that was set
        actual_scale = result["result"]["value"]
        
        # Calculate error
        error = abs(actual_scale - scale)
        
        if error < 0.01:  # Allow small error due to floating point precision
            print(f"✅ Set Scale to {scale} (actual: {actual_scale})")
        else:
            print(f"⚠️ Set Scale to {scale}, but actual value is {actual_scale} (error: {error:.2f})")
    
    return True

def main():
    """Run all tests."""
    print_divider("ABLETON MCP PRECISE EQ PARAMETER CONTROL TEST")
    
    # Check if server is running
    print("\nChecking connection to MCP server...")
    session_info = send_command("get_session_info")
    if session_info.get("status") != "success":
        print("❌ Error: Failed to connect to MCP server")
        return 1
    
    print("✅ Successfully connected to MCP server")
    
    # Set up test environment
    track_index, device_index = setup_test_environment()
    if track_index is None:
        print("❌ Failed to set up test environment")
        return 1
    
    # Run tests
    tests = [
        ("precise_frequency_control", lambda: test_precise_frequency_control(track_index, device_index)),
        ("precise_gain_control", lambda: test_precise_gain_control(track_index, device_index)),
        ("precise_q_control", lambda: test_precise_q_control(track_index, device_index)),
        ("filter_types", lambda: test_filter_types(track_index, device_index)),
        ("scale_parameter", lambda: test_scale_parameter(track_index, device_index))
    ]
    
    results = {}
    for name, test_func in tests:
        print(f"\nRunning test for {name}...")
        try:
            result = test_func()
            results[name] = result
        except Exception as e:
            print(f"❌ Test failed with exception: {str(e)}")
            results[name] = False
    
    # Print summary
    print_divider("TEST SUMMARY")
    all_passed = True
    for name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{name}: {status}")
        if not result:
            all_passed = False
    
    if all_passed:
        print("\n✅ All tests passed successfully!")
    else:
        print("\n⚠️ Some tests failed. See details above.")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
