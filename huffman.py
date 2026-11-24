
import heapq
import json
import os
import hashlib
from collections import Counter


class Node:
    def __init__(self, value, frequency):
        self.value = value
        self.frequency = frequency
        self.left = None
        self.right = None


def build_tree(data):
    frequencies = Counter(data)
    heap = []
    counter = 0

    for value, frequency in frequencies.items():
        node = Node(value, frequency)
        heapq.heappush(heap, (frequency, counter, node))
        counter += 1

    if not heap:
        return None, frequencies

    while len(heap) > 1:
        f1, _, left = heapq.heappop(heap)
        f2, _, right = heapq.heappop(heap)

        parent = Node(None, f1 + f2)
        parent.left = left
        parent.right = right

        heapq.heappush(heap, (parent.frequency, counter, parent))
        counter += 1

    return heap[0][2], frequencies


def build_tree_from_frequencies(frequencies):
    heap = []
    counter = 0

    for value, frequency in frequencies.items():
        node = Node(value, frequency)
        heapq.heappush(heap, (frequency, counter, node))
        counter += 1

    if not heap:
        return None

    while len(heap) > 1:
        f1, _, left = heapq.heappop(heap)
        f2, _, right = heapq.heappop(heap)

        parent = Node(None, f1 + f2)
        parent.left = left
        parent.right = right

        heapq.heappush(heap, (parent.frequency, counter, parent))
        counter += 1

    return heap[0][2]


def generate_codes(root):
    codes = {}

    def walk(node, code):
        if node is None:
            return

        if node.value is not None:
            codes[node.value] = code or "0"
            return

        walk(node.left, code + "0")
        walk(node.right, code + "1")

    walk(root, "")
    return codes


def read_header(input_path):
    with open(input_path, "rb") as file:
        size_data = file.read(4)

        if len(size_data) != 4:
            raise ValueError("Invalid compressed file.")

        header_size = int.from_bytes(size_data, "big")

        header_data = file.read(header_size)

        if len(header_data) != header_size:
            raise ValueError("Incomplete compressed file header.")

        return json.loads(header_data.decode("utf-8"))


def compress_file(input_path, output_path, original_name=None):

    with open(input_path, "rb") as file:
        data = file.read()

    root, frequencies = build_tree(data)
    codes = generate_codes(root)

    encoded = bytearray()
    buffer = 0
    bit_count = 0

    for symbol in data:
        for bit in codes[symbol]:
            buffer = (buffer << 1) | int(bit)
            bit_count += 1

            if bit_count == 8:
                encoded.append(buffer)
                buffer = 0
                bit_count = 0

    padding = (8 - bit_count) % 8

    if bit_count:
        buffer <<= padding
        encoded.append(buffer)

    header = {
        "original_name": original_name or os.path.basename(input_path),
        "original_size": len(data),
        "padding": padding,
        "frequencies": list(frequencies.items()),
        "sha256": hashlib.sha256(data).hexdigest()
    }

    header_bytes = json.dumps(header).encode("utf-8")

    with open(output_path, "wb") as file:
        file.write(len(header_bytes).to_bytes(4, "big"))
        file.write(header_bytes)
        file.write(encoded)

    return len(data), os.path.getsize(output_path)


def decompress_file(input_path, output_path):

    with open(input_path, "rb") as file:
        size_data = file.read(4)

        if len(size_data) != 4:
            raise ValueError("Invalid compressed file.")

        header_size = int.from_bytes(size_data, "big")
        header_data = file.read(header_size)

        if len(header_data) != header_size:
            raise ValueError("Incomplete compressed file header.")

        header = json.loads(header_data.decode("utf-8"))
        encoded = file.read()

    original_size = header["original_size"]
    padding = header["padding"]

    if padding < 0 or padding > 7:
        raise ValueError("Invalid padding information.")

    if original_size == 0:
        data = b""

    else:
        frequencies = {
            int(value): int(frequency)
            for value, frequency in header["frequencies"]
        }

        root = build_tree_from_frequencies(frequencies)

        if root is None:
            raise ValueError("Missing Huffman tree.")

        if root.value is not None:
            data = bytes([root.value]) * original_size

        else:
            result = bytearray()
            node = root

            total_bits = len(encoded) * 8 - padding

            if total_bits < 0:
                raise ValueError("Invalid compressed data.")

            for bit_index in range(total_bits):
                byte_index = bit_index // 8
                position = 7 - (bit_index % 8)

                bit = (encoded[byte_index] >> position) & 1

                node = node.left if bit == 0 else node.right

                if node is None:
                    raise ValueError("Invalid Huffman data.")

                if node.value is not None:
                    result.append(node.value)
                    node = root

                    if len(result) == original_size:
                        break

            data = bytes(result)

    if len(data) != original_size:
        raise ValueError("Restored file size does not match original.")

    expected_hash = header.get("sha256")

    if expected_hash:
        actual_hash = hashlib.sha256(data).hexdigest()

        if actual_hash != expected_hash:
            raise ValueError("File verification failed. Data may be corrupted.")

    with open(output_path, "wb") as file:
        file.write(data)

    return output_path
