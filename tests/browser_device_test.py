#!/usr/bin/env python3
"""
Test script for Browser and Device Management functionality in Ableton MCP.
This script tests:
1. get_browser_tree
2. get_browser_items_at_path
3. load_instrument_or_effect
4. load_drum_kit
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

def test_get_browser_tree():
    """Test the get_browser_tree command."""
    print_divider("TESTING GET BROWSER TREE")
    
    # Test with default category_type
    result = send_command("get_browser_tree")
    if result.get("status") != "success":
        print("❌ Failed to get browser tree with default category_type")
        return False
    
    # Test with specific category_type
    for category_type in ["instruments", "audio_effects", "midi_effects", "drums", "sounds"]:
        result = send_command("get_browser_tree", {"category_type": category_type})
        if result.get("status") != "success":
            print(f"❌ Failed to get browser tree for category_type: {category_type}")
            return False
        print(f"✅ Successfully retrieved browser tree for: {category_type}")
    
    return True

def test_get_browser_items_at_path():
    """Test the get_browser_items_at_path command."""
    print_divider("TESTING GET BROWSER ITEMS AT PATH")
    
    # Test with root paths
    root_paths = ["instruments", "audio_effects", "midi_effects", "drums", "sounds"]
    for path in root_paths:
        result = send_command("get_browser_items_at_path", {"path": path})
        if result.get("status") != "success":
            print(f"❌ Failed to get browser items at path: {path}")
            return False
        print(f"✅ Successfully retrieved browser items at path: {path}")
    
    # Try to find a valid subpath for audio effects
    result = send_command("get_browser_items_at_path", {"path": "audio_effects"})
    if result.get("status") == "success" and "items" in result.get("result", {}):
        items = result["result"]["items"]
        if items and len(items) > 0:
            # Find a folder to navigate into
            for item in items:
                if item.get("is_folder", False):
                    subpath = f"audio_effects/{item['name']}"
                    sub_result = send_command("get_browser_items_at_path", {"path": subpath})
                    if sub_result.get("status") == "success":
                        print(f"✅ Successfully retrieved browser items at subpath: {subpath}")
                        break
    
    return True

def test_load_instrument_or_effect():
    """Test the load_instrument_or_effect command."""
    print_divider("TESTING LOAD INSTRUMENT OR EFFECT")
    
    # First, create a MIDI track to load the instrument/effect onto
    track_result = send_command("create_midi_track")
    if track_result.get("status") != "success" or "index" not in track_result.get("result", {}):
        print("❌ Failed to create a MIDI track for testing")
        return False
    
    track_index = track_result["result"]["index"]
    print(f"✅ Created MIDI track at index {track_index}")
    
    # Rename the track for clarity
    rename_result = send_command("set_track_name", {
        "track_index": track_index,
        "name": "Device Test Track"
    })
    if rename_result.get("status") == "success":
        print("✅ Renamed track to 'Device Test Track'")
    
    # Try to load an EQ Eight effect
    # IMPORTANT: The server actually sends "load_browser_item" to the Remote Script,
    # not "load_instrument_or_effect"
    eq_result = send_command("load_browser_item", {
        "track_index": track_index,
        "item_uri": "query:AudioFx#EQ%20Eight"
    })
    
    if eq_result.get("status") == "success":
        print("✅ Successfully loaded EQ Eight onto the track")
        return True
    else:
        print(f"❌ Failed to load EQ Eight. Error: {eq_result.get('message', 'Unknown error')}")
        print("This functionality might not be implemented correctly.")
        return False

def test_load_drum_kit():
    """Test the load_drum_kit command."""
    print_divider("TESTING LOAD DRUM KIT")
    
    # First, create a MIDI track to load the drum kit onto
    track_result = send_command("create_midi_track")
    if track_result.get("status") != "success" or "index" not in track_result.get("result", {}):
        print("❌ Failed to create a MIDI track for testing")
        return False
    
    track_index = track_result["result"]["index"]
    print(f"✅ Created MIDI track at index {track_index}")
    
    # Rename the track for clarity
    rename_result = send_command("set_track_name", {
        "track_index": track_index,
        "name": "Drum Kit Test Track"
    })
    if rename_result.get("status") == "success":
        print("✅ Renamed track to 'Drum Kit Test Track'")
    
    # Try to load a drum rack and kit
    # IMPORTANT: The server actually sends a sequence of commands to the Remote Script,
    # not a single "load_drum_kit" command
    
    # Step 1: Load the drum rack
    rack_uri = "query:Drums#Drum%20Rack"  # URI for Drum Rack
    rack_result = send_command("load_browser_item", {
        "track_index": track_index,
        "item_uri": rack_uri
    })
    
    if rack_result.get("status") != "success":
        print(f"❌ Failed to load drum rack. Error: {rack_result.get('message', 'Unknown error')}")
        return False
    
    print("✅ Successfully loaded Drum Rack onto the track")
    
    # Step 2: Get the drum kit items at a specific path
    kit_path = "drums"  # Path to drum kits
    kit_result = send_command("get_browser_items_at_path", {
        "path": kit_path
    })
    
    if kit_result.get("status") != "success":
        print(f"❌ Failed to get drum kits. Error: {kit_result.get('message', 'Unknown error')}")
        return False
    
    # Step 3: Find a loadable drum kit
    kit_items = kit_result.get("result", {}).get("items", [])
    loadable_kits = [item for item in kit_items if item.get("is_loadable", False)]
    
    if not loadable_kits:
        print(f"❌ No loadable drum kits found at path '{kit_path}'")
        return False
    
    # Step 4: Load the first loadable kit
    kit_uri = loadable_kits[0].get("uri")
    kit_name = loadable_kits[0].get("name")
    
    load_result = send_command("load_browser_item", {
        "track_index": track_index,
        "item_uri": kit_uri
    })
    
    if load_result.get("status") == "success":
        print(f"✅ Successfully loaded drum kit '{kit_name}' onto the track")
        return True
    else:
        print(f"❌ Failed to load drum kit. Error: {load_result.get('message', 'Unknown error')}")
        return False

def main():
    """Run all tests."""
    print_divider("ABLETON MCP BROWSER & DEVICE MANAGEMENT TEST")
    
    # Check if server is running
    print("\nChecking connection to MCP server...")
    session_info = send_command("get_session_info")
    if session_info.get("status") != "success":
        print("❌ Error: Failed to connect to MCP server")
        return 1
    
    print("✅ Successfully connected to MCP server")
    
    # Run tests
    tests = [
        ("get_browser_tree", test_get_browser_tree),
        ("get_browser_items_at_path", test_get_browser_items_at_path),
        ("load_instrument_or_effect", test_load_instrument_or_effect),
        ("load_drum_kit", test_load_drum_kit)
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
