#!/usr/bin/env python3
"""
Volume Control Test Script for Ableton MCP

This script demonstrates the volume control functionality of the Ableton MCP system.
It creates a track, sets its volume to different values, and displays the volume in dB.
"""

import socket
import json
import time
import sys

# Connection settings
HOST = "localhost"
PORT = 9877

def send_command(sock, command_type, params=None):
    """Send a command to the Ableton MCP server and return the response"""
    if params is None:
        params = {}
    
    command = {
        "type": command_type,
        "params": params
    }
    
    # Send the command
    sock.sendall(json.dumps(command).encode('utf-8'))
    
    # Receive the response
    response_data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response_data += chunk
        
        # Check if we have a complete JSON response
        try:
            json.loads(response_data.decode('utf-8'))
            break  # If we can parse it, we have the full response
        except json.JSONDecodeError:
            continue  # Keep receiving if the JSON is incomplete
    
    # Parse and return the response
    response = json.loads(response_data.decode('utf-8'))
    return response

def main():
    """Main function to test volume control functionality"""
    try:
        # Connect to the Ableton MCP server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
        print(f"Connected to Ableton MCP server at {HOST}:{PORT}")
        
        # Get session info
        response = send_command(sock, "get_session_info")
        if response["status"] != "success":
            print(f"Error getting session info: {response.get('message', 'Unknown error')}")
            return
        
        print("Session info:")
        print(f"  Tempo: {response['result']['tempo']} BPM")
        print(f"  Time signature: {response['result']['signature_numerator']}/{response['result']['signature_denominator']}")
        print(f"  Track count: {response['result']['track_count']}")
        
        # Create a new MIDI track
        response = send_command(sock, "create_midi_track")
        if response["status"] != "success":
            print(f"Error creating MIDI track: {response.get('message', 'Unknown error')}")
            return
        
        track_index = response["result"]["index"]
        track_name = response["result"]["name"]
        print(f"Created new MIDI track: {track_name} (index: {track_index})")
        
        # Set the track name
        new_name = "Volume Test Track"
        response = send_command(sock, "set_track_name", {
            "track_index": track_index,
            "name": new_name
        })
        if response["status"] != "success":
            print(f"Error setting track name: {response.get('message', 'Unknown error')}")
            return
        
        print(f"Renamed track to: {new_name}")
        
        # Get the current track info to see the default volume
        response = send_command(sock, "get_track_info", {
            "track_index": track_index
        })
        if response["status"] != "success":
            print(f"Error getting track info: {response.get('message', 'Unknown error')}")
            return
        
        current_volume = response["result"]["volume"]
        print(f"Current volume: {current_volume}")
        
        # Test different volume levels
        print("\nTesting volume control:")
        
        # Test volume levels
        volume_levels = [
            {"value": 0.0, "description": "Muted (0%)"},
            {"value": 0.425, "description": "Half volume (-6dB)"},
            {"value": 0.85, "description": "Unity gain (0dB)"},
            {"value": 1.0, "description": "Maximum (+6dB)"}
        ]
        
        for level in volume_levels:
            # Set the volume
            response = send_command(sock, "set_track_volume", {
                "track_index": track_index,
                "value": level["value"]
            })
            if response["status"] != "success":
                print(f"Error setting volume: {response.get('message', 'Unknown error')}")
                continue
            
            # Get the actual volume value and dB representation
            volume = response["result"]["volume"]
            volume_db = response["result"]["volume_db"]
            
            # Format the dB value for display
            if volume_db == float('-inf'):
                volume_db_str = "-∞ dB"
            else:
                volume_db_str = f"{volume_db:.1f} dB"
            
            print(f"  Set volume to {level['description']}: {volume:.3f} ({volume_db_str})")
            
            # Small delay to see the change in Ableton
            time.sleep(1)
        
        print("\nVolume control test completed successfully!")
        
    except ConnectionRefusedError:
        print(f"Error: Could not connect to Ableton MCP server at {HOST}:{PORT}")
        print("Make sure Ableton Live is running with the AbletonMCP Remote Script loaded.")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        if 'sock' in locals():
            sock.close()

if __name__ == "__main__":
    main()
