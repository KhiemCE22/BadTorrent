import argparse
import os
import bencodepy
import hashlib
import logging
import urllib.parse
import logging_config
class Metainfo:
    def __init__(self, torrent_file=None):
        self.metainfo = None
        self.info = None
        if torrent_file:
            self.load_metainfo(torrent_file)

    def load_metainfo(self, torrent_file):
        """Phân tích file .torrent và lưu trữ thông tin về tệp."""
        with open(torrent_file, 'rb') as f:
            self.metainfo = bencodepy.decode(f.read())
        self.info = self.metainfo[b'info']

    def get_info_hash(self):
        """Trả về info_hash của tệp từ file .torrent."""
        if not self.info:
            raise ValueError("Metainfo not loaded")
        info_encoded = bencodepy.encode(self.info)
        return hashlib.sha1(info_encoded).hexdigest()

    def get_piece_length(self):
        """Trả về kích thước mỗi mảnh tệp."""
        if not self.info:
            raise ValueError("Metainfo not loaded")
        return self.info[b'piece length']

    def get_total_size(self):
        """Trả về tổng kích thước tệp."""
        if not self.info:
            raise ValueError("Metainfo not loaded")
        if b'files' in self.info:
            # Multi-file mode
            return sum(file[b'length'] for file in self.info[b'files'])
        else:
            # Single-file mode
            return self.info[b'length']

    def create_magnet_link(self):
        """Tạo magnet link từ tệp .torrent."""
        if not self.metainfo:
            raise ValueError("Metainfo not loaded")

        info_hash = self.get_info_hash()
        name = self.info[b'name'].decode('utf-8')
        trackers = self.metainfo.get(b'announce-list', [[self.metainfo[b'announce']]])
        tracker_urls = [tracker[0].decode('utf-8') for tracker in trackers]

        magnet_link = f"magnet:?xt=urn:btih:{info_hash}&dn={urllib.parse.quote(name)}"
        for tracker_url in tracker_urls:
            magnet_link += f"&tr={urllib.parse.quote(tracker_url)}"

        return magnet_link

    @staticmethod
    def calculate_piece_hashes(file_list, piece_length):
        pieces = []
        buffer = bytearray()
        for file_path in file_list:
            with open(file_path, 'rb') as f:
                while True:
                    piece = f.read(piece_length - len(buffer))
                    if not piece:
                        break
                    buffer.extend(piece)
                    while len(buffer) >= piece_length:
                        pieces.append(hashlib.sha1(buffer[:piece_length]).digest())
                        buffer = buffer[piece_length:]
        if buffer:
            pieces.append(hashlib.sha1(buffer).digest())
        return b''.join(pieces)

    @staticmethod
    def create_torrent_file(input_path, tracker_address, output_torrent='output.torrent', piece_length=524288):
        # piece_length = 524288 means 512 KB per piece, you can adjust this
        
        # Gather file information
        files = []
        total_length = 0
        if os.path.isdir(input_path):
            for root, _, filenames in os.walk(input_path):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    file_info = {
                        "length": os.path.getsize(file_path),
                        "path": os.path.relpath(file_path, input_path).split(os.sep)
                    }
                    files.append(file_info)
                    total_length += os.path.getsize(file_path)
        else:
            file_info = {
                "length": os.path.getsize(input_path),
                "path": [os.path.basename(input_path)]
            }
            files.append(file_info)
            total_length += os.path.getsize(input_path)
        
        # Build torrent metadata (info dictionary)
        if len(files) == 1:
            # Single file mode
            file_path = input_path
            torrent_info = {
                'name': os.path.basename(file_path),
                'length': os.path.getsize(file_path),
                'piece length': piece_length,
                'pieces': Metainfo.calculate_piece_hashes([file_path], piece_length)
            }
        else:
            # Multi-file mode
            full_paths = [os.path.join(input_path, *file['path']) for file in files]
            torrent_info = {
                'name': os.path.basename(input_path) if os.path.isdir(input_path) else 'files',
                'files': files,
                'piece length': piece_length,
                'pieces': Metainfo.calculate_piece_hashes(full_paths, piece_length)
            }

        # Create final torrent file structure
        torrent_data = {
            'announce': tracker_address,
            'created by': 'Custom Torrent Creator',
            'info': torrent_info
        }

        # Write the .torrent file
        with open(output_torrent, 'wb') as f:
            f.write(bencodepy.encode(torrent_data))
        
        logging.info(f"Torrent file '{output_torrent}' created successfully.")

def main():
    parser = argparse.ArgumentParser(description="Create a torrent file and optionally generate a magnet link.")
    parser.add_argument('input_path', nargs='?', help='Path to the file or directory to include in the torrent')
    parser.add_argument('--tracker', help='Tracker address')
    parser.add_argument('--output', default='output.torrent', help='Output torrent file name')
    parser.add_argument('--piece-length', type=int, default=524288, help='Piece length in bytes (default: 512 KB)')
    parser.add_argument('--magnet', action='store_true', help='Generate magnet link')
    parser.add_argument('--torrent-file', help='Path to an existing .torrent file to generate a magnet link')

    args = parser.parse_args()

    if args.torrent_file:
        storage = Metainfo(args.torrent_file)
        magnet_link = storage.create_magnet_link()
        print(f"Magnet link: {magnet_link}")
    elif args.input_path and args.tracker:
        Metainfo.create_torrent_file(args.input_path, args.tracker, args.output, args.piece_length)

        if args.magnet:
            storage = Metainfo(args.output)
            magnet_link = storage.create_magnet_link()
            print(f"Magnet link: {magnet_link}")
    else:
        parser.error("the following arguments are required: input_path and --tracker, or --torrent-file")

if __name__ == '__main__':
    main()

    # Example usage:
    # python metainfo_storage.py ../torrent_example --tracker http://192.168.1.11/announce --output multiple.torrent --magnet
    # python metainfo_storage.py --torrent-file multiple.torrent --magnet