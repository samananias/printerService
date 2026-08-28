"""
hello_server.py — Phase 1 throwaway server (P1: Networking Fundamentals)

Educational only. Uses ONLY Python's standard library (http.server) so you
can see HTTP with zero frameworks in the way. Delete this file once Phase 2's
FastAPI /health endpoint works.

What it teaches (README Section 15, in order):
- IP address: which MACHINE the data goes to (printed below).
- Port: which PROGRAM on that machine gets the data (8000 here).
- TCP: handled for us — http.server accepts connections and never loses bytes.
- HTTP: a request has a method (GET) and a path (/); a response has a status
  code (200 = OK) and a body (the HTML below).

Run:     python hello_server.py
Then:    open http://localhost:8000 in THIS PC's browser (tests the server)
And:     open http://<this-pc-ip>:8000 on your PHONE (tests the network path)
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import socket

PORT = 8000


def local_ips():
    """Best-effort list of this PC's LAN IPv4 addresses (e.g. 192.168.1.10)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if "." in ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (
            "<h1>👋 Hello from the print-server PC!</h1>"
            "<p>If you can read this on your phone, the network path works:</p>"
            "<pre>Phone → Wi-Fi → Router → This PC (port 8000) → this server</pre>"
        ).encode("utf-8")
        self.send_response(200)  # 200 = OK
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Show who asked, so you can see the phone's request arrive live.
        print(f"[request] {self.address_string()} - {fmt % args}")


def main():
    print("=" * 56)
    print(f"Hello server (Phase 1) — stdlib http.server, port {PORT}")
    print(f"  From this PC:  http://localhost:{PORT}")
    for ip in local_ips():
        print(f"  From phone:    http://{ip}:{PORT}")
    print("  (phone must be on the SAME Wi-Fi network)")
    print("Ctrl+C to stop.")
    print("=" * 56)

    # "0.0.0.0" = listen on ALL network interfaces, not just localhost.
    # This is what makes the PC reachable from the phone. Forgetting this
    # (or the equivalent in uvicorn) is the classic Phase 2 mistake.
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
