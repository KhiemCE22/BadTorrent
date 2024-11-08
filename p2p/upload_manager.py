import logging
import threading
import struct
import sys
import os
import hashlib
import bencodepy
import socket
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from p2p.message import Message, MessageID
from p2p.peer_communication import Communicator
from p2p.piece import Piece
from p2p.bitfield import Bitfield
from p2p.handshake import Handshake
import logging_config
# Số lượng tối đa các yêu cầu tải lên có thể xử lý đồng thời
MAX_UPLOAD_QUEUE = 5

class UploadingManager:
    def __init__(self, pieces, peer_id, info_hash, file_paths, total_lengths, metadata=[]):
        """
        Khởi tạo UploadingManager với các mảnh mà client sở hữu.
        :param pieces: Danh sách các mảnh mà client có.
        :param peer_id: Peer ID của client.
        :param info_hash: Info hash của torrent.
        :param file_paths: Danh sách đường dẫn tới các file chứa dữ liệu.
        :param total_lengths: Danh sách chiều dài của từng file.
        :param metadata: Metadata để seeding (nếu có).
        """
        self.pieces = {piece.index: piece for piece in pieces}  # Lưu trữ mảnh theo index để truy xuất nhanh
        self.peer_id = peer_id
        self.info_hash = info_hash
        self.file_paths = file_paths  # Danh sách đường dẫn tới các file chứa dữ liệu
        self.total_lengths = total_lengths  # Danh sách chiều dài của từng file
        self.upload_queue = []
        self.peers = {}
        self.lock = threading.Lock()
        self.piece_to_file_map = self.build_piece_to_file_map()
        self.metadata = metadata  # Metadata để seeding (nếu có)

    def build_piece_to_file_map(self):
        """
        Xây dựng bản đồ ánh xạ mỗi mảnh tới các phần file tương ứng khi một mảnh có thể trải qua hai file.
        """
        piece_to_file_map = {}
        current_offset = 0
        file_idx = 0

        for piece in self.pieces.values():
            remaining_length = piece.length
            piece_to_file_map[piece.index] = []  # Tạo danh sách các phần của piece này

            while remaining_length > 0:
                file_remaining = self.total_lengths[file_idx] - current_offset

                if remaining_length <= file_remaining:
                    # Nếu mảnh còn lại hoàn toàn nằm trong file hiện tại
                    piece_to_file_map[piece.index].append((file_idx, current_offset, remaining_length))
                    current_offset += remaining_length
                    remaining_length = 0
                    if remaining_length == file_remaining:
                        # Nếu mảnh kết thúc tại cuối file hiện tại
                        current_offset = 0
                        file_idx += 1
                else:
                    # Nếu mảnh cần trải qua file kế tiếp
                    piece_to_file_map[piece.index].append((file_idx, current_offset, file_remaining))
                    remaining_length -= file_remaining
                    current_offset = 0
                    file_idx += 1

        return piece_to_file_map

    def upload_piece(self, communicator, index, begin, length):
        """
        Gửi mảnh dữ liệu cho peer khi có yêu cầu hợp lệ.
        :param communicator: Đối tượng Communicator để giao tiếp với peer.
        :param index: Index của mảnh.
        :param begin: Vị trí bắt đầu của block.
        :param length: Độ dài của block.
        """
        if index not in self.pieces:
            logging.error(f"Requested piece {index} not available.")
            return

        piece_segments = self.piece_to_file_map.get(index)
        if not piece_segments:
            logging.error(f"Piece {index} not found in piece_to_file_map.")
            return

        data = bytearray()  # Để lưu dữ liệu block cần gửi
        remaining_length = length
        read_offset = begin

        # Duyệt qua các segment của piece để đọc dữ liệu từ nhiều file nếu cần thiết
        for file_idx, file_offset, segment_length in piece_segments:
            if read_offset >= segment_length:
                # Bỏ qua phần đã vượt qua
                read_offset -= segment_length
                continue

            segment_offset = file_offset + read_offset
            segment_read_length = min(remaining_length, segment_length - read_offset)
            read_offset = 0  # Reset sau khi lấy được offset đọc ban đầu

            try:
                with open(self.file_paths[file_idx], 'rb') as f:
                    f.seek(segment_offset)
                    data.extend(f.read(segment_read_length))
                    remaining_length -= segment_read_length
                    if remaining_length <= 0:
                        break  # Đã đọc đủ dữ liệu
            except FileNotFoundError:
                logging.error(f"File not found: {self.file_paths[file_idx]}")
                return
            except IOError as e:
                logging.error(f"I/O error occurred while reading piece {index}: {e}")
                return

        # Kiểm tra đủ dữ liệu đọc được
        if len(data) != length:
            logging.error(f"Expected to read {length} bytes, but read {len(data)} bytes for piece {index}.")
            return

        # Gửi block đã hoàn thành cho peer
        msg = Message.format_piece(index, begin, data)
        communicator.conn.send(msg.serialize())
        logging.debug(f"Uploaded block {begin}-{begin + length} of piece {index} to {communicator.peer}")

    def add_peer(self, peer, client_socket):
        """
        Thêm một peer vào danh sách và bắt đầu thread để xử lý tải lên cho peer này.
        :param peer: Đối tượng Peer muốn kết nối.
        :param client_socket: Socket đã được chấp nhận từ peer.
        """
        flag_extension = False
        max_index = max(self.pieces.keys()) + 1
        bitfield_array = bytearray((max_index + 7) // 8)  # Create a bytearray to hold the bitfield
        bitfield = Bitfield(bitfield_array)

        for i in self.pieces.keys():
            bitfield.set_piece(i)
        communicator = Communicator(peer, self.peer_id, self.info_hash, bitfield.bitfield, client_socket,expected_pieces=len(self.metadata), metadata=self.metadata)
        communicator.send_handshake()  # Gửi handshake tới peer
        # manual recieve handshake, check extension bittorrent
        try:
            msg = Handshake.read(communicator.conn)
            if msg.info_hash != self.info_hash:
                raise ValueError(f"Expected infohash {self.info_hash.hex()} but got {msg.info_hash.hex()}")
            logging.debug("Received valid handshake response")

            # Check if the extension protocol is supported
            if msg.extension_bittorrent is True:
                flag_extension = True
                logging.debug("Peer supports the extension protocol")
            else:
                flag_extension = False
                logging.debug("Peer does not support the extension protocol")

        except (socket.timeout, socket.error) as e:
            logging.error(f"Error during handshake with peer {peer}: {e}")
            raise e
        if flag_extension is False:
            communicator.recv_bitfield()
            communicator.send_bitfield()  # Gửi bitfield của client tới peer
            logging.info(f"Received bitfield from {communicator.peer}")
            threading.Thread(target=self.handle_peer_requests, args=(communicator,)).start()
        else:
            communicator.send_extended_handshake()
            communicator.recv_extended_handshake()  # Nhận extended handshake từ peer
            logging.info(f"Received extended handshake from {communicator.peer}")
            threading.Thread(target=self.handle_peer_request_metadata, args=(communicator,)).start()
        self.peers[peer] = communicator

    def handle_peer_requests(self, communicator):
        """
        Xử lý yêu cầu tải lên từ một peer cụ thể.
        """
        while True:
            try:
                message = communicator.read()  # Đọc thông điệp từ peer
                if message is None:
                    continue

                # Nếu nhận được yêu cầu tải lên
                if message.ID == MessageID.MsgRequest:
                    index, begin, length = struct.unpack('>III', message.Payload)
                    logging.debug(f"Received request for piece {index} from {communicator.peer}")

                    # Gửi mảnh nếu client có mảnh được yêu cầu
                    with self.lock:
                        if index in self.pieces:
                            self.upload_piece(communicator, index, begin, length)
                            logging.debug(f"Uploaded piece {index} to {communicator.peer}")
                        else:
                            logging.warning(f"Requested piece {index} not available for upload")
                elif message.ID == MessageID.MsgInterested:
                    communicator.send_unchoke()  # Gửi thông điệp Unchoke
                elif message.ID == MessageID.MsgChoke:
                    logging.info(f"Peer {communicator.peer} has choked us")
                    break  # Dừng khi bị choked

                elif message.ID == MessageID.MsgUnchoke:
                    logging.info(f"Peer {communicator.peer} has unchoked us")

                elif message.ID == MessageID.MsgHave:
                    piece_index = struct.unpack('>I', message.Payload)[0]
                    logging.info(f"Peer {communicator.peer} has piece {piece_index}")

                elif message.ID == MessageID.MsgNotInterested:
                    logging.info(f"Peer {communicator.peer} is not interested")
                    communicator.send_choke()  # Gửi lại thông điệp Unchoke
                    break
            except Exception as e:
                logging.error(f"Error handling peer request: {e}")
                break

    def handle_peer_request_metadata(self, communicator):
        """
        Xử lý yêu cầu metadata từ một peer cụ thể.
        """
        logging.info(f"Handling metadata request from {communicator.peer}")
        while True:
            try:
                message = communicator.read()  # Đọc thông điệp từ peer
                if message is None:
                    continue    
                msg_type, payload = Message.parse_extended(message)
                # logging.debug(f"msg_type: {msg_type} with payload: {payload}")
                if msg_type == 0:  # Metadata request
                    piece_index = bencodepy.decode(payload)[b'piece']
                    if piece_index < len(self.metadata):
                        communicator.send_metadata_piece(piece_index)
                    else:
                        communicator.reject_metadata_request(piece_index)
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
                elif msg_type == 3:
                    logging.info("Peer has all metadata")
                    if Message.parse_metadata_response_type_3(message) == len(self.metadata):
                        break
                    break
            except Exception as e:
                logging.error(f"Error handling peer request: {e}")
                break
