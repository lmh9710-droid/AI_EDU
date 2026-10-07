import json
import socket

import config as C


class HubClient:
    """Rust 인터록 허브 Unix 소켓 클라이언트 (JSON 한 줄 요청/응답)."""

    def __init__(self, path=C.HUB_SOCK, timeout=2.0):
        self.path, self.timeout, self.sock, self.rfile = path, timeout, None, None

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        finally:
            self.sock, self.rfile = None, None

    def send(self, src, kind, code, value=0.0, detail=""):
        msg = json.dumps(dict(src=src, kind=kind, code=code, value=float(value), detail=detail), ensure_ascii=False) + "\n"
        for _ in range(2):
            try:
                if self.sock is None:
                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.sock.settimeout(self.timeout)
                    self.sock.connect(self.path)
                    self.rfile = self.sock.makefile("r", encoding="utf-8")
                self.sock.sendall(msg.encode("utf-8"))
                line = self.rfile.readline()
                if not line:
                    raise ConnectionError("hub closed")
                return json.loads(line)
            except (OSError, ConnectionError, ValueError):
                self.close()
        return None
