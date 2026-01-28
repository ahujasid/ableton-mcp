#!/usr/bin/env python3
"""
Audio Effects Testing Script for Ableton MCP.
This script tests parameter control for various audio effects to ensure
the generic device parameter control implementation works across different devices.
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
    print("\n" + "=" * 80)
    if title:
        print(f"{title.center(80)}")
    print("=" * 80)

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

def setup_test_track(track_name="Audio Effects Test Track"):
    """Set up a test track and return its index."""
    print_divider(f"SETTING UP TEST TRACK: {track_name}")
    
    # Create a MIDI track
    track_result = send_command("create_midi_track")
    if track_result.get("status") != "success" or "index" not in track_result.get("result", {}):
        print("❌ Failed to create a MIDI track for testing")
        return None
    
    track_index = track_result["result"]["index"]
    print(f"✅ Created MIDI track at index {track_index}")
    
    # Rename the track for clarity
    rename_result = send_command("set_track_name", {
        "track_index": track_index,
        "name": track_name
    })
    if rename_result.get("status") == "success":
        print(f"✅ Renamed track to '{track_name}'")
    
    return track_index

def load_device(track_index, device_uri, device_name):
    """Load a device onto a track and return its index."""
    print_divider(f"LOADING DEVICE: {device_name}")
    
    if track_index is None:
        print("❌ Cannot load device without a valid track")
        return None
    
    # Load the device onto the track
    device_result = send_command("load_browser_item", {
        "track_index": track_index,
        "item_uri": device_uri
    })
    
    if device_result.get("status") != "success":
        print(f"❌ Failed to load {device_name}. Error: {device_result.get('message', 'Unknown error')}")
        return None
    
    print(f"✅ Successfully loaded {device_name} onto the track")
    
    # Get track info to find the device index
    track_info = send_command("get_track_info", {"track_index": track_index})
    
    if track_info.get("status") != "success" or "devices" not in track_info.get("result", {}):
        print("❌ Failed to get track info")
        return None
    
    # Find the device
    devices = track_info["result"]["devices"]
    device_index = None
    for device in devices:
        if device_name in device.get("name", ""):
            device_index = device.get("index", 0)
            break
    
    if device_index is None:
        print(f"❌ Could not find {device_name} device in track")
        return None
    
    print(f"✅ Found {device_name} at device index {device_index}")
    
    return device_index

def test_device_parameters(track_index, device_index, device_name):
    """Test getting and setting parameters for a device."""
    print_divider(f"TESTING PARAMETERS FOR: {device_name}")
    
    if track_index is None or device_index is None:
        print("❌ Cannot test without track and device indices")
        return False
    
    # Get all parameters for the device
    params_result = send_command("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index
    })
    
    if params_result.get("status") != "success" or "parameters" not in params_result.get("result", {}):
        print(f"❌ Failed to get parameters for {device_name}")
        return False
    
    parameters = params_result["result"]["parameters"]
    print(f"✅ Successfully retrieved {len(parameters)} parameters for {device_name}")
    
    # Test setting a few key parameters
    test_parameters = []
    
    # Select a few parameters to test based on the device type
    for param in parameters:
        param_name = param.get("name", "")
        
        # Skip device on/off parameter
        if param_name == "Device On":
            continue
        
        # Add parameter to test list if it's not quantized or if it has value items
        if not param.get("is_quantized", False) or "value_items" in param:
            test_parameters.append(param)
            
            # Limit to 5 parameters for brevity
            if len(test_parameters) >= 5:
                break
    
    print(f"Selected {len(test_parameters)} parameters to test:")
    for param in test_parameters:
        print(f"  - {param.get('name')}: {param.get('value')} (min: {param.get('min')}, max: {param.get('max')})")
    
    # Test setting each parameter
    all_passed = True
    for param in test_parameters:
        param_name = param.get("name")
        param_min = param.get("min", 0)
        param_max = param.get("max", 1)
        
        # For quantized parameters with value items, test setting to each value item
        if param.get("is_quantized", False) and "value_items" in param:
            value_items = param.get("value_items", [])
            for i, item in enumerate(value_items):
                print(f"\nTesting {param_name} = {item} (index {i})")
                
                result = send_command("set_device_parameter", {
                    "track_index": track_index,
                    "device_index": device_index,
                    "parameter_name": param_name,
                    "value": i
                })
                
                if result.get("status") != "success":
                    print(f"❌ Failed to set {param_name} to {item}")
                    all_passed = False
                    continue
                
                # Verify the value was set correctly
                actual_value = result["result"]["value"]
                if abs(actual_value - i) < 0.01:
                    print(f"✅ Set {param_name} to {item} (value: {actual_value})")
                else:
                    print(f"⚠️ Set {param_name} to {item}, but actual value is {actual_value}")
                    all_passed = False
        
        # For continuous parameters, test min, middle, and max values
        else:
            test_values = [param_min, (param_min + param_max) / 2, param_max]
            for value in test_values:
                print(f"\nTesting {param_name} = {value}")
                
                result = send_command("set_device_parameter", {
                    "track_index": track_index,
                    "device_index": device_index,
                    "parameter_name": param_name,
                    "value": value
                })
                
                if result.get("status") != "success":
                    print(f"❌ Failed to set {param_name} to {value}")
                    all_passed = False
                    continue
                
                # Verify the value was set correctly
                actual_value = result["result"]["value"]
                if abs(actual_value - value) < 0.01:
                    print(f"✅ Set {param_name} to {value} (actual: {actual_value})")
                else:
                    print(f"⚠️ Set {param_name} to {value}, but actual value is {actual_value}")
                    all_passed = False
    
    return all_passed

def test_compressor(track_index):
    """Test parameter control for the Compressor device."""
    device_name = "Compressor"
    device_uri = "query:AudioFx#Compressor"
    
    device_index = load_device(track_index, device_uri, device_name)
    if device_index is None:
        return False
    
    return test_device_parameters(track_index, device_index, device_name)

def test_reverb(track_index):
    """Test parameter control for the Reverb device."""
    device_name = "Reverb"
    device_uri = "query:AudioFx#Reverb"
    
    device_index = load_device(track_index, device_uri, device_name)
    if device_index is None:
        return False
    
    return test_device_parameters(track_index, device_index, device_name)

def test_auto_filter(track_index):
    """Test parameter control for the Auto Filter device."""
    device_name = "Auto Filter"
    device_uri = "query:AudioFx#Auto%20Filter"
    
    device_index = load_device(track_index, device_uri, device_name)
    if device_index is None:
        return False
    
    return test_device_parameters(track_index, device_index, device_name)

def test_delay(track_index):
    """Test parameter control for the Delay device."""
    device_name = "Delay"
    device_uri = "query:AudioFx#Delay"
    
    device_index = load_device(track_index, device_uri, device_name)
    if device_index is None:
        return False
    
    return test_device_parameters(track_index, device_index, device_name)

def main():
    """Run all tests."""
    print_divider("ABLETON MCP AUDIO EFFECTS PARAMETER CONTROL TEST")
    
    # Check if server is running
    print("\nChecking connection to MCP server...")
    session_info = send_command("get_session_info")
    if session_info.get("status") != "success":
        print("❌ Error: Failed to connect to MCP server")
        return 1
    
    print("✅ Successfully connected to MCP server")
    
    # Run tests for each device type
    tests = [
        ("compressor", lambda: test_compressor(setup_test_track("Compressor Test Track"))),
        ("reverb", lambda: test_reverb(setup_test_track("Reverb Test Track"))),
        ("auto_filter", lambda: test_auto_filter(setup_test_track("Auto Filter Test Track"))),
        ("delay", lambda: test_delay(setup_test_track("Delay Test Track")))
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
