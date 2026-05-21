import socket
import json
import sys

def test_time_range(start_time, end_time, track_indices):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    try:
        s.connect(('localhost', 9877))
        command = {
            'type': 'get_clips_in_time_range',
            'start_time': start_time,
            'end_time': end_time,
            'track_indices': track_indices
        }
        print(f"Sending command: {json.dumps(command, indent=2)}")
        s.sendall((json.dumps(command) + "\n").encode('utf-8'))
        
        # Read response (delimited by newline in Remote Script)
        response_data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response_data += chunk
            if b"\n" in chunk or len(chunk) < 4096:
                break
                
        decoded = response_data.decode('utf-8').strip()
        print("\n--- Response ---")
        try:
            parsed = json.loads(decoded)
            print(json.dumps(parsed, indent=2))
        except Exception:
            print(decoded)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        s.close()

if __name__ == "__main__":
    # Allow command line args: python test_time_range.py <start> <end> <track_indices_json>
    # E.g. python test_time_range.py 0 16 "[0,1]"
    start = 0.0
    end = 16.0
    tracks = [0, 1]
    
    if len(sys.argv) > 1:
        start = float(sys.argv[1])
    if len(sys.argv) > 2:
        end = float(sys.argv[2])
    if len(sys.argv) > 3:
        tracks = json.loads(sys.argv[3])
        
    test_time_range(start, end, tracks)
