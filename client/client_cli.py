import argparse
import os
import sys
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from client.client_node import ClientNode
from metainfo.metainfo import Metainfo
import logging_config
def main():
    """
    Main function to initialize and run the Torrent Client CLI.
    This function sets up the argument parser, defines subcommands for various
    torrent-related operations, and handles the execution of these commands
    based on user input. It also provides an interactive mode for continuous
    command execution.
    Commands:
        download: Download a torrent file.
            Arguments:
                torrent_file (str): Path to the torrent file.
                --port (int): Port to use for downloading (default: 6881).
                --download-dir (str): Directory to save the downloaded file.
        download_magnet: Download a torrent using a magnet link.
            Arguments:
                magnet_link (str): Magnet link to download the torrent.
                --download-dir (str): Directory to save the downloaded file.
        seed: Seed a torrent file.
            Arguments:
                torrent_file (str): Path to the torrent file.
                complete_file (str): Path to the complete file to seed.
                --port (int): Port to use for seeding (default: 6882).
        status: Show the status of the torrent client.
        peers: Manage peers for a torrent file.
            Arguments:
                torrent_file (str): Path to the torrent file.
                --scrape (bool): Scrape the tracker for peer information.
                --get (bool): Get the list of peers from the tracker.
        stop: Stop a torrent file.
            Arguments:
                torrent_file (str): Path to the torrent file.
        remove: Remove a torrent file.
            Arguments:
                torrent_file (str): Path to the torrent file.
        create: Create a new torrent file.
            Arguments:
                input_path (str): Path to the file or directory to include in the torrent.
                --tracker (str): Tracker address (required).
                --output (str): Output torrent file name (default: 'output.torrent').
                --piece-length (int): Piece length in bytes (default: 524288).
                --magnet (bool): Generate magnet link.
    Interactive Mode:
        Allows continuous command execution until 'exit' is entered.
    Exceptions:
        Catches and prints any exceptions that occur during command execution.
    Finally:
        Ensures the client signs out when exiting the interactive mode.
    """
    # Initialize client
    client = ClientNode()

    parser = argparse.ArgumentParser(description="Torrent Client CLI")
    subparsers = parser.add_subparsers(dest='command')

    # Command download
    download_parser = subparsers.add_parser('download')
    download_parser.add_argument('torrent_file', help='Path to the torrent file')
    download_parser.add_argument('--port', type=int, default=6881, help='Port to use for downloading')
    download_parser.add_argument('--download-dir', help='Directory to save the downloaded file')

    # Command download magnet
    download_magnet_parser = subparsers.add_parser('download_magnet')
    download_magnet_parser.add_argument('magnet_link', help='Magnet link to download the torrent')
    download_magnet_parser.add_argument('--download-dir', help='Directory to save the downloaded file')

    # Command seed
    seed_parser = subparsers.add_parser('seed')
    seed_parser.add_argument('torrent_file', help='Path to the torrent file')
    seed_parser.add_argument('complete_file', help='Path to the complete file to seed')
    seed_parser.add_argument('--port', type=int, default=6882, help='Port to use for seeding')

    # Command status
    status_parser = subparsers.add_parser('status')

    # Command peers
    peers_parser = subparsers.add_parser('peers')
    peers_parser.add_argument('torrent_file', help='Path to the torrent file')
    peers_parser.add_argument('--scrape', action='store_true', help='Scrape the tracker for peer information')
    peers_parser.add_argument('--get', action='store_true', help='Get the list of peers from the tracker')

    # Command stop
    stop_parser = subparsers.add_parser('stop')
    stop_parser.add_argument('torrent_file', help='Path to the torrent file')

    # Command remove
    remove_parser = subparsers.add_parser('remove')
    remove_parser.add_argument('torrent_file', help='Path to the torrent file')

    # Command create
    create_parser = subparsers.add_parser('create')
    create_parser.add_argument('input_path', help='Path to the file or directory to include in the torrent')
    create_parser.add_argument('--tracker', required=True, help='Tracker address')
    create_parser.add_argument('--output', default='output.torrent', help='Output torrent file name')
    create_parser.add_argument('--piece-length', type=int, default=524288, help='Piece length in bytes (default: 512 KB)')
    create_parser.add_argument('--magnet', action='store_true', help='Generate magnet link')

    # Parse initial arguments
    args = parser.parse_args()

    # If a command is provided, execute it
    if args.command:
        try:
            if args.command == 'download':
                client.download_torrent(args.torrent_file, port=args.port, download_dir=args.download_dir)
            elif args.command == 'download_magnet':
                client.download_magnet(args.magnet_link, download_dir=args.download_dir)
            elif args.command == 'seed':
                client.seed_torrent(args.torrent_file, args.complete_file, port=args.port)
            elif args.command == 'status':
                client.show_status()
            elif args.command == 'peers':
                if args.scrape:
                    client.scrape_peers(args.torrent_file)
                elif args.get:
                    client.show_peers(args.torrent_file)
                else:
                    print("Unknown peers command")
            elif args.command == 'stop':
                client.stop_torrent(args.torrent_file)
            elif args.command == 'remove':
                client.remove_torrent(args.torrent_file)
            elif args.command == 'create':
                Metainfo.create_torrent_file(args.input_path, args.tracker, args.output, args.piece_length)
                if args.magnet:
                    storage = Metainfo(args.output)
                    magnet_link = storage.create_magnet_link()
                    print(f"Magnet link: {magnet_link}")
            else:
                print("Unknown command")
        except Exception as e:
            print(f"Error executing command: {e}")

    # Enter interactive mode
    try:
        while True:
            command = input(">>> ").split()
            if not command:
                continue
            if command[0] == 'exit':
                break
            try:
                args = parser.parse_args(command)
            except SystemExit:
                print("Invalid command. Please try again.")
                continue

            if args.command == 'download':
                client.download_torrent(args.torrent_file, port=args.port, download_dir=args.download_dir)
            elif args.command == 'download_magnet':
                client.download_magnet(args.magnet_link, download_dir=args.download_dir)
            elif args.command == 'seed':
                client.seed_torrent(args.torrent_file, args.complete_file, port=args.port)
            elif args.command == 'status':
                client.show_status()
            elif args.command == 'peers':
                if args.scrape:
                    client.scrape_peers(args.torrent_file)
                elif args.get:
                    client.show_peers(args.torrent_file)
                else:
                    print("Unknown peers command")
            elif args.command == 'stop':
                client.stop_torrent(args.torrent_file)
            elif args.command == 'remove':
                client.remove_torrent(args.torrent_file)
            elif args.command == 'create':
                Metainfo.create_torrent_file(args.input_path, args.tracker, args.output, args.piece_length)
                if args.magnet:
                    storage = Metainfo(args.output)
                    magnet_link = storage.create_magnet_link()
                    print(f"Magnet link: {magnet_link}")
            else:
                print("Unknown command")
    finally:
        # Sign out when exiting if an event was announced
        client.sign_out()

if __name__ == '__main__':
    main()