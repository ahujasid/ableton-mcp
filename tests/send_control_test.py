#!/usr/bin/env python3
"""
Send Control Testing Script for Ableton MCP.
This script tests the functionality of controlling send levels from tracks to return tracks.
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

def test_create_tracks_and_return_tracks():
    """Test creating tracks and return tracks for testing send controls."""
    print_divider("CREATING TEST TRACKS AND RETURN TRACKS")
    
    # Create a MIDI track
    result = send_command("create_midi_track")
    if result.get("status") != "success":
        print("❌ Failed to create MIDI track")
        return False
    
    midi_track_index = result["result"]["index"]
    print(f"✅ Created MIDI track at index {midi_track_index}")
    
    # Create a return track
    result = send_command("create_return_track")
    if result.get("status") != "success":
        print("❌ Failed to create return track")
        return False
    
    return_track_index = result["result"]["index"]
    print(f"✅ Created return track at index {return_track_index}")
    
    # Get session info to verify track counts
    session_info = send_command("get_session_info")
    if session_info.get("status") != "success":
        print("❌ Failed to get session info")
        return False
    
    track_count = session_info["result"]["track_count"]
    return_track_count = session_info["result"]["return_track_count"]
    print(f"Current track count: {track_count}")
    print(f"Current return track count: {return_track_count}")
    
    return {
        "midi_track_index": midi_track_index,
        "return_track_index": return_track_index,
        "track_count": track_count,
        "return_track_count": return_track_count
    }

def test_load_effect_on_return_track(track_info):
    """Test loading an effect onto a return track."""
    print_divider("TESTING LOADING EFFECT ON RETURN TRACK")
    
    track_count = track_info["track_count"]
    return_track_count = track_info["return_track_count"]
    
    # Calculate the track index for the return track
    # The index for return tracks is track_count + return_track_index
    return_track_index = track_info["return_track_index"]
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
    print("✅ Verified reverb device was loaded onto return track based on load_browser_item response")
    return True

def test_set_send_level(track_info):
    """Test setting send levels from a track to a return track."""
    print_divider("TESTING SEND LEVEL CONTROL")
    
    midi_track_index = track_info["midi_track_index"]
    return_track_index = track_info["return_track_index"]
    
    # The send index corresponds to the return track index in the return tracks list
    send_index = return_track_index
    
    # Test setting send level to 0.0 (minimum)
    result = send_command("set_send_level", {
        "track_index": midi_track_index,
        "send_index": send_index,
        "value": 0.0
    })
    
    if result.get("status") != "success":
        print("❌ Failed to set send level to 0.0")
        return False
    
    print("✅ Successfully set send level to 0.0")
    
    # Test setting send level to 0.5 (mid-range)
    result = send_command("set_send_level", {
        "track_index": midi_track_index,
        "send_index": send_index,
        "value": 0.5
    })
    
    if result.get("status") != "success":
        print("❌ Failed to set send level to 0.5")
        return False
    
    print("✅ Successfully set send level to 0.5")
    
    # Test setting send level to 1.0 (maximum)
    result = send_command("set_send_level", {
        "track_index": midi_track_index,
        "send_index": send_index,
        "value": 1.0
    })
    
    if result.get("status") != "success":
        print("❌ Failed to set send level to 1.0")
        return False
    
    print("✅ Successfully set send level to 1.0")
    
    return True

def main():
    """Run all tests."""
    print_divider("ABLETON MCP SEND CONTROL TEST")
    
    # Check connection to MCP server
    print("Checking connection to MCP server...")
    session_info = send_command("get_session_info")
    if session_info.get("status") != "success":
        print("❌ Failed to connect to MCP server")
        return 1
    
    print("✅ Successfully connected to MCP server")
    
    # Create tracks for testing
    track_info = test_create_tracks_and_return_tracks()
    if not track_info:
        print("❌ Failed to create test tracks")
        return 1
    
    # Load an effect on the return track
    effect_result = test_load_effect_on_return_track(track_info)
    
    # Test send level control
    send_result = test_set_send_level(track_info)
    
    # Print test summary
    print_divider("TEST SUMMARY")
    print(f"create_tracks_and_return_tracks: {'✅ PASSED' if track_info else '❌ FAILED'}")
    print(f"load_effect_on_return_track: {'✅ PASSED' if effect_result else '❌ FAILED'}")
    print(f"set_send_level: {'✅ PASSED' if send_result else '❌ FAILED'}")
    
    if track_info and effect_result and send_result:
        print("\n✅ All tests passed successfully!")
        return 0
    else:
        print("\n⚠️ Some tests failed. See details above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
