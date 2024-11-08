import socket
import logging
import threading
import os
import sys
import bencodepy

MAX_BLOCK_SIZE = 16384  # 16 KB
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import logging_config
from p2p.bitfield import Bitfield
from p2p.peer import Peer
from p2p.message import Message, MessageID
from p2p.handshake import Handshake
class Communicator:
    def __init__(self, peer: Peer, peer_id: bytes, info_hash: bytes, bitfield: Bitfield = None, conn=None, expected_pieces=0, metadata=[]):
        self.conn = conn
        self.peer = peer
        self.peer_id = peer_id
        self.info_hash = info_hash
        self.bitfield = bitfield
        self.expected_pieces = expected_pieces  # Số lượng phần của metadata cần nhận
        self.metadata = metadata  # Lưu trữ metadata từng phần đã nhận
        self.choked = True

        logging.debug(f"Created communicator with peer {peer}")

        if self.conn is None:
            self.conn = self.connect(peer)

        # self.complete_handshake()
        # if self.bitfield is None:
        #     self.recv_bitfield()
        # else:
        #     logging.debug("Bitfield already present (seeder), skipping recv_bitfield")

    def connect(self, peer: Peer):
        """Kết nối đến một peer."""
        try:
            conn = socket.create_connection((peer.ip, peer.port), timeout=1.5)
            logging.debug(f"Connected to peer {peer}")
            return conn
        except (socket.timeout, socket.error) as e:
            logging.error(f"Error connecting to peer {peer}: {e}")
            raise e

    # def complete_handshake(self):
    #     """Thực hiện handshake với peer và gửi bitfield nếu có."""
    #     req = Handshake(info_hash=self.info_hash, peer_id=self.peer_id)
    #     self.conn.settimeout(7)

    #     try:
    #         self.conn.send(req.serialize())
    #         logging.debug("Sent handshake")

    #         res = Handshake.read(self.conn)
    #         if res.info_hash != self.info_hash:
    #             raise ValueError(f"Expected infohash {self.info_hash.hex()} but got {res.info_hash.hex()}")
    #         logging.debug("Received valid handshake response")

    #         # Kiểm tra hỗ trợ Extension Protocol
    #         if res.reserved[0] & 0x10:
    #             logging.debug("Peer supports Extension Protocol")
    #             self.send_extended_handshake()
    #             self.recv_extended_handshake()
    #         else:
    #             logging.debug("Peer does not support Extension Protocol")

    #         # Send bitfield sau khi handshake nếu có
    #         if self.bitfield:
    #             self.send_bitfield()
    #         else:
    #             logging.debug("No bitfield to send")
    #     except (socket.timeout, socket.error) as e:
    #         logging.error(f"Error during handshake with peer {self.peer}: {e}")
    #         raise e
    def send_extended_handshake(self):
        """Gửi extended handshake để thông báo khả năng hỗ trợ metadata."""
        extended_handshake = Message.format_extended_handshake(self.expected_pieces)
        self.conn.send(extended_handshake.serialize())
        logging.debug("Sent extended handshake to peer")

    def recv_extended_handshake(self):
        """Nhận và xử lý Extended Handshake Message từ peer."""
        msg, err = Message.read(self.conn)
        if err:
            logging.error(f"Error reading extended handshake message: {err}")
            return
        if msg.ID == MessageID.MsgExtended:
            logging.info(f"msg.Payload: {msg.Payload[1:0]}")
            
            handshake = bencodepy.decode(bytes(msg.Payload[1:]))
            logging.debug(f"Received extended handshake: {handshake}")
            logging.debug("Received extended handshake")
            if handshake[b'pieces_number'] > 0:
                self.expected_pieces = handshake[b'pieces_number']
                logging.debug("Peer supports metadata exchange (ut_metadata)")
            else:
                logging.debug("Peer does not support metadata exchange")

    def recv_bitfield(self):
        """Nhận bitfield từ peer và gửi xác nhận 'Interested' nếu có thể download."""
        self.conn.settimeout(10)
        try:
            msg, err = Message.read(self.conn)
            if err:
                logging.error(f"Error reading message: {err}")
                return False  # Trả về False nếu có lỗi
            if msg is None:
                logging.error("Expected bitfield but got None")
                return False  # Trả về False nếu không nhận được thông điệp
            if msg.ID != MessageID.MsgBitfield:
                logging.error(f"Expected bitfield message but got {msg.ID}")
                return False  # Trả về False nếu không phải thông điệp bitfield
            if self.bitfield is None:
                self.bitfield = Bitfield(msg.Payload)
            logging.debug("Received bitfield")
            return True  # Trả về True nếu nhận thành công
        except socket.timeout:
            logging.error("Timeout while waiting for bitfield")
            return False  # Trả về False nếu timeout


    def send_bitfield(self):
        """Gửi bitfield tới peer."""
        bitfield_msg = Message(message_id=MessageID.MsgBitfield, payload=self.bitfield)
        self.conn.send(bitfield_msg.serialize())
        logging.debug("Sent bitfield")

    def send_interested(self):
        """Gửi thông điệp Interested tới peer."""
        msg = Message(message_id=MessageID.MsgInterested)
        self.conn.send(msg.serialize())

    def send_request(self, index, begin, length):
        """Gửi một thông điệp Request tới peer."""
        req = Message.format_request(index, begin, length)
        self.conn.send(req.serialize())
    def send_unchoke(self):
        """Gửi thông điệp Unchoke tới peer."""
        msg = Message(message_id=MessageID.MsgUnchoke)
        self.conn.send(msg.serialize())
    def send_have(self, piece_index):
        """Gửi thông điệp Have tới peer."""
        msg = Message.format_have(piece_index)
        self.conn.send(msg.serialize())
    def send_choke(self):
        """Gửi thông điệp Choke tới peer."""
        msg = Message(message_id=MessageID.MsgChoke)
        self.conn.send(msg.serialize())
    def handle_metadata_message(self, message):
        """Xử lý phản hồi metadata từ peer."""
        try:
            msg_type, payload = Message.parse_extended(message)
            logging.debug(f"msg_type: {msg_type} with payload: {payload}")
            if msg_type == 0:  # Metadata request
                piece_index = bencodepy.decode(payload)[b'piece']
                if piece_index < len(self.metadata):
                    self.send_metadata_piece(piece_index)
                else:
                    self.reject_metadata_request(piece_index)
            elif msg_type == 1:  # Metadata data (response)
                piece_index, data = Message.parse_metadata_response_type_1(message)
                while len(self.metadata) <= piece_index:
                    self.metadata.append(None)  # Hoặc giá trị mặc định nào đó
                self.metadata[piece_index] = data
                logging.debug(f"type of metadata: {type(data)}")
                logging.debug(f"Received metadata piece {piece_index}")
            elif msg_type == 2:  # Metadata reject
                piece_index = Message.parse_metadata_response_type_2(message)
                logging.warning(f"Metadata request for piece {piece_index} was rejected")
        except Exception as e:
            logging.error(f"Failed to handle metadata message: {e}")

    def send_have_metadata(self, pieces_number):
        """Gửi thông điệp Have cho một phần metadata đã nhận."""
        have_metadata = Message.format_have_metadata(pieces_number)
        self.conn.sendall(have_metadata.serialize())
        logging.debug(f"Sent have_metadata")

    def send_metadata_piece(self, piece_index):
        """Gửi phần metadata được yêu cầu cho peer."""
        if piece_index < len(self.metadata):
            data = self.metadata[piece_index]
            response_message = Message.format_metadata_data(piece_index, data)
            self.conn.sendall(response_message.serialize())
            logging.debug(f"Sent metadata piece {piece_index}")
        else:
            self.reject_metadata_request(piece_index)
    def receive_metadata_piece(self):
        """Nhận một phần metadata từ peer."""
        try:
            message, error = Message.read(self.conn)
            if error:
                logging.error(f"Error receiving metadata piece: {error}")
            elif message and message.ID == MessageID.MsgExtended:
                logging.debug("Received metadata message")
                logging.debug(f"msg.Payload: {message.Payload}")
                self.handle_metadata_message(message)
            else:
                logging.debug("Received non-metadata message or keep-alive")
        except Exception as e:
            logging.error(f"Unexpected error in receive_metadata_piece: {e}")
    def request_metadata_piece(self, piece_index):
        """Gửi yêu cầu metadata cho một phần cụ thể."""
        metadata_request = Message.format_metadata_request(piece_index)
        self.conn.sendall(metadata_request.serialize())
        logging.debug(f"Requested metadata piece {piece_index}")

    def reject_metadata_request(self, piece_index):
        """Phản hồi từ chối yêu cầu metadata."""
        reject_message = Message.format_metadata_reject(piece_index)
        self.conn.sendall(reject_message.serialize())
        logging.debug(f"Rejected metadata request for piece {piece_index}")

    def check_complete_metadata(self):
        """Kiểm tra nếu toàn bộ metadata đã được nhận."""
        if len(self.metadata) == self.expected_pieces:
            return True
        else:
            return False

    def receive(self):
        """Nhận và xử lý các thông điệp từ peer."""
        try:
            message, error = Message.read(self.conn)
            if error:
                logging.error(f"Error receiving message: {error}")
            elif message and message.ID == MessageID.MsgExtended:
                self.handle_metadata_message(message)
            else:
                logging.debug("Received non-metadata message or keep-alive")
        except Exception as e:
            logging.error(f"Unexpected error in receive: {e}")

    def send_handshake(self, bittorrent_extension=False):
        """Gửi handshake tới peer."""
        handshake = Handshake(self.info_hash, self.peer_id, bittorrent_extension)
        self.conn.send(handshake.serialize())
        logging.debug("Sent handshake")
    def send_not_interested(self):
        """Gửi thông điệp Not Interested tới peer."""
        msg = Message(message_id=MessageID.MsgNotInterested)
        self.conn.send(msg.serialize())
    def recv_handshake(self):
        """Nhận và xử lý handshake từ peer."""
        try:
            msg = Handshake.read(self.conn)
            if msg.info_hash != self.info_hash:
                raise ValueError(f"Expected infohash {self.info_hash.hex()} but got {msg.info_hash.hex()}")
            logging.debug("Received valid handshake response")
        except (socket.timeout, socket.error) as e:
            logging.error(f"Error during handshake with peer {self.peer}: {e}")
            raise e
    def read(self):
        """Đọc một thông điệp từ kết nối."""
        try:
            msg, err = Message.read(self.conn)
            if err:
                logging.error(f"Error reading message: {err}")
            return msg
        except socket.timeout:
            logging.warning("Timeout while reading message, retrying...")
            return None
    def close_connection(self):
        """Đóng kết nối."""
        self.conn.close()
        logging.debug(f"Closed connection to {self.peer}")