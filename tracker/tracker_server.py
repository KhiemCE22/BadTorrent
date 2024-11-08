import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from client_list import ClientList
import bencodepy
import threading
import logging
import argparse
import socket
import os
import sys
from tabulate import tabulate
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import logging_config
def decode_info_hash(url_encoded_string):
    decoded_string = bytearray()
    i = 0
    while i < len(url_encoded_string):
        if url_encoded_string[i] == '%':
            if i + 2 < len(url_encoded_string):
                hex_value = url_encoded_string[i + 1:i + 3]
                try:
                    decoded_byte = int(hex_value, 16)
                    decoded_string.append(decoded_byte)
                except ValueError:
                    raise ValueError(f"Invalid hex value: {hex_value}")
                i += 3
            else:
                break
        else:
            decoded_string.append(ord(url_encoded_string[i]))
            i += 1

    if len(decoded_string) != 20:
        raise ValueError(f"Decoded string is not a valid SHA1 hash length: {decoded_string.hex()}")

    return bytes(decoded_string).hex()


# Constants
DEFAULT_PORT = 8000
TRACKER_INTERVAL = 1800  # Time between tracker updates in seconds

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TrackerServer(BaseHTTPRequestHandler):
    client_list = ClientList()
    lock = threading.Lock()

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        info_hash = None
        for param in query.split('&'):
            if param.startswith('info_hash='):
                info_hash = param.split('=')[1]
                break
        params = urllib.parse.parse_qs(query)
        if info_hash is not None:
            params['info_hash'] = [info_hash]
        if self.path.startswith("/announce"):
            self.handle_announce(params)
        elif self.path.startswith("/scrape"):
            self.handle_scrape(params)
        elif self.path.startswith("/ping"):
            self.handle_ping(params)
        else:
            self.send_error(404, "Unknown request path")

    def handle_announce(self, params):
        info_hash = params.get("info_hash", [None])[0]
        peer_id = params.get("peer_id", [None])[0]
        port = int(params.get("port", [None])[0]) if params.get("port") else None
        uploaded = int(params.get("uploaded", [0])[0]) if params.get("uploaded") else None
        downloaded = int(params.get("downloaded", [0])[0]) if params.get("downloaded") else None
        left = int(params.get("left", [0])[0]) if params.get("left") else None
        event = params.get("event", [None])[0]

        if peer_id is None or port is None:
            self.send_error(400, "Missing required parameters")
            return

        client_ip = self.client_address[0]

        with self.lock:
            if event == "started":
                if info_hash:
                    try:
                        info_hash_hex = decode_info_hash(info_hash)
                        info_hash = bytes.fromhex(info_hash_hex)
                    except Exception as e:
                        self.send_error(400, "Invalid info_hash encoding")
                        logger.error(f"Encoding error: {e}")
                        return
                    self.client_list.update_peer(info_hash, peer_id, client_ip, port, uploaded, downloaded, left, event)
            elif event == "stopped":
                if info_hash:
                    try:
                        info_hash_hex = decode_info_hash(info_hash)
                        info_hash = bytes.fromhex(info_hash_hex)
                    except Exception as e:
                        self.send_error(400, "Invalid info_hash encoding")
                        logger.error(f"Encoding error: {e}")
                        return
                    self.client_list.remove_peer(info_hash, peer_id)
                    logger.info(f"Peer {peer_id} has been removed from {info_hash.hex()} list")
                else:
                    self.client_list.remove_peer_from_all(peer_id)
                    logger.info(f"Peer {peer_id} has been removed from all torrents")

            elif event == "completed":
                if info_hash:
                    try:
                        info_hash_hex = decode_info_hash(info_hash)
                        info_hash = bytes.fromhex(info_hash_hex)
                    except Exception as e:
                        self.send_error(400, "Invalid info_hash encoding")
                        logger.error(f"Encoding error: {e}")
                        return
                    self.client_list.update_peer(info_hash, peer_id, client_ip, port, uploaded, downloaded, left, event)

        if info_hash:
            # Lấy danh sách peers và loại bỏ peer của client
            peers = self.client_list.get_peers(info_hash, peer_id)
            response = {
                "interval": TRACKER_INTERVAL,
                "peers": peers,
                "complete": self.client_list.get_complete_count(info_hash),
                "incomplete": self.client_list.get_incomplete_count(info_hash),
            }

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(bencodepy.encode(response))
        else:
            response_data = { "failure reason": "no info_hash parameter suppliede" }
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(bencodepy.encode(response_data))

    def handle_scrape(self, params):
        info_hash = params.get("info_hash", [None])[0]
        if info_hash is not None:
            try:
                info_hash_hex = decode_info_hash(info_hash)
                info_hash = bytes.fromhex(info_hash_hex)
            except Exception as e:
                self.send_error(400, "Invalid info_hash encoding")
                logger.error(f"Encoding error: {e}")
                return

        scrape_data = self.client_list.get_scrape_info(info_hash)

        response = {b'files': scrape_data}

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(bencodepy.encode(response))

    def handle_ping(self, params):
        peer_ip = params.get("peer_ip", [None])[0]
        peer_port = int(params.get("peer_port", [None])[0]) if params.get("peer_port") else None

        if peer_ip is None or peer_port is None:
            self.send_error(400, "Missing required parameters")
            return

        try:
            with socket.create_connection((peer_ip, peer_port), timeout=5) as sock:
                sock.sendall(b'ping')
                response = sock.recv(1024)
                if response == b'pong':
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"Client is online")
                else:
                    self.send_response(500)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"Unexpected response from client")
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Client is offline")
            logger.error(f"Error pinging client: {e}")

