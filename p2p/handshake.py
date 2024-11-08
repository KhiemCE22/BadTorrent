import logging
import logging_config
class Handshake:
    def __init__(self, info_hash: bytes, peer_id: bytes, extension_bittorrent: bool = False):
        if len(info_hash) != 20 or len(peer_id) != 20:
            raise ValueError("info_hash and peer_id must be 20 bytes long.")
        self.pstr = "BitTorrent protocol"
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.extension_bittorrent = extension_bittorrent
        if extension_bittorrent:
            self.reverse_byte = b'\x10' + b'\x00' * 7  # Bật cờ extension ở byte đầu tiên
        else:
            self.reverse_byte = b'\x00' * 8  # Không bật cờ nào
        logging.debug(f"Created handshake with info_hash: {info_hash.hex()} and peer_id: {peer_id.hex()}")

    @classmethod
    def new(cls, info_hash: bytes, peer_id: bytes):
        return cls(info_hash, peer_id)

    def serialize(self) -> bytes:
        buf = bytearray()
        buf.append(len(self.pstr))
        buf.extend(self.pstr.encode('utf-8'))
        buf.extend(self.reverse_byte)
        buf.extend(self.info_hash)
        buf.extend(self.peer_id)
        logging.debug(f"Serialized handshake: {buf.hex()}")
        return bytes(buf)

    @classmethod
    def read(cls, r) -> 'Handshake':
        length_buf = r.recv(1)
        if len(length_buf) == 0:
            raise ValueError("Failed to read handshake length")

        pstrlen = length_buf[0]
        if pstrlen == 0:
            raise ValueError("Handshake pstrlen is 0")

        handshake_buf = bytearray()
        while len(handshake_buf) < 48 + pstrlen:
            part = r.recv(48 + pstrlen - len(handshake_buf))
            if not part:
                raise ValueError("Failed to read full handshake")
            handshake_buf.extend(part)

        pstr = handshake_buf[:pstrlen].decode('utf-8')
        reserved = handshake_buf[pstrlen:pstrlen + 8]
        info_hash = handshake_buf[pstrlen + 8:pstrlen + 28]
        peer_id = handshake_buf[pstrlen + 28:pstrlen + 48]
        extension_bittorrent = (reserved[0] & 0x10) != 0
        logging.debug(f"Received handshake with pstr: {pstr}, info_hash: {info_hash.hex()}, peer_id: {peer_id.hex()}")
        return cls(info_hash, peer_id, extension_bittorrent)
