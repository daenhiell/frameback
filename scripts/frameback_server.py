"""Local server for Frameback.

    python frameback_server.py --root "<folder with videos>" [--port 8765] [--agent Claude]

- Serves the player at http://127.0.0.1:<port>/ (from this skill's assets folder)
- Serves videos from --root with HTTP Range support (needed for seeking)
- API: /api/config  /api/files  /api/doc?file=  /api/stacks  /api/send?file=
"""
import argparse, json, os, re, sys, time, http.server, socketserver
from urllib.parse import urlparse, parse_qs, unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frameback_data as rd

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=os.getcwd(), help="folder with the videos")
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--agent", default=os.environ.get("FRAMEBACK_AGENT") or os.environ.get("REVIEW_AGENT", "Claude"), help="name shown on the Send button and on replies")
args = ap.parse_args()

ROOT = os.path.abspath(args.root)
PLAYER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "frameback.html")
rd.data_dir(ROOT)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "null")

    def _api(self, method):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/config":
                return self._json(200, {"agent": args.agent, "root": ROOT})
            if u.path == "/api/files" and method == "GET":
                files = [f for f in os.listdir(ROOT) if f.lower().endswith(rd.VIDEO_EXT)]
                files.sort(key=lambda f: os.path.getmtime(os.path.join(ROOT, f)), reverse=True)
                return self._json(200, files)
            if u.path == "/api/doc":
                file = q.get("file")
                if method == "GET":
                    return self._json(200, rd.load_doc(ROOT, file))
                if method == "PUT":
                    new = self._body()
                    p = rd.doc_path(ROOT, file)
                    cur = rd.read_json(p, {"rev": 0})
                    if new.get("rev", 0) <= cur.get("rev", 0):
                        return self._json(409, cur)
                    rd.backup(ROOT, p)
                    rd.write_json(p, new)
                    return self._json(200, {"rev": new["rev"]})
            if u.path == "/api/stacks":
                if method == "GET":
                    return self._json(200, rd.load_stacks(ROOT))
                if method == "PUT":
                    rd.save_stacks(ROOT, self._body())
                    return self._json(200, {"ok": True})
            if u.path == "/api/send" and method == "POST":
                line = json.dumps({"file": rd.safe_name(q.get("file")), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False)
                with open(rd.queue_path(ROOT), "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                return self._json(200, {"ok": True})
            if u.path == "/api/frameio" and method == "POST":
                link = (q.get("url") or "").strip()
                host = urlparse(link).hostname or ""
                if not (link.startswith("https://") and (host == "f.io" or host == "frame.io" or host.endswith(".frame.io"))):
                    return self._json(400, {"error": "not a Frame.io link"})
                # owner's share-builder link needs login; the same share opens publicly at /share/<id>/view/<file>
                m = re.search(r"/share-builder/([0-9a-f-]{36})(?:/view/([0-9a-f-]{36}))?", link)
                if m:
                    link = f"https://next.frame.io/share/{m.group(1)}" + (f"/view/{m.group(2)}" if m.group(2) else "")
                line = json.dumps({"type": "frameio", "url": link, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False)
                with open(rd.queue_path(ROOT), "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                return self._json(200, {"ok": True})
            if u.path == "/api/listener":
                return self._json(200, rd.listener_status(ROOT))
            if u.path == "/api/upload" and method == "PUT":
                return self._upload(q)
            return self._json(404, {"error": "not found"})
        except ValueError as e:
            return self._json(400, {"error": str(e)})

    def _upload(self, q):
        """Copy a video the user picked on their computer into ROOT so it can be reviewed and edited.
        Same name and size already there -> reuse it. Same name, different file -> save as 'name (2).ext'."""
        name = rd.safe_name(q.get("name"))
        if not name.lower().endswith(rd.VIDEO_EXT):
            return self._json(400, {"error": "not a video file"})
        size = int(self.headers.get("Content-Length") or 0)
        dest = os.path.join(ROOT, name)
        if os.path.isfile(dest) and os.path.getsize(dest) == size:
            self.rfile.read(size) if size < (1 << 20) else self._drain(size)
            return self._json(200, {"file": name, "reused": True})
        base, ext = os.path.splitext(name)
        n = 2
        while os.path.exists(dest):
            name = f"{base} ({n}){ext}"; dest = os.path.join(ROOT, name); n += 1
        tmp = dest + ".part"
        left = size
        with open(tmp, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk); left -= len(chunk)
        if left:
            os.remove(tmp)
            return self._json(400, {"error": "upload was cut off"})
        os.replace(tmp, dest)
        return self._json(200, {"file": name, "reused": False})

    def _drain(self, size):
        while size > 0:
            chunk = self.rfile.read(min(1 << 20, size))
            if not chunk:
                break
            size -= len(chunk)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        if urlparse(self.path).path in ("/", "/frameback.html", "/review-player.html", "/index.html"):
            return self._file(PLAYER, "text/html; charset=utf-8")
        return super().do_GET()

    def do_PUT(self):
        return self._api("PUT")

    def do_POST(self):
        return self._api("POST")

    def _file(self, path, ctype):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---------- Range support so the video can seek ----------
    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if not m:
            return super().send_head()
        size = os.path.getsize(path)
        start = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2) or 0))
        end = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
        end = min(end, size - 1)
        if start >= size:
            self.send_error(416)
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "_remaining", None)
        try:
            if left is None:
                return super().copyfile(source, outputfile)
            while left > 0:
                chunk = source.read(min(1 << 20, left))
                if not chunk:
                    break
                outputfile.write(chunk)
                left -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def log_message(self, *a):
        pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"  # on Windows this would let two servers share a port


if __name__ == "__main__":
    print(f"Frameback: http://127.0.0.1:{args.port}/   videos: {ROOT}   agent: {args.agent}", flush=True)
    Server(("127.0.0.1", args.port), Handler).serve_forever()