def ping_all_clients(client_list):
    results = []
    with threading.Lock():
        all_clients = client_list.get_all_clients()
        if not all_clients:
            logger.info("No clients to ping")
            return results
        for client in all_clients:
            peer_ip = client["ip"]
            peer_id = client["id"]
            try:
                with socket.create_connection((peer_ip, 6884), timeout=5) as sock:
                    sock.sendall(b'ping')
                    response = sock.recv(1024)
                    if response == b'pong':
                        results.append([peer_id, peer_ip, "online"])
                        logger.info(f"Client {peer_id} ({peer_ip}) is online")
                    else:
                        results.append([peer_id, peer_ip, "offline"])
                        logger.info(f"Client {peer_id} ({peer_ip}) is offline")
            except Exception as e:
                results.append([peer_id, peer_ip, "error"])
                logger.error(f"Error pinging client {peer_id} ({peer_ip}): {e}")
    return results

def run(server_class=ThreadingHTTPServer, handler_class=TrackerServer, port=DEFAULT_PORT, stop_event=None):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    ip_address = socket.gethostbyname(socket.gethostname())
    logger.info(f"Starting tracker server on {ip_address}:{port} with multi-threading support")
    print(f"Starting tracker server on {ip_address}:{port} with multi-threading support")
    def check_stop_event():
        while not stop_event.is_set():
            pass
        httpd.shutdown()

    stop_thread = threading.Thread(target=check_stop_event)
    stop_thread.start()

    httpd.serve_forever()
    httpd.server_close()
    logger.info("Tracker server stopped.")
    print("Tracker server stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the tracker server.")
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Port to run the tracker server on')
    args = parser.parse_args()

    stop_event = threading.Event()
    server_thread = threading.Thread(target=run, args=(ThreadingHTTPServer, TrackerServer, args.port, stop_event))
    server_thread.start()

    # Enter interactive mode
    try:
        while True:
            command = input(">>> ").split()
            if not command:
                continue
            if command[0] == 'exit':
                stop_event.set()
                server_thread.join()
                break
            elif command[0] == 'ping':
                try:
                    results = ping_all_clients(TrackerServer.client_list)
                    if results:
                        print(tabulate(results, headers=["Peer ID", "IP Address", "Status"], tablefmt="grid"))
                except Exception as e:
                    print(f"Error executing ping_all command: {e}")
            else:
                print("Unknown command or incorrect parameters")
    except KeyboardInterrupt:
        stop_event.set()
        server_thread.join()
        print("\nExiting tracker CLI.")