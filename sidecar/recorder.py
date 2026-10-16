"""Garnet sidecar recorder: a pass-through SNI relay on :443.

Modal's `proxy_traffic_via_sidecar` relays every TCP:443 connection from the main
container to this process. It reads the TLS ClientHello, records the SNI host name,
connects to that host on 443 and splices bytes both ways. Nothing is decrypted and
nothing runs in the sandbox. One JSON line per connection in /garnet/sidecar.log.
"""
import asyncio, json, os, socket, struct, time

LOG = os.environ.get("GARNET_SIDECAR_LOG", "/garnet/sidecar.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)


def parse_sni(data: bytes):
    # TLS record: type(1) ver(2) len(2); handshake: type(1) len(3); ClientHello body
    if len(data) < 9 or data[0] != 0x16 or data[5] != 0x01:
        return None
    p = 9 + 2 + 32                       # version + random
    if len(data) < p + 1:
        return None
    p += 1 + data[p]                     # session id
    if len(data) < p + 2:
        return None
    p += 2 + struct.unpack("!H", data[p:p + 2])[0]   # cipher suites
    if len(data) < p + 1:
        return None
    p += 1 + data[p]                     # compression
    if len(data) < p + 2:
        return None
    ext_len = struct.unpack("!H", data[p:p + 2])[0]
    p += 2
    end = min(len(data), p + ext_len)
    while p + 4 <= end:
        et, el = struct.unpack("!HH", data[p:p + 4])
        p += 4
        if et == 0 and p + 5 <= end:
            nl = struct.unpack("!H", data[p + 3:p + 5])[0]
            return data[p + 5:p + 5 + nl].decode("ascii", "replace").lower().rstrip(".")
        p += el
    return None


def log(rec):
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")


async def pump(r, w, counter):
    try:
        while True:
            b = await r.read(65536)
            if not b:
                break
            counter[0] += len(b)
            w.write(b)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def handle(reader, writer):
    try:
        await _handle(reader, writer)
    except Exception as e:
        log({"ts": round(time.time(), 3), "outcome": "handler_exception", "error": repr(e)[:200]})
        try: writer.close()
        except Exception: pass


async def _handle(reader, writer):
    t0 = time.time()
    peer = writer.get_extra_info("peername")
    rec = {"ts": round(t0, 3), "client": f"{peer[0]}:{peer[1]}", "port": 443}
    try:  # is the original destination visible to the sidecar? (recorded as a fact either way)
        raw = writer.get_extra_info("socket").getsockopt(socket.SOL_IP, 80, 16)  # SO_ORIGINAL_DST
        rec["orig_dst"] = f"{socket.inet_ntoa(raw[4:8])}:{struct.unpack('!H', raw[2:4])[0]}"
    except OSError as e:
        rec["orig_dst"] = None
    try:
        head = await asyncio.wait_for(reader.read(16384), timeout=10)
    except Exception as e:
        rec.update(outcome="no_clienthello", error=str(e)[:100])
        log(rec); writer.close(); return
    sni = parse_sni(head)
    rec["sni"] = sni
    if not sni:
        rec.update(outcome="refused_no_sni")
        log(rec); writer.close(); return
    try:
        ur, uw = await asyncio.wait_for(asyncio.open_connection(sni, 443), timeout=15)
    except Exception as e:
        rec.update(outcome="upstream_failed", error=str(e)[:100])
        log(rec); writer.close(); return
    rec["upstream"] = uw.get_extra_info("peername")[0]
    try:
        uw.write(head); await uw.drain()
        up, down = [len(head)], [0]
        await asyncio.gather(pump(reader, uw, up), pump(ur, writer, down))
        rec.update(outcome="relayed", bytes_up=up[0], bytes_down=down[0], dur_s=round(time.time() - t0, 3))
    except Exception as e:
        rec.update(outcome="relay_error", error=str(e)[:100], dur_s=round(time.time() - t0, 3))
    log(rec)


async def main():
    log({"ts": round(time.time(), 3), "event": "recorder_start", "pid": os.getpid()})
    srv = await asyncio.start_server(handle, "0.0.0.0", 443)
    async with srv:
        await srv.serve_forever()

asyncio.run(main())
