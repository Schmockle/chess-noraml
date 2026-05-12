#!/usr/bin/env python3
"""
Chess relay server — lets two players connect over the internet with a 4-digit code.
No external dependencies (stdlib only).

Deploy to Railway:
  1. Push this file to a GitHub repo
  2. New project on railway.app → deploy from repo
  3. Settings → Networking → Add TCP Proxy → note the host:port
  4. Paste host + port into RELAY_HOST / RELAY_PORT in chess_ui.py

Run locally for LAN testing:
  python relay.py
"""
import os, socket, threading, json, random, time

rooms      = {}    # code -> host socket
lock       = threading.Lock()

queue_list = []    # list of {sock, name, is_admin, at}
queue_lock = threading.Lock()


def _gen_code():
    for _ in range(10_000):
        c = f"{random.randint(0, 9999):04d}"
        with lock:
            if c not in rooms:
                return c
    raise RuntimeError("out of room codes")


def _forward(src, dst):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try: s.close()
            except: pass


def _bridge(a, b):
    threading.Thread(target=_forward, args=(a, b), daemon=True).start()
    threading.Thread(target=_forward, args=(b, a), daemon=True).start()


def _read_line(sock):
    """Read one newline-terminated JSON line; return (parsed_dict, leftover_bytes)."""
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("disconnected during handshake")
        buf += chunk
    line, rest = buf.split(b"\n", 1)
    return json.loads(line), rest


def _send(sock, obj):
    sock.sendall(json.dumps(obj).encode() + b"\n")


def _send_queue_status():
    """Broadcast current queue to all waiting players; remove dead connections."""
    with queue_lock:
        snapshot = list(queue_list)
    players = [{"name": p["name"], "is_admin": p["is_admin"], "wait": int(time.time() - p["at"])}
               for p in snapshot]
    dead = []
    for p in snapshot:
        try:
            _send(p["sock"], {"queue": players})
        except OSError:
            dead.append(p)
    if dead:
        with queue_lock:
            for p in dead:
                if p in queue_list:
                    queue_list.remove(p)


def _try_match():
    """Pop the first two queued players atomically. Returns (p1, p2) or (None, None)."""
    with queue_lock:
        if len(queue_list) >= 2:
            return queue_list.pop(0), queue_list.pop(0)
    return None, None


def _queue_status_loop():
    while True:
        time.sleep(2)
        _send_queue_status()


def handle(sock, addr):
    try:
        msg, rest = _read_line(sock)
        action = msg.get("action", "")

        if action == "host":
            code = _gen_code()
            with lock:
                rooms[code] = sock
            _send(sock, {"code": code})
            print(f"[+] {addr[0]} hosted  room {code}")
            # Thread exits here; socket kept alive by rooms dict until joiner arrives.

        elif action == "join":
            code = str(msg.get("code", "")).zfill(4)
            with lock:
                host_sock = rooms.pop(code, None)
            if host_sock is None:
                _send(sock, {"error": "Room not found — check the code or ask host to restart"})
                sock.close()
                return
            print(f"[+] {addr[0]} joined  room {code}")
            try:
                _send(host_sock, {"joined": True})
            except OSError:
                _send(sock, {"error": "Host disconnected before you joined"})
                sock.close()
                return
            _send(sock, {"ok": True})
            if rest:                     # forward any bytes read past the handshake line
                host_sock.sendall(rest)
            _bridge(host_sock, sock)

        elif action == "queue":
            name     = str(msg.get("name", "Player"))[:20]
            is_admin = bool(msg.get("is_admin", False))
            entry    = {"sock": sock, "name": name, "is_admin": is_admin, "at": time.time()}
            with queue_lock:
                queue_list.append(entry)
            _send(sock, {"queued": True})
            _send_queue_status()
            print(f"[+] {addr[0]} queued as '{name}' (admin={is_admin})")

            p1, p2 = _try_match()
            if p1 and p2:
                try:
                    _send(p1["sock"], {"matched": True, "role": "host"})
                    _send(p2["sock"], {"matched": True, "role": "join"})
                except OSError as e:
                    print(f"[!] Match notify error: {e}")
                    return
                print(f"[+] Queue match: '{p1['name']}' vs '{p2['name']}'")
                _bridge(p1["sock"], p2["sock"])
            # else: thread exits; socket stays alive via queue_list reference

        else:
            sock.close()

    except Exception as e:
        print(f"[!] {addr}: {e}")
        try: sock.close()
        except: pass


def main():
    port = int(os.environ.get("PORT", 8765))
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(100)
    print(f"Chess relay listening on :{port}")
    threading.Thread(target=_queue_status_loop, daemon=True).start()
    while True:
        sock, addr = srv.accept()
        threading.Thread(target=handle, args=(sock, addr), daemon=True).start()


if __name__ == "__main__":
    main()
