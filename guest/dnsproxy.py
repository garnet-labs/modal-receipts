"""Tiny in-guest DNS forwarder: answers come from the sandbox's own resolver,
every (name -> address) pair is appended to a log so connections can be named."""
import socket, struct, sys, time, threading

UPSTREAM = sys.argv[1]
LOG = sys.argv[2]


def read_name(buf, off):
    labels = []
    jumped = False
    end = None
    guard = 0
    while True:
        guard += 1
        if guard > 128:
            raise ValueError("name loop")
        ln = buf[off]
        if ln == 0:
            off += 1
            break
        if ln & 0xC0 == 0xC0:
            ptr = struct.unpack("!H", buf[off:off + 2])[0] & 0x3FFF
            if not jumped:
                end = off + 2
            jumped = True
            off = ptr
            continue
        labels.append(buf[off + 1:off + 1 + ln].decode("ascii", "replace"))
        off += 1 + ln
    return ".".join(labels), (end if end is not None else off)


def answers(buf):
    qd, an = struct.unpack("!HH", buf[4:8])
    off = 12
    for _ in range(qd):
        _, off = read_name(buf, off)
        off += 4
    out = []
    for _ in range(an):
        name, off = read_name(buf, off)
        typ, _cls, _ttl, rdlen = struct.unpack("!HHIH", buf[off:off + 10])
        off += 10
        rdata = buf[off:off + rdlen]
        off += rdlen
        if typ == 1 and rdlen == 4:
            out.append((name, socket.inet_ntop(socket.AF_INET, rdata)))
        elif typ == 28 and rdlen == 16:
            out.append((name, socket.inet_ntop(socket.AF_INET6, rdata)))
        elif typ == 5:
            cname, _ = read_name(buf, off - rdlen)
            out.append((name, "cname:" + cname))
    return out


def handle(sock, data, addr, log):
    up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    up.settimeout(5)
    try:
        up.sendto(data, (UPSTREAM, 53))
        resp, _ = up.recvfrom(4096)
    except OSError:
        return
    finally:
        up.close()
    sock.sendto(resp, addr)
    try:
        qname, _ = read_name(resp, 12)
        rows = answers(resp)
    except Exception:
        return
    now = time.time()
    with open(LOG, "a") as f:
        for name, value in rows:
            f.write(f"{now:.6f}\t{qname}\t{name}\t{value}\n")
        if len(rows) == 0:
            f.write(f"{now:.6f}\t{qname}\t-\tnoanswer\n")


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 53))
    open(LOG, "a").close()
    while True:
        data, addr = sock.recvfrom(4096)
        threading.Thread(target=handle, args=(sock, data, addr, LOG), daemon=True).start()


if __name__ == "__main__":
    main()
