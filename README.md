# Require: Python version 3.12
Install package in `requirements.txt`
# How to use client_cli.py

## Commands:

### download
Download a torrent file.

**Arguments:**
- `torrent_file` (str): Path to the torrent file.
- `--port` (int): Port to use for downloading (default: 6881).
- `--download-dir` (str): Directory to save the downloaded file.

### download_magnet
Download a torrent using a magnet link.

**Arguments:**
- `magnet_link` (str): Magnet link to download the torrent.
- `--download-dir` (str): Directory to save the downloaded file.

### seed
Seed a torrent file.

**Arguments:**
- `torrent_file` (str): Path to the torrent file.
- `complete_file` (str): Path to the complete file to seed.
- `--port` (int): Port to use for seeding (default: 6882).

### status
Show the status of the torrent client.

### peers
Manage peers for a torrent file.

**Arguments:**
- `torrent_file` (str): Path to the torrent file.
- `--scrape` (bool): Scrape the tracker for peer information.
- `--get` (bool): Get the list of peers from the tracker.

### stop
Stop a torrent file.

**Arguments:**
- `torrent_file` (str): Path to the torrent file.

### remove
Remove a torrent file.

**Arguments:**
- `torrent_file` (str): Path to the torrent file.

### create
Create a new torrent file.

**Arguments:**
- `input_path` (str): Path to the file or directory to include in the torrent.
- `--tracker` (str): Tracker address (required).
- `--output` (str): Output torrent file name (default: 'output.torrent').
- `--piece-length` (int): Piece length in bytes (default: 524288).
- `--magnet` (bool): Generate magnet link.
