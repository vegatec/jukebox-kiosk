import http.server
import socketserver
import json
import subprocess
import os
import time
import threading

# Strip Snap's LD_LIBRARY_PATH so GTK subprocesses don't hit libc conflicts
_clean_env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}

# --- Configuration ---
PORT = 8000
VOLUME_COMMAND = "pactl"
VOLUME_STEP = 5 
SINK_IDENTIFIER = "0" 

# Global state to hold the latest known volume. This is accessed by all threads.
# We use a Lock to ensure thread-safe updates.
global_volume_state = {"level": 0}
volume_lock = threading.Lock()

# --- Utility Functions ---

def get_current_volume():
    """Executes pactl to get the current volume percentage from the system."""
    with volume_lock:
        try:
            result = subprocess.run(
                [VOLUME_COMMAND, "list", "sinks"],
                check=True,
                capture_output=True,
                text=True
            )
            output = result.stdout
            
            # Simple parsing: look for lines like 'Volume: 0:  80% / 0.80'
            for line in output.split('\n'):
                if "Volume:" in line and "Base Volume:" not in line:
                    volume_parts = line.split('/')
                    for part in volume_parts:
                        if '%' in part:
                            # Extract the number and convert to integer
                            level = int(part.strip().split()[0].replace('%', ''))
                            global_volume_state['level'] = level
                            return level
            
            # Fallback if parsing fails
            return global_volume_state['level']

        except Exception as e:
            print(f"Error fetching volume: {e}")
            return global_volume_state['level']


def execute_volume_change(direction):
    """Executes the pactl command to change the volume and updates global state."""
    if direction == 'raise':
        current = get_current_volume()
        if current >= 100:
            return True, "Volume is already at 100%."
        target = min(current + VOLUME_STEP, 100)
        volume_change = f"{target}%"
    else:
        volume_change = f"-{VOLUME_STEP}%"

    try:
        pactl_args = [
            VOLUME_COMMAND,
            "set-sink-volume",
            SINK_IDENTIFIER,
            volume_change
        ]

        subprocess.run(pactl_args, check=True, capture_output=True, text=True)

        # After changing, immediately fetch the new accurate volume level and update state
        new_level = get_current_volume()

	# Call the external script and pass the volume as an argument
        subprocess.Popen(["python3", "volume-indicator.py", str(new_level)], env=_clean_env)

        return True, f"Volume adjusted to {new_level}%."

    except FileNotFoundError:
        return False, f"Error: '{VOLUME_COMMAND}' not found."
    except subprocess.CalledProcessError as e:
        return False, f"Error executing pactl: {e.stderr.strip()}"
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"


def execute_volume_set(percentage):
    """Sets the volume to an exact percentage (1-100) and updates global state."""
    if not isinstance(percentage, (int, float)) or not (0 <= percentage <= 100):
        return False, "Invalid level. Must be a number between 0 and 100."

    level = int(percentage)
    try:
        subprocess.run(
            [VOLUME_COMMAND, "set-sink-volume", SINK_IDENTIFIER, f"{level}%"],
            check=True, capture_output=True, text=True
        )

        new_level = get_current_volume()
        subprocess.Popen(["python3", "volume-indicator.py", str(new_level)], env=_clean_env)

        return True, f"Volume set to {new_level}%."

    except FileNotFoundError:
        return False, f"Error: '{VOLUME_COMMAND}' not found."
    except subprocess.CalledProcessError as e:
        return False, f"Error executing pactl: {e.stderr.strip()}"
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"


# Initialize global state with current volume
get_current_volume() 
print(f"Initial Volume: {global_volume_state['level']}%")

# --- Request Handler ---

class SSEVolumeHandler(http.server.SimpleHTTPRequestHandler):
    
    def _set_headers(self, status_code=200, content_type='application/json'):
        """Helper function to set common response and CORS headers."""
        self.send_response(status_code)
        self.send_header('Content-type', content_type)
        # CORS Headers to allow cross-origin requests
        self.send_header('Access-Control-Allow-Origin', '*') 
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS') 
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        """Handles the pre-flight request for CORS."""
        self._set_headers(200)

    # --- SSE Endpoint (GET /events) ---
    def do_GET(self):
        """
        Handles the SSE connection. This runs in its own thread due to the 
        ThreadingMixIn, preventing it from blocking the server.
        """
        if self.path == '/events':
            # 1. Set SSE Headers
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*') 
            self.end_headers()
            
            last_sent_level = global_volume_state['level']
            print(f"Client connected for SSE in thread {threading.get_ident()}")
            
            # Continuous Loop for Broadcasting
            while True:
                try:
                    # Thread-safe read of the current volume level
                    with volume_lock:
                        current_level = global_volume_state['level']
                    
                    if current_level != last_sent_level:
                        # 2. Format SSE Data (data: JSON_STRING\n\n)
                        sse_data = {
                            "volume": current_level,
                            "timestamp": time.time()
                        }
                        message = f"data: {json.dumps(sse_data)}\n\n"
                        
                        # 3. Send Data
                        self.wfile.write(message.encode('utf-8'))
                        self.wfile.flush() # Essential: forces data transmission
                        last_sent_level = current_level
                        print(f"Sent volume update: {current_level}%")

                    # Keep polling interval short for near real-time updates
                    time.sleep(0.1) 

                except Exception as e:
                    # Connection closed by client or network error
                    print(f"SSE connection closed: {e}")
                    break
        elif self.path == '/qr':
            subprocess.Popen(["python3", "qr-indicator.py"], env=_clean_env)
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "success", "message": "QR code displayed"}).encode('utf-8'))
        else:
            # Handle other GET requests
            #self.send_error(404, "File Not Found")
            # FALLBACK: Use the built-in logic to serve files (app-launcher.html)
            super().do_GET()

    # --- Volume Control Endpoint (POST /) ---
    def do_POST(self):
        """Handle POST requests to change volume."""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            action = data.get('action')

            if action in ['raise', 'lower']:
                # The execution updates the global state
                success, message = execute_volume_change(action)

                current_level = global_volume_state['level']

                if success:
                    response = {"status": "success", "message": message, "volume": current_level}
                    self._set_headers(200)
                else:
                    response = {"status": "error", "message": message, "action": action}
                    self._set_headers(500)
            elif action == 'set':
                level = data.get('level')
                success, message = execute_volume_set(level)

                current_level = global_volume_state['level']

                if success:
                    response = {"status": "success", "message": message, "volume": current_level}
                    self._set_headers(200)
                else:
                    response = {"status": "error", "message": message, "action": action}
                    self._set_headers(400)
            else:
                response = {"status": "error", "message": "Invalid action. Must be 'raise', 'lower', or 'set'.", "action": action}
                self._set_headers(400)

        except json.JSONDecodeError:
            response = {"status": "error", "message": "Invalid JSON format."}
            self._set_headers(400)
        except Exception as e:
            response = {"status": "error", "message": f"Server error: {e}"}
            self._set_headers(500)

        self.wfile.write(json.dumps(response).encode('utf-8'))


# --- Server Implementation (The Concurrency Fix) ---

class ThreadingVolumeServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """
    A custom server class that inherits from both ThreadingMixIn and HTTPServer.
    This ensures every request (including the long-running SSE GET) is handled 
    in a separate thread, preventing the server from blocking.
    
    """
    pass

# --- Server Execution ---
if __name__ == "__main__":
    if os.name != 'posix' or os.uname().sysname != 'Linux':
        print("⚠️ WARNING: This script is designed for Linux with PulseAudio/PipeWire and may not run elsewhere.")
    
    # Use the threaded server class
    with ThreadingVolumeServer(("", PORT), SSEVolumeHandler) as httpd:
        print(f"\n✅ Server running (Threaded) on http://localhost:{PORT}")
        print("   - POST request to change volume: curl -X POST -d '{\"action\":\"raise\"}' http://localhost:8000")
        print("   - GET request for SSE events: curl -N http://localhost:8000/events")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped by user.")
            httpd.server_close()
