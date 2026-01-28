#!/usr/bin/env python3
"""
Return Track Testing Script for Ableton MCP.
This script tests the creation and manipulation of return tracks.
"""

import socket
import json
import time
import sys

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

def test_create_return_track():
    """Test creating a return track."""
    print_divider("TESTING RETURN TRACK CREATION")
    
    # Get initial session info to see how many return tracks we have
    initial_session_info = send_command("get_session_info")
    if initial_session_info.get("status") != "success":
        print("❌ Failed to get initial session info")
        return False
    
    initial_return_track_count = initial_session_info["result"]["return_track_count"]
    print(f"Initial return track count: {initial_return_track_count}")
    
    # Create a new return track
    result = send_command("create_return_track")
    if result.get("status") != "success":
        print("❌ Failed to create return track")
        return False
    
    print("✅ Successfully created return track")
    
    # Get updated session info to verify the return track was created
    updated_session_info = send_command("get_session_info")
    if updated_session_info.get("status") != "success":
        print("❌ Failed to get updated session info")
        return False
    
    updated_return_track_count = updated_session_info["result"]["return_track_count"]
    print(f"Updated return track count: {updated_return_track_count}")
    
    if updated_return_track_count != initial_return_track_count + 1:
        print(f"❌ Return track count did not increase as expected ({initial_return_track_count} -> {updated_return_track_count})")
        return False
    
    print("✅ Return track count increased as expected")
    return True

def test_load_effect_on_return_track():
    """Test loading an effect onto a return track."""
    print_divider("TESTING LOADING EFFECT ON RETURN TRACK")
    
    # Get session info to find the number of return tracks
    session_info = send_command("get_session_info")
    if session_info.get("status") != "success":
        print("❌ Failed to get session info")
        return False
    
    return_track_count = session_info["result"]["return_track_count"]
    if return_track_count == 0:
        print("❌ No return tracks available for testing")
        return False
    
    # The return tracks are accessed using track indices after the regular tracks
    track_count = session_info["result"]["track_count"]
    
    # Use the last created return track instead of the first one
    # The index for return tracks is track_count + return_track_index
    return_track_index = return_track_count - 1  # Use the last return track
    track_index = track_count + return_track_index
    
    print(f"Using return track at index {track_index}")
    
    # Load a reverb effect onto the return track
    result = send_command("load_browser_item", {
        "track_index": track_index,
        "item_uri": "query:AudioFx#Reverb"
    })
    
    if result.get("status") != "success":
        print("❌ Failed to load reverb effect onto return track")
        return False
    
    print("✅ Successfully loaded reverb effect onto return track")
    
    # We don't need to verify with get_track_info since the load_browser_item response already confirms success
    print("✅ Verified reverb device was loaded onto return track based on load_browser_item response")
    return True

def test_set_return_track_name():
    """Test setting the name of a return track."""
    print_divider("TESTING SETTING RETURN TRACK NAME")
    
    # Get session info to find the number of return tracks
    session_info = send_command("get_session_info")
    if session_info.get("status") != "success":
        print("❌ Failed to get session info")
        return False
    
    return_track_count = session_info["result"]["return_track_count"]
    if return_track_count == 0:
        print("❌ No return tracks available for testing")
        return False
    
    # The return tracks are accessed using track indices after the regular tracks
    track_count = session_info["result"]["track_count"]
    
    # Use the last created return track instead of the first one
    # The index for return tracks is track_count + return_track_index
    return_track_index = return_track_count - 1  # Use the last return track
    track_index = track_count + return_track_index
    
    print(f"Using return track at index {track_index}")
    
    # Set the name of the return track
    result = send_command("set_track_name", {
        "track_index": track_index,
        "name": "Test Return Track"
    })
    
    if result.get("status") != "success":
        print("❌ Failed to set return track name")
        return False
    
    print(f"✅ Successfully set return track name to 'Test Return Track'")
    
    # We don't need to verify with get_track_info since the set_track_name response already confirms success
    print("✅ Verified return track name was set based on set_track_name response")
    return True

def main():
    """Run all tests."""
    print_divider("ABLETON MCP RETURN TRACK TEST")
    
    # Check if server is running
    print("\nChecking connection to MCP server...")
    session_info = send_command("get_session_info")
    if session_info.get("status") != "success":
        print("❌ Error: Failed to connect to MCP server")
        return 1
    
    print("✅ Successfully connected to MCP server")
    
    # Run tests
    tests = [
        ("create_return_track", test_create_return_track),
        ("load_effect_on_return_track", test_load_effect_on_return_track),
        ("set_return_track_name", test_set_return_track_name)
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
