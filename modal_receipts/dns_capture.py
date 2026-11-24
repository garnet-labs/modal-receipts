"""Passive port-53 capture in the guest; no decrypted application traffic."""

import json
import signal
import socket
import struct
import sys
import time
from pathlib import Path


def packet_record(packet, timestamp):
    if len(packet) < 14:
        raise ValueError("short Ethernet header")
    fragmented = False
    if packet[12:14] == b"\x08\x00":
        if len(packet) < 34:
            raise ValueError("short IPv4 header")
        offset = 14 + (packet[14] & 15) * 4
        protocol = packet[23]
        if protocol not in (socket.IPPROTO_UDP, socket.IPPROTO_TCP):
            return None
        if offset < 34 or len(packet) < offset:
            raise ValueError("invalid IPv4 header length")
        end = 14 + struct.unpack_from("!H", packet, 16)[0]
        if end < offset:
            raise ValueError("invalid IPv4 packet length")
        packet = packet[:end]
        source = socket.inet_ntop(socket.AF_INET, packet[26:30])
        destination = socket.inet_ntop(socket.AF_INET, packet[30:34])
        fragment = struct.unpack_from("!H", packet, 20)[0]
        if fragment & 0x1FFF:
            raise ValueError("non-first transport fragment may contain DNS")
        fragmented = bool(fragment & 0x2000)
    elif packet[12:14] == b"\x86\xdd":
        if len(packet) < 54:
            raise ValueError("short IPv6 header")
        protocol, offset = packet[20], 54
        end = 54 + struct.unpack_from("!H", packet, 18)[0]
        packet = packet[:end]
        source = socket.inet_ntop(socket.AF_INET6, packet[22:38])
        destination = socket.inet_ntop(socket.AF_INET6, packet[38:54])
        while protocol in (0, 43, 44, 51, 60):
            if len(packet) < offset + 2:
                raise ValueError("short IPv6 extension header")
            following = packet[offset]
            if protocol == 44:
                length = 8
                if len(packet) < offset + length:
                    raise ValueError("short IPv6 fragment header")
                fragment = struct.unpack_from("!H", packet, offset + 2)[0]
                if fragment & 0xFFF8:
                    if following not in (0, 43, 44, 50, 51, 60, 6, 17):
                        return None
                    raise ValueError("non-first transport fragment may contain DNS")
                fragmented = fragmented or bool(fragment & 1)
            else:
                length = (
                    (packet[offset + 1] + 2) * 4
                    if protocol == 51
                    else (packet[offset + 1] + 1) * 8
                )
            if len(packet) < offset + length:
                raise ValueError("truncated IPv6 extension header")
            protocol, offset = following, offset + length
        if protocol == 50:
            raise ValueError("encrypted IPv6 payload may contain DNS")
    else:
        return None
    if protocol not in (socket.IPPROTO_UDP, socket.IPPROTO_TCP):
        return None
    if len(packet) < offset + 4:
        raise ValueError("short transport header")
    sport, dport = struct.unpack_from("!HH", packet, offset)
    if 53 not in (sport, dport):
        return None
    if fragmented:
        raise ValueError("fragmented DNS packet")
    if protocol == socket.IPPROTO_TCP:
        raise ValueError("TCP DNS requires stream reassembly")
    if len(packet) < offset + 8:
        raise ValueError("short DNS transport header")
    length = struct.unpack_from("!H", packet, offset + 4)[0]
    if length < 8 or len(packet) < offset + length:
        raise ValueError("truncated DNS datagram")
    dns_message(packet[offset + 8 : offset + length])
    return {
        "event": "dns_udp",
        "ts": timestamp,
        "source_ip": source,
        "source_port": sport,
        "destination_ip": destination,
        "destination_port": dport,
        "payload_hex": packet[offset + 8 : offset + length].hex(),
    }


def _dns_message(data):
    def name(offset, seen=()):
        labels = []
        while True:
            size = data[offset]
            offset += 1
            if size == 0:
                return ".".join(labels).lower(), offset
            if size & 0xC0 == 0xC0:
                pointer = ((size & 63) << 8) | data[offset]
                if pointer in seen or len(seen) >= 32:
                    raise ValueError("DNS compression loop")
                suffix, _ = name(pointer, (*seen, pointer))
                return ".".join([*labels, suffix]), offset + 1
            if size > 63 or offset + size > len(data):
                raise ValueError("invalid DNS label")
            labels.append(data[offset : offset + size].decode("ascii"))
            offset += size
            if len(labels) > 127:
                raise ValueError("DNS name too long")

    ident, flags, qd, an, ns, ar = struct.unpack_from("!6H", data)
    offset, questions, answers = 12, [], []
    if qd != 1 or an + ns + ar > 4096:
        raise ValueError("unsupported DNS record count")
    for _ in range(qd):
        host, offset = name(offset)
        kind, cls = struct.unpack_from("!HH", data, offset)
        offset += 4
        questions.append((host, kind, cls))
    for index in range(an + ns + ar):
        host, offset = name(offset)
        kind, cls, ttl, size = struct.unpack_from("!HHIH", data, offset)
        offset += 10
        end = offset + size
        if end > len(data):
            raise ValueError("truncated DNS record")
        value = None
        if cls == 1 and kind in (1, 28):
            value = socket.inet_ntop(
                socket.AF_INET if kind == 1 else socket.AF_INET6, data[offset:end]
            )
        elif cls == 1 and kind == 5:
            value, consumed = name(offset)
            if consumed != end:
                raise ValueError("invalid CNAME length")
        if index < an and value is not None:
            answers.append({"host": host, "type": kind, "ttl": ttl, "value": value})
        offset = end
    if offset != len(data):
        raise ValueError("trailing DNS bytes")
    return {"id": ident, "flags": flags, "questions": questions, "answers": answers}


def dns_message(data):
    try:
        return _dns_message(data)
    except (IndexError, struct.error, OSError) as exc:
        raise ValueError("malformed DNS message") from exc


def record(state):
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with (state / "dns.jsonl").open("w", buffering=1) as log:

        def emit(row):
            log.write(json.dumps({"ts": time.time(), **row}) + "\n")

        with socket.socket(
            socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)
        ) as capture:
            capture.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            capture.settimeout(0.2)
            emit({"event": "start"})
            (state / "dns-ready").touch()
            count = skipped = gaps = 0
            while running:
                try:
                    packet = capture.recv(65535)
                except TimeoutError:
                    continue
                try:
                    row = packet_record(packet, time.time())
                except (ValueError, OSError, struct.error) as exc:
                    gaps += 1
                    emit({"event": "error", "reason": str(exc)})
                    continue
                if row:
                    emit(row)
                    count += 1
                    if count >= 100000:
                        emit({"event": "error", "reason": "DNS capture limit reached"})
                        gaps += 1
                        break
                else:
                    skipped += 1
            packets, drops = struct.unpack("II", capture.getsockopt(263, 6, 8))
            emit(
                {
                    "event": "stop",
                    "packets": packets,
                    "drops": drops,
                    "skipped_non_dns": skipped,
                    "possible_dns_parse_gaps": gaps,
                }
            )


if __name__ == "__main__":
    record(Path(sys.argv[1]))
