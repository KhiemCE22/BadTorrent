import requests
import bencodepy
import random
import string
import struct
import os
import sys
import socket
import threading
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import hashlib
import logging
from tabulate import tabulate
from p2p.download_manager import DownloadingManager
from p2p.peer import Peer
from p2p.upload_manager import UploadingManager
from p2p.piece import Piece

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _generate_peer_id(length=20):
    """Generate a random peer ID."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

class ClientNode:
    def __init__(self):
        self.tracker_url = None
        self.tracker_id = None
        self.torrent_file = None
        self.torrent_data = None
        self.has_announced = False  # Track if the client has announced to the tracker
        self.peer_id = _generate_peer_id()
        self.download_port = 6881
        self.upload_port = 6882
        self.announce_port = 6883
        self.downloadding_manager = None
        self.uploading_manager = None
        self.stop_event = threading.Event()  # Event to signal the server thread to stop
        self.seeding_files = {}  # Dictionary to store seeding files info
        self.announced_trackers = set()  # Set to store announced trackers

    def _load_torrent_file(self, torrent_file):
        """Load and parse the .torrent file."""
        def decode_keys(data):
            """Recursively decode keys in a dictionary."""
            if isinstance(data, dict):
                return {k.decode('utf-8'): decode_keys(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [decode_keys(item) for item in data]
            else:
                return data

        with open(torrent_file, 'rb') as f:
            torrent_data = bencodepy.decode(f.read())
        self.torrent_file = torrent_file
        torrent_data = decode_keys(torrent_data)
        self.tracker_url = torrent_data['announce']
        self.torrent_data = torrent_data
        return torrent_data, torrent_data['info']

    def announce(self, info_hash, port, event='started'):
        """Send announce request to tracker and update client state."""
        info = self.torrent_data['info']
        if 'length' in info:
            file_length = info['length']
        elif 'files' in info:
            file_length = sum(file['length'] for file in info['files'])
        else:
            raise KeyError("Neither 'length' nor 'files' key found in torrent info dictionary.")

        params = {
            'info_hash': info_hash,
            'peer_id': self.peer_id,
            'port': port,
            'uploaded': 0,
            'downloaded': 0,
            'left': file_length,  # Set the length of the file from the torrent data
            'event': event,
            'compact': 1
        }
        if self.tracker_id:
            params['trackerid'] = self.tracker_id

        try:
            response = requests.get(self.tracker_url, params=params)
            response.raise_for_status()
            response_data = bencodepy.decode(response.content)
            self.has_announced = True  # Confirm that the client has announced to the tracker
            self.announced_trackers.add(self.tracker_url)  # Add the tracker to the announced trackers set
            if b'failure reason' in response_data:
                logging.error(f"Tracker error: {response_data[b'failure reason'].decode()}")
                return []
            if b'warning message' in response_data:
                logging.warning(f"Tracker warning: {response_data[b'warning message'].decode()}")
            if b'tracker id' in response_data:
                self.tracker_id = response_data[b'tracker id'].decode()
            peers = response_data.get(b'peers', [])
            if isinstance(peers, bytes):
                # Handle compact format
                peers = self._parse_compact_peers(peers)
            return peers
        except requests.RequestException as e:
            logging.error(f"Error during announce request: {e}")
            return []

    def download_torrent(self, torrent_file, port=None, download_dir=None):
        """Handle the download process of a torrent."""
        torrent_data, info = self._load_torrent_file(torrent_file)
        info_hash = hashlib.sha1(bencodepy.encode(info)).digest()
        logging.info(f"Starting download from {self.tracker_url} on port {port or self.download_port}...")

        peers = self.announce(info_hash, port or self.download_port)
        logging.info(f"Found peers: {peers}")
        peers = [Peer(peer['ip'], peer['port']) for peer in peers]

        # Create the download directory if it doesn't exist
        if download_dir and not os.path.exists(download_dir):
            os.makedirs(download_dir)

        # Get the piece length and the total length of the file
        piece_length = info['piece length']
        total_length = sum(file['length'] for file in info['files']) if 'files' in info else info['length']
        pieces = []

        # Create Piece objects for each piece in the torrent
        for i in range(0, total_length, piece_length):
            length = min(piece_length, total_length - i)
            piece_hash = info['pieces'][i // piece_length * 20:(i // piece_length + 1) * 20]
            pieces.append(Piece(i // piece_length, length, piece_hash))

        # Ensure info['name'] is a string
        file_name = info['name']
        if isinstance(file_name, bytes):
            file_name = file_name.decode('utf-8')

        # Determine the file path to save the downloaded file
        if 'files' in info:
            # Multi-file mode
            file_path = download_dir if download_dir else os.getcwd()
        else:
            # Single-file mode
            file_path = os.path.join(download_dir if download_dir else os.getcwd(), file_name)

        peer_id_encoded = self.peer_id.encode("utf-8")
        # Start the download process
        with tqdm(total=total_length, unit='B', unit_scale=True, desc=file_name) as pbar:
            self.downloading_manager = DownloadingManager(progress_bar=pbar)  # Pass progress bar
            if self.downloading_manager.start_download(peers, pieces, info_hash, peer_id_encoded, file_path, info['files'] if 'files' in info else None):
                self.announce(info_hash, port or self.download_port, event='completed')
                logging.info(f"Download completed. Files saved to {file_path}")
            else:
                logging.error("Download failed.")

    def seed_torrent(self, torrent_file, complete_file, port=None, upload_rate=None):
        """Handle the seeding process of a torrent."""
        torrent_data, info = self._load_torrent_file(torrent_file)
        info_hash = hashlib.sha1(bencodepy.encode(info)).digest()
        logging.info(f"Starting seeding to {self.tracker_url} on port {port or self.upload_port} with upload rate {upload_rate}...")
        peers = self.announce(info_hash, port or self.upload_port, event='completed')
        logging.info(f"Seeding to peers: {peers}")
        peers = [Peer(peer['ip'], peer['port']) for peer in peers]
        
        # Get the piece length and the total length of the file
        piece_length = info['piece length']
        total_length = sum(file['length'] for file in info['files']) if 'files' in info else info['length']
        pieces = []
        
        # Create Piece objects for each piece in the torrent
        for i in range(0, total_length, piece_length):
            length = min(piece_length, total_length - i)
            piece_hash = info['pieces'][i // piece_length * 20:(i // piece_length + 1) * 20]
            pieces.append(Piece(i // piece_length, length, piece_hash))
        
        # Initialize the UploadingManager
        if 'files' in info:
            # Multi-file mode
            file_paths = [os.path.join(complete_file, *[part.decode('utf-8') if isinstance(part, bytes) else part for part in file['path']]) for file in info['files']]
            total_lengths = [file['length'] for file in info['files']]
        else:
            # Single-file mode
            file_paths = [complete_file]
            total_lengths = [total_length]
        
        self.uploading_manager = UploadingManager(pieces, self.peer_id.encode("utf-8"), info_hash, file_paths, total_lengths)
        
        # Start a server to accept incoming connections from peers
        server_thread = threading.Thread(target=self._start_seeding_server, args=(port or self.upload_port,))
        server_thread.start()
        self.seeding_files[torrent_file] = (file_paths, self.tracker_url)  # Add to seeding files

    def _start_seeding_server(self, port):
        """Start a server to accept incoming connections from peers."""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Set the SO_REUSEADDR option
        server_socket.bind(('0.0.0.0', port))
        server_socket.listen(5)
        logging.info(f"Seeding server started on port {port}")

        while not self.stop_event.is_set():  # Check the stop event
            try:
                server_socket.settimeout(1)  # Set a timeout to periodically check the stop event
                client_socket, client_address = server_socket.accept()
                logging.info(f"Accepted connection from {client_address}")
                peer = Peer(client_address[0], client_address[1])
                self.uploading_manager.add_peer(peer, client_socket)
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Error accepting connection: {e}")
                break

        server_socket.close()
        logging.info("Seeding server stopped.")

    def show_status(self):
        """Show the status of a torrent."""
        logging.info(f"Peer ID: {self.peer_id}")
        seeding_table = [[torrent, path, tracker] for torrent, (path, tracker) in self.seeding_files.items()]
        if seeding_table:
            logging.info("\nSeeding Torrents:\n" + tabulate(seeding_table, headers=["Torrent File", "Path", "Tracker"], tablefmt="grid"))
        else:
            logging.info("No seeding torrents.")
    def show_peers(self, torrent_file):
        """Show the list of peers for a torrent."""
        torrent_data, info = self._load_torrent_file(torrent_file)
        info_hash = hashlib.sha1(bencodepy.encode(info)).digest()
        logging.info(f"Fetching peers from {self.tracker_url}...")

        peers = self.announce(info_hash, port=self.announce_port)  # Use announce port
        table = [[peer['ip'], peer['port']] for peer in peers]
        logging.info(f"Peers for {torrent_file}:\n")
        logging.info("\n" + tabulate(table, headers=["IP Address", "Port"], tablefmt="grid"))

    def stop_torrent(self, torrent_file):
        """Stop the torrent download or seeding."""
        torrent_data, info = self._load_torrent_file(torrent_file)
        info_hash = hashlib.sha1(bencodepy.encode(info)).digest()
        logging.info(f"Stopping torrent {torrent_file}...")

        # Notify tracker that we're stopping
        self.announce(info_hash, port=self.announce_port, event='stopped')
        logging.info("Torrent stopped.")

    def remove_torrent(self, torrent_file):
        """Remove the torrent from the client."""
        logging.info(f"Removing torrent {torrent_file} from the client...")
        # Simulate removing torrent (e.g., remove from a list or database)

    def _parse_compact_peers(self, peers):
        """Parse compact peer format."""
        peer_list = []
        for i in range(0, len(peers), 6):
            ip = struct.unpack("!I", peers[i:i+4])[0]
            ip_str = f"{(ip >> 24) & 0xFF}.{(ip >> 16) & 0xFF}.{(ip >> 8) & 0xFF}.{ip & 0xFF}"
            port = struct.unpack("!H", peers[i+4:i+6])[0]
            peer_list.append({'ip': ip_str, 'port': port})
        return peer_list

    def scrape(self, info_hash):
        """Gửi yêu cầu scrape tới tracker để lấy thông tin về số lượng peers của torrent với info_hash."""
        # Tạo URL scrape
        if 'announce' in self.tracker_url:
            scrape_url = self.tracker_url.replace('announce', 'scrape')
        else:
            raise ValueError("Tracker does not support scrape convention.")

        # Thực hiện yêu cầu scrape
        params = {'info_hash': info_hash}
        try:
            response = requests.get(scrape_url, params=params)
            response.raise_for_status()  # Kiểm tra xem yêu cầu có thành công không
            self.has_announced = True  # Đánh dấu rằng đã thông báo sự kiện
            # Giải mã phản hồi
            response_data = bencodepy.decode(response.content)

            # Lấy thông tin về torrents
            files_info = response_data.get(b'files', {})

            if info_hash in files_info:
                torrent_info = files_info[info_hash]
                complete = torrent_info.get(b'complete', 0)
                incomplete = torrent_info.get(b'incomplete', 0)
                downloaded = torrent_info.get(b'downloaded', 0)
                return {
                    'complete': complete,
                    'incomplete': incomplete,
                    'downloaded': downloaded
                }
            else:
                logging.info("No information found for the given info_hash.")
                return None

        except requests.RequestException as e:
            logging.error(f"Error during scrape request: {e}")
            return None

    def scrape_peers(self, torrent_file):
        """Scrape the tracker for peer information."""
        torrent_data, info = self._load_torrent_file(torrent_file)
        info_hash = hashlib.sha1(bencodepy.encode(info)).digest()
        logging.info(f"Scraping tracker for peer information...")
        stats = self.scrape(info_hash)
        
        if stats:
            table = [
                ["Seeders (complete)", stats['complete']],
                ["Leechers (incomplete)", stats['incomplete']],
                ["Total downloaded", stats['downloaded']]
            ]
            logging.info(f"Scrape info for {torrent_file}:\n")
            logging.info("\n" + tabulate(table, headers=["Description", "Count"], tablefmt="grid", maxcolwidths=[None, 20]))

    def sign_out(self):
        """Notify tracker that the client is offline if an event was announced."""
        if not self.has_announced:
            logging.info("No event announced, skipping sign out.")
            return

        params = {
            'peer_id': self.peer_id,
            'port': self.announce_port,
            'event': 'stopped'
        }
        try:
            for tracker_url in self.announced_trackers:
                response = requests.get(tracker_url, params=params)
                response.raise_for_status()
                logging.info(f"Signed out from tracker: {tracker_url}")
            logging.info("Signed out successfully from all trackers.")
        except requests.RequestException as e:
            logging.error(f"Error during sign out request: {e}")
        finally:
            self.stop_event.set()  # Signal the server thread to stop