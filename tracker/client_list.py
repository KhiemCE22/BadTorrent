class ClientList:
    def __init__(self):
        self.peers = {}

    def update_peer(self, info_hash, peer_id, ip, port, uploaded, downloaded, left, event):
        if info_hash not in self.peers:
            self.peers[info_hash] = {}

        self.peers[info_hash][peer_id] = {
            "ip": ip,
            "port": port,
            "uploaded": uploaded,
            "downloaded": downloaded,
            "left": left,
            "event": event
        }

    def remove_peer(self, info_hash, peer_id):
        if info_hash in self.peers and peer_id in self.peers[info_hash]:
            del self.peers[info_hash][peer_id]
            if not self.peers[info_hash]:
                del self.peers[info_hash]

    def remove_peer_from_all(self, peer_id):
        info_hashes_to_remove = []
        for info_hash, peer_dict in self.peers.items():
            if peer_id in peer_dict:
                del peer_dict[peer_id]
            if not peer_dict:
                info_hashes_to_remove.append(info_hash)

        for info_hash in info_hashes_to_remove:
            del self.peers[info_hash]

    def get_peers(self, info_hash, exclude_peer_id=None):
        if info_hash not in self.peers:
            return []

        peers = []
        for peer_id, peer_info in self.peers[info_hash].items():
            if peer_id == exclude_peer_id:
                continue  # Bỏ qua peer của client

            ip_bytes = bytes(map(int, peer_info["ip"].split('.')))
            port_bytes = peer_info["port"].to_bytes(2, 'big')
            peers.append(ip_bytes + port_bytes)

        return b''.join(peers)

    def get_complete_count(self, info_hash):
        if info_hash not in self.peers:
            return 0
        return sum(1 for peer in self.peers[info_hash].values() if peer["left"] == 0)

    def get_incomplete_count(self, info_hash):
        if info_hash not in self.peers:
            return 0
        return len(self.peers[info_hash]) - self.get_complete_count(info_hash)

    def get_scrape_info(self, info_hash):
        if info_hash not in self.peers:
            return {}

        complete = self.get_complete_count(info_hash)
        incomplete = len(self.peers[info_hash]) - complete

        return {
            info_hash: {
                b'complete': complete,
                b'incomplete': incomplete,
                b'downloaded': len(self.peers[info_hash])
            }
        }

    def get_all_clients(self):
        if not self.peers:
            return []
        all_clients = []
        for peer_dict in self.peers.values():
            for peer_id, peer_info in peer_dict.items():
                all_clients.append({
                    "id": peer_id,
                    "ip": peer_info["ip"]
                })
        return all_clients