import os
import time
import struct
from typing import Optional, List
from dataclasses import dataclass
from evs.event_encoder import EncodedEventPacket, EventEncoder, EventDecoder


@dataclass
class IOStats:
    packets_written: int = 0
    packets_read: int = 0
    total_bytes: int = 0
    dvs_events_count: int = 0
    keyframes_count: int = 0


class EventFileWriter:
    def __init__(self, file_path: str, width: int = 640, height: int = 480):
        self.file_path = file_path
        self.file = None
        self.encoder = EventEncoder(width, height)
        self.stats = IOStats()
        
        # File header
        self.magic_number = b'EVNT'  # Magic number for identification
        self.version = 1

    def open(self):
        self.file = open(self.file_path, 'wb')
        # Write file header
        header = self.magic_number + struct.pack('>I', self.version)
        self.file.write(header)

    def write_packet(self, packet: EncodedEventPacket):
        if self.file is None:
            raise RuntimeError("File not opened")
        
        data = self.encoder.serialize(packet)
        packet_len = struct.pack('>I', len(data))
        self.file.write(packet_len + data)
        
        self.stats.packets_written += 1
        self.stats.total_bytes += len(data)
        
        if packet.is_keyframe:
            self.stats.keyframes_count += 1
        self.stats.dvs_events_count += len(packet.dvs_events)

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class EventFileReader:
    def __init__(self, file_path: str, width: int = 640, height: int = 480):
        self.file_path = file_path
        self.file = None
        self.decoder = EventDecoder(width, height)
        self.stats = IOStats()
        
        self.magic_number = b'EVNT'

    def open(self) -> bool:
        self.file = open(self.file_path, 'rb')
        # Read and verify header
        magic = self.file.read(4)
        if magic != self.magic_number:
            self.close()
            return False
        
        version = struct.unpack('>I', self.file.read(4))[0]
        if version != 1:
            print(f"Warning: Unknown version {version}")
        
        return True

    def read_packet(self) -> Optional[EncodedEventPacket]:
        if self.file is None:
            return None
        
        # Read packet length
        len_data = self.file.read(4)
        if not len_data:
            return None
        
        packet_len = struct.unpack('>I', len_data)[0]
        data = self.file.read(packet_len)
        if not data:
            return None
        
        packet = self.decoder.deserialize(data)
        
        self.stats.packets_read += 1
        self.stats.total_bytes += packet_len
        if packet.is_keyframe:
            self.stats.keyframes_count += 1
        self.stats.dvs_events_count += len(packet.dvs_events)
        
        return packet

    def read_all_packets(self) -> List[EncodedEventPacket]:
        packets = []
        while True:
            packet = self.read_packet()
            if packet is None:
                break
            packets.append(packet)
        return packets

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class EventNetworkInterface:
    def __init__(self, host: str = 'localhost', port: int = 5000):
        self.host = host
        self.port = port
        self.socket = None
        self.connection = None
        self.encoder = EventEncoder()
        self.decoder = EventDecoder()
        self.stats = IOStats()

    def listen(self):
        import socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((self.host, self.port))
        self.socket.listen(1)
        print(f"Listening on {self.host}:{self.port}")

    def accept_connection(self) -> bool:
        if self.socket is None:
            return False
        self.connection, addr = self.socket.accept()
        print(f"Connected by {addr}")
        return True

    def connect(self) -> bool:
        import socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        self.connection = self.socket
        print(f"Connected to {self.host}:{self.port}")
        return True

    def send_packet(self, packet: EncodedEventPacket) -> bool:
        if self.connection is None:
            return False
        
        data = self.encoder.serialize(packet)
        packet_len = struct.pack('>I', len(data))
        
        try:
            self.connection.sendall(packet_len + data)
            self.stats.packets_written += 1
            self.stats.total_bytes += len(data)
            if packet.is_keyframe:
                self.stats.keyframes_count += 1
            self.stats.dvs_events_count += len(packet.dvs_events)
            return True
        except:
            return False

    def receive_packet(self) -> Optional[EncodedEventPacket]:
        if self.connection is None:
            return None
        
        try:
            len_data = self.connection.recv(4)
            if not len_data:
                return None
            
            packet_len = struct.unpack('>I', len_data)[0]
            data = self.connection.recv(packet_len)
            if not data:
                return None
            
            packet = self.decoder.deserialize(data)
            self.stats.packets_read += 1
            self.stats.total_bytes += packet_len
            if packet.is_keyframe:
                self.stats.keyframes_count += 1
            self.stats.dvs_events_count += len(packet.dvs_events)
            
            return packet
        except:
            return None

    def close(self):
        if self.connection is not None and self.connection != self.socket:
            self.connection.close()
            self.connection = None
        if self.socket is not None:
            self.socket.close()
            self.socket = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
