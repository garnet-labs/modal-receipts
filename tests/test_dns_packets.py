import json
import signal
import socket
import struct

import pytest
from test_dns_attribution import messages

from modal_receipts.dns_capture import packet_record, record


def ipv4(payload, protocol=17, fragment=0):
    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(payload),
        1,
        fragment,
        64,
        protocol,
        0,
        socket.inet_aton("192.0.2.1"),
        socket.inet_aton("192.0.2.2"),
    )
    return bytes(12) + b"\x08\x00" + header + payload


def ipv6(payload, protocol=17):
    header = struct.pack(
        "!IHBB16s16s",
        6 << 28,
        len(payload),
        protocol,
        64,
        socket.inet_pton(socket.AF_INET6, "::1"),
        socket.inet_pton(socket.AF_INET6, "::2"),
    )
    return bytes(12) + b"\x86\xdd" + header + payload


def udp(payload, port=53):
    return struct.pack("!HHHH", 5000, port, 8 + len(payload), 0) + payload


def test_mld_after_hop_by_hop_is_not_dns():
    hop = bytes([58, 0, 5, 2, 0, 0, 1, 0])
    assert packet_record(ipv6(hop + bytes([143]) + bytes(27), 0), 1) is None


def test_non_first_non_transport_ipv4_fragment_is_not_dns():
    assert packet_record(ipv4(bytes(16), protocol=1, fragment=1), 1) is None


@pytest.mark.parametrize("make", [ipv4, ipv6])
def test_dns_parses_and_non_dns_skips(make):
    query, _ = messages()
    assert packet_record(make(udp(query)), 1)["payload_hex"] == query.hex()
    assert packet_record(make(udp(b"not DNS", port=123)), 1) is None
    with pytest.raises(ValueError, match="DNS"):
        packet_record(make(udp(b"bad")), 1)
    with pytest.raises(ValueError, match="truncated DNS"):
        packet_record(make(udp(query)[:-1]), 1)


@pytest.mark.parametrize("extension,length", [(0, 8), (43, 8), (60, 8), (51, 8)])
def test_dns_after_extension(extension, length):
    query, _ = messages()
    header = bytes([17, 0]) + bytes(length - 2)
    assert packet_record(ipv6(header + udp(query), extension), 1)


def test_fragments_fail_closed_unless_provably_non_dns():
    query, _ = messages()
    with pytest.raises(ValueError, match="fragmented DNS"):
        packet_record(ipv4(udp(query), fragment=0x2000), 1)
    assert packet_record(ipv4(udp(query, port=123), fragment=0x2000), 1) is None
    with pytest.raises(ValueError, match="may contain DNS"):
        packet_record(ipv4(bytes(16), fragment=1), 1)
    with pytest.raises(ValueError, match="fragmented DNS"):
        packet_record(ipv6(bytes([17, 0, 0, 1]) + bytes(4) + udp(query), 44), 1)
    with pytest.raises(ValueError, match="may contain DNS"):
        packet_record(ipv6(bytes([17, 0, 0, 8]) + bytes(20), 44), 1)


@pytest.mark.parametrize("payload", [b"", b"\x11", b"\x11\x02" + bytes(6)])
def test_truncated_extensions_are_gaps(payload):
    with pytest.raises(ValueError, match="IPv6 extension"):
        packet_record(ipv6(payload, 0), 1)


def test_recorder_counts_skips_and_gaps_and_emits_error(monkeypatch, tmp_path):
    query, _ = messages()
    packets = iter(
        [ipv4(udp(b"non-DNS", port=123)), ipv4(udp(query)), ipv4(udp(b"bad"))]
    )
    handlers = {}

    class Capture:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def setsockopt(self, *_):
            pass

        def settimeout(self, *_):
            pass

        def recv(self, *_):
            try:
                return next(packets)
            except StopIteration:
                handlers[signal.SIGTERM]()
                raise TimeoutError from None

        def getsockopt(self, *_):
            return struct.pack("II", 3, 0)

    monkeypatch.setattr(
        signal, "signal", lambda key, handler: handlers.update({key: handler})
    )
    monkeypatch.setattr(socket, "socket", lambda *_: Capture())
    record(tmp_path)
    rows = [
        json.loads(line) for line in (tmp_path / "dns.jsonl").read_text().splitlines()
    ]
    assert [row["event"] for row in rows] == ["start", "dns_udp", "error", "stop"]
    assert rows[-1]["skipped_non_dns"] == 1
    assert rows[-1]["possible_dns_parse_gaps"] == 1
