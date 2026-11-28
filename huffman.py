import heapq
import json
import os
import hashlib
import zlib
import bz2
import lzma
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
        heapq.heappush(heap, (frequency, counter, Node(value, frequency)))
        counter += 1
    if not heap:
        return None, frequencies
    while len(heap) > 1:
        f1, _, left = heapq.heappop(heap)
        f2, _, right = heapq.heappop(heap)
        parent = Node(None, f1 + f2)
        parent.left, parent.right = left, right
        heapq.heappush(heap, (parent.frequency, counter, parent))
        counter += 1
    return heap[0][2], frequencies


def build_tree_from_frequencies(frequencies):
    heap = []
    counter = 0
    for value, frequency in frequencies.items():
        heapq.heappush(heap, (frequency, counter, Node(value, frequency)))
        counter += 1
    if not heap:
        return None
    while len(heap) > 1:
        f1, _, left = heapq.heappop(heap)
        f2, _, right = heapq.heappop(heap)
        parent = Node(None, f1 + f2)
        parent.left, parent.right = left, right
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


def _huffman_encode(data):
    root, frequencies = build_tree(data)
    if root is None:
        return b"", 0, []
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
        encoded.append(buffer << padding)
    return bytes(encoded), padding, list(frequencies.items())


def _huffman_decode(encoded, header):
    original_size = int(header["original_size"])
    padding = int(header["padding"])
    if not 0 <= padding <= 7:
        raise ValueError("Invalid padding information.")
    if original_size == 0:
        return b""
    frequencies = {int(v): int(f) for v, f in header["frequencies"]}
    root = build_tree_from_frequencies(frequencies)
    if root is None:
        raise ValueError("Missing Huffman tree.")
    if root.value is not None:
        return bytes([root.value]) * original_size
    result, node = bytearray(), root
    total_bits = len(encoded) * 8 - padding
    if total_bits < 0:
        raise ValueError("Invalid compressed data.")
    for bit_index in range(total_bits):
        byte_index, position = divmod(bit_index, 8)
        bit = (encoded[byte_index] >> (7 - position)) & 1
        node = node.left if bit == 0 else node.right
        if node is None:
            raise ValueError("Invalid Huffman data.")
        if node.value is not None:
            result.append(node.value)
            node = root
            if len(result) == original_size:
                break
    return bytes(result)


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


def _make_candidate(data, codec, level):
    if codec == "huffman":
        payload, padding, frequencies = _huffman_encode(data)
        return payload, {"codec": "huffman", "padding": padding, "frequencies": frequencies}
    if codec == "zlib":
        return zlib.compress(data, level), {"codec": "zlib"}
    if codec == "bz2":
        return bz2.compress(data, compresslevel=level), {"codec": "bz2"}
    if codec == "lzma":
        return lzma.compress(data, preset=level), {"codec": "lzma"}
    raise ValueError("Unsupported compression method.")


def compress_file(input_path, output_path, original_name=None,
                  target_mode="percentage", target_value=30,
                  compression_level="medium"):
    with open(input_path, "rb") as file:
        data = file.read()
    levels = {
        "low": [("huffman", 0), ("zlib", 1)],
        "medium": [("huffman", 0), ("zlib", 6), ("bz2", 5)],
        "high": [("huffman", 0), ("zlib", 9), ("bz2", 9), ("lzma", 6)]
    }
    compression_level = str(compression_level).lower()
    if compression_level not in levels:
        compression_level = "medium"
    if target_mode == "size":
        target_bytes = max(1, int(float(target_value) * 1024 * 1024))
    else:
        reduction = min(95.0, max(1.0, float(target_value)))
        target_bytes = max(1, int(len(data) * (1 - reduction / 100)))
    candidates = []
    for codec, level in levels[compression_level]:
        payload, codec_info = _make_candidate(data, codec, level)
        header = {
            "original_name": original_name or os.path.basename(input_path),
            "original_size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            **codec_info
        }
        header_bytes = json.dumps(header).encode("utf-8")
        total_size = 4 + len(header_bytes) + len(payload)
        candidates.append((total_size, header_bytes, payload))
    meeting = [item for item in candidates if item[0] <= target_bytes]
    chosen = max(meeting, key=lambda item: item[0]) if meeting else min(candidates, key=lambda item: item[0])
    _, header_bytes, payload = chosen
    with open(output_path, "wb") as file:
        file.write(len(header_bytes).to_bytes(4, "big"))
        file.write(header_bytes)
        file.write(payload)
    return len(data), os.path.getsize(output_path), target_bytes


def compress_pdf(input_path, output_path, target_mode="percentage", target_value=30):
    """Optimize a PDF without wrapping it in .huff; output remains a readable PDF."""
    try:
        import pikepdf
    except ImportError as exc:
        raise RuntimeError("PDF optimization needs pikepdf. Install it with: python -m pip install pikepdf") from exc

    original_size = os.path.getsize(input_path)
    if target_mode == "size":
        target_bytes = max(1, int(float(target_value) * 1024 * 1024))
    else:
        target_bytes = max(1, int(original_size * (1 - float(target_value) / 100)))

    try:
        with pikepdf.open(input_path) as pdf:
            pdf.save(
                output_path,
                compress_streams=True,
                recompress_flate=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate
            )
    except Exception as exc:
        raise ValueError(f"Could not optimize this PDF. It may be encrypted or damaged: {exc}") from exc

    return original_size, os.path.getsize(output_path), target_bytes


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
    codec = header.get("codec", "huffman")
    if codec == "huffman":
        data = _huffman_decode(encoded, header)
    elif codec == "zlib":
        data = zlib.decompress(encoded)
    elif codec == "bz2":
        data = bz2.decompress(encoded)
    elif codec == "lzma":
        data = lzma.decompress(encoded)
    else:
        raise ValueError("Unknown compression method in this file.")
    if len(data) != int(header["original_size"]):
        raise ValueError("Restored file size does not match original.")
    expected_hash = header.get("sha256")
    if expected_hash and hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("File verification failed. Data may be corrupted.")
    with open(output_path, "wb") as file:
        file.write(data)
    return output_path
