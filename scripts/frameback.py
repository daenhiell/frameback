"""Frameback helper for any AI agent (Claude Code, Codex, Cursor, Gemini CLI...).

All commands take --root "<folder with the videos>" (default: current folder).

  start        start the server detached and check it answers (best for agents)
  serve        run the Frameback server in the foreground
  launcher     write a double-clickable "Frameback.bat" into the folder
  status       versions, open comments and Send rounds for every video
  wait         block until the user clicks Send, then print what was sent
  notes        list the open comments on a video (timecodes, frames, drawings, images)
  stills       save a still of each open comment's frame, with the drawing on it
  working      tell the player you started editing (locks commenting)
  reply        reply to a comment, optionally resolving it
  resolve      mark a comment resolved
  next-name    print the file name for the next version
  add-version  register a new version so the player opens and plays it
  done         finish the round with a short note
"""
import argparse, json, os, subprocess, sys, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import frameback_data as rd

AGENT = os.environ.get("FRAMEBACK_AGENT") or os.environ.get("REVIEW_AGENT", "Claude")


def now():
    return datetime.now().isoformat(timespec="seconds")


def fps_of(doc):
    return float(doc.get("fps") or 30)


def tc(frame, fps):
    r = round(fps)
    s, f = divmod(int(frame), r)
    return f"{s // 3600:02}:{s // 60 % 60:02}:{s % 60:02}:{f:02}"


def ordered(doc):
    """Same order and numbering (#1, #2...) as the player: by timecode, general comments first."""
    return sorted(doc["notes"], key=lambda n: (n.get("frame") if n.get("frame") is not None else -1, n.get("created", "")))


def find_note(doc, ref):
    notes = ordered(doc)
    if ref.startswith("#") or ref.isdigit():
        i = int(ref.lstrip("#")) - 1
        if 0 <= i < len(notes):
            return notes[i]
    for n in notes:
        if n["id"] == ref:
            return n
    sys.exit(f"No comment {ref}. Use the # number from `notes` or the comment id.")


def describe_ink(ink):
    out = []
    for s in ink or []:
        t = s.get("t", "pen")
        if t == "pen":
            pts = s.get("p") or []
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            if xs:
                out.append(f"pen stroke around x {min(xs):.2f}-{max(xs):.2f}, y {min(ys):.2f}-{max(ys):.2f}")
        else:
            (x1, y1), (x2, y2) = s["a"], s["b"]
            name = {"rect": "box", "ellipse": "circle", "arrow": "arrow"}.get(t, t)
            out.append(f"{name} from ({x1:.2f},{y1:.2f}) to ({x2:.2f},{y2:.2f})")
    return out


# ---------------- commands ----------------
def cmd_serve(a):
    srv = os.path.join(HERE, "frameback_server.py")
    # Never opens the system browser: the page belongs in the AI app's built-in browser.
    print(f"Open http://127.0.0.1:{a.port}/ in your AI app's built-in browser.", flush=True)
    sys.exit(subprocess.call([sys.executable, srv, "--root", a.root, "--port", str(a.port), "--agent", a.agent]))


def _alive(port, wait=0.0):
    import urllib.request
    end = time.time() + wait
    while True:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=2) as r:
                return r.status == 200
        except Exception:
            if time.time() >= end:
                return False
            time.sleep(0.5)


def _sandboxed():
    return any(os.environ.get(k) for k in ("CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED"))


def cmd_start(a):
    """Start the server detached (survives the agent's command ending) and check it answers."""
    url = f"http://127.0.0.1:{a.port}/"
    if _alive(a.port):
        import urllib.request
        try:
            with urllib.request.urlopen(url + "api/config", timeout=2) as r:
                root = json.load(r).get("root", "")
        except Exception:
            root = ""
        if root and os.path.normcase(os.path.abspath(root)) != os.path.normcase(os.path.abspath(a.root)):
            print(f"OTHER FOLDER: port {a.port} already serves {root}. Use --port {a.port + 1} for this folder.")
            sys.exit(4)
        print(f"OK already running: open {url} in your AI app's built-in browser.")
        return
    if _sandboxed():
        print("BLOCKED: this command runs inside the agent's sandbox, which firewalls local ports, so the "
              "browser would time out. Re-run this exact command outside the sandbox (Codex: request escalated "
              "permissions / sandbox_permissions=require_escalated), or ask the user to double-click Frameback.bat.")
        sys.exit(2)
    import socket
    try:
        with socket.socket() as t:
            t.bind(("127.0.0.1", a.port))
    except OSError:
        print(f"PORT BUSY: something holds port {a.port} but does not answer (often a server an agent started "
              "inside its sandbox). Kill the old python frameback_server.py / frameback.py serve processes, "
              "or pass --port 8766.")
        sys.exit(3)
    srv = os.path.join(HERE, "frameback_server.py")
    exe = sys.executable
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(w):
            exe = w
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED | NEW_GROUP | NO_WINDOW
    else:
        kw["start_new_session"] = True
    subprocess.Popen([exe, srv, "--root", a.root, "--port", str(a.port), "--agent", a.agent], **kw)
    if _alive(a.port, wait=10):
        print(f"OK started: open {url} in your AI app's built-in browser.")
    else:
        print(f"FAILED: server did not answer on {url} within 10s. If you run inside a sandbox, re-run outside it "
              "(Codex: escalated permissions), or ask the user to double-click Frameback.bat.")
        sys.exit(1)


def cmd_launcher(a):
    bat = os.path.join(a.root, "Frameback.bat")
    with open(bat, "w", encoding="utf-8") as f:
        f.write("@echo off\r\nrem Starts the Frameback server for the videos in this folder.\r\n"
                f"rem It does not open a browser: open http://127.0.0.1:{a.port}/ inside your AI app's built-in browser.\r\n"
                f'python "{os.path.join(HERE, "frameback_server.py")}" --root "%~dp0." --port {a.port} --agent "{a.agent}"\r\n')
    print(bat)


def cmd_status(a):
    s = rd.load_stacks(a.root)
    if not s["stacks"]:
        print("No videos reviewed yet in", a.root)
    for key, files in s["stacks"].items():
        print(f"{key}")
        for i, f in enumerate(files, 1):
            d = rd.load_doc(a.root, f)
            open_n = sum(1 for n in d["notes"] if not n.get("done"))
            r = d.get("round") or {}
            extra = f"  round: {r.get('state')}" if r else ""
            st = f"  status: {d['status']}" if d.get("status") else ""
            print(f"  v{i}  {f}  ({len(d['notes'])} comments, {open_n} open){st}{extra}")
    print("last opened:", s.get("last"))


def _beat(a, state="listening"):
    """Tell the player an AI is listening (it shows a badge next to Submit)."""
    rd.write_json(rd.listener_path(a.root), {"agent": a.agent, "state": state, "pid": os.getpid(), "last_seen": time.time()})


def _received(a, line):
    """Mark the submitted round as received so the player confirms it, then report it."""
    try:
        item = json.loads(line)
        def fn(d):
            r = d.get("round") or {}
            if r.get("state") in (None, "sent"):
                r.update({"state": "received", "received_at": now(), "by": a.agent})
                d["round"] = r
        rd.update_doc(a.root, item["file"], fn)
    except Exception as e:  # never let one bad line stop the listener
        print("WARN could not mark received:", e, flush=True)


def _new_lines(q, pos):
    with open(q, encoding="utf-8") as f:
        f.seek(pos)
        lines = [l for l in f.read().splitlines() if l.strip()]
        return lines, f.tell()


def cmd_listen(a):
    """Run in the background. Prints one 'SEND {...}' line per Submit (repeat clicks on the same
    video within a few seconds are merged), marks it received, and keeps a heartbeat for the player."""
    q = rd.queue_path(a.root)
    open(q, "a").close()
    pos = os.path.getsize(q)
    end = time.time() + a.timeout if a.timeout else None
    print(f"LISTENING for Submit in {a.root}", flush=True)
    last_beat = 0
    try:
        while True:
            if time.time() - last_beat > 4:
                _beat(a); last_beat = time.time()
            if os.path.getsize(q) > pos:
                time.sleep(1.5)  # let quick double clicks land, then merge them
                lines, pos = _new_lines(q, pos)
                seen = set()
                for line in lines:
                    item = json.loads(line)
                    if item.get("type") == "frameio":
                        print("FRAMEIO " + line + "\n"
                              "DO import this Frame.io link now (see SKILL.md section 'Frame.io import'): open it, download the video into the root, "
                              "write the comments to a JSON file, run import-notes. Do not ask first.", flush=True)
                        if a.once:
                            return
                        continue
                    f = item.get("file")
                    if f in seen:
                        continue
                    seen.add(f)
                    _received(a, line)
                    # the comments themselves come with the Submit, so the agent can start editing at once
                    block = ["SEND " + line]
                    try:
                        block += ["NOTE " + l for l in notes_lines(a.root, f)]
                    except Exception as e:
                        block.append(f"WARN could not read the comments: {e}")
                    block.append(f'DO start editing now: stills "{f}", working, edit, reply, add-version, done (see SKILL.md section 3). Do not ask first.')
                    print("\n".join(block), flush=True)
                if a.once:
                    return
            if end and time.time() > end:
                print("TIMEOUT no Submit yet", flush=True)
                return
            time.sleep(1)
    finally:
        _beat(a, "stopped")


def cmd_wait(a):
    a.once = True
    cmd_listen(a)


def notes_lines(root, file, include_done=False):
    """The comments on a video as readable lines (shared by `notes` and the listener)."""
    d = rd.load_doc(root, file)
    fps = fps_of(d)
    att_dir = os.path.join(rd.data_dir(root), "attachments")
    out, shown = [], 0
    for i, n in enumerate(ordered(d), 1):
        if n.get("done") and not include_done:
            continue
        shown += 1
        f = n.get("frame")
        if f is None:
            where = "general (whole video)"
        elif n.get("end") is not None:
            where = f"{tc(f, fps)} -> {tc(n['end'], fps)}  frames {f}-{n['end']}  ({f / fps:.3f}s-{(n['end'] + 1) / fps:.3f}s)"
        else:
            where = f"{tc(f, fps)}  frame {f}  ({f / fps:.3f}s)"
        out.append(f"#{i}  [{n['id']}]  {where}{'  [resolved]' if n.get('done') else ''}")
        out.append(f"    {n.get('author', '?')}: {n.get('text') or '(no text)'}")
        for line in describe_ink(n.get("ink")):
            out.append(f"    drawing: {line}  (0-1 = fraction of frame width/height)")
        if n.get("image"):
            import base64
            os.makedirs(att_dir, exist_ok=True)
            p = os.path.join(att_dir, f"{n['id']}.jpg")
            with open(p, "wb") as fh:
                fh.write(base64.b64decode(n["image"].split(",", 1)[1]))
            out.append(f"    attached image: {p}")
        for r in n.get("replies") or []:
            out.append(f"    reply {r.get('author')}: {r.get('text')}")
    r = d.get("round")
    out.append(f"{shown} comment(s). fps {fps:g}. round: {r.get('state') if r else 'none'}")
    return out


def cmd_notes(a):
    print("\n".join(notes_lines(a.root, a.file, a.all)))


def cmd_stills(a):
    from PIL import Image, ImageDraw
    d = rd.load_doc(a.root, a.file)
    fps = fps_of(d)
    out = a.out or os.path.join(rd.data_dir(a.root), "stills", os.path.splitext(rd.safe_name(a.file))[0])
    os.makedirs(out, exist_ok=True)
    src = os.path.join(a.root, a.file)
    for i, n in enumerate(ordered(d), 1):
        if (n.get("done") and not a.all) or n.get("frame") is None:
            continue
        p = os.path.join(out, f"{i:02}_f{n['frame']}.jpg")
        t = (n["frame"] + 0.5) / fps
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.4f}", "-i", src, "-frames:v", "1", "-q:v", "3", p], check=True)
        if n.get("ink"):
            im = Image.open(p).convert("RGB")
            W, H = im.size
            dr = ImageDraw.Draw(im)
            lw = max(3, W // 150)
            for s in n["ink"]:
                c = s.get("c", "#ff3b6b")
                if s.get("t", "pen") == "pen":
                    pts = [(x * W, y * H) for x, y in s.get("p") or []]
                    if len(pts) > 1:
                        dr.line(pts, fill=c, width=lw, joint="curve")
                else:
                    (x1, y1), (x2, y2) = (s["a"][0] * W, s["a"][1] * H), (s["b"][0] * W, s["b"][1] * H)
                    box = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
                    if s["t"] == "rect":
                        dr.rectangle(box, outline=c, width=lw)
                    elif s["t"] == "ellipse":
                        dr.ellipse(box, outline=c, width=lw)
                    else:
                        dr.line([(x1, y1), (x2, y2)], fill=c, width=lw)
            im.save(p, quality=90)
        print(f"#{i}  {p}")


def set_round(a, state, note=None):
    def fn(d):
        r = d.get("round") or {}
        r.update({"state": state, "at": now()})
        if note:
            r["note"] = note
        d["round"] = r
    rd.update_doc(a.root, a.file, fn)
    print(f"round -> {state}")


def cmd_working(a):
    set_round(a, "working")


def cmd_done(a):
    set_round(a, "done", a.note)


def cmd_reply(a):
    def fn(d):
        n = find_note(d, a.ref)
        n.setdefault("replies", []).append({"id": f"r{int(time.time() * 1000):x}", "author": a.agent, "text": a.text, "created": now()})
        if a.resolve:
            n["done"] = True
    rd.update_doc(a.root, a.file, fn)
    print("replied" + (" and resolved" if a.resolve else ""))


def cmd_import_notes(a):
    """Merge comments copied from another review tool (Frame.io) into a video's notes.
    JSON: {"fps": 24, "source": "frameio", "notes": [{"id", "author", "text", "seconds" | "frame",
    "end_seconds" | "end", "done", "created", "replies": [{"author", "text", "created"}]}]}
    Re-running skips comments already imported (matched by source id) but adds their new replies."""
    with open(a.json, encoding="utf-8") as f:
        src = json.load(f)
    tag = src.get("source", "frameio")
    added = updated = 0

    def fn(d):
        nonlocal added, updated
        if src.get("fps") and not d.get("fps"):
            d["fps"] = float(src["fps"])
        fps = fps_of(d)
        have = {n.get("src"): n for n in d["notes"] if n.get("src")}
        removed = set(d.get("removed") or [])  # deleted in the player: don't bring them back

        def frame(x, sec_key, frame_key):
            if x.get(frame_key) is not None:
                return int(x[frame_key])
            if x.get(sec_key) is not None:
                return int(round(float(x[sec_key]) * fps))
            return None

        for x in src.get("notes", []):
            key = f"{tag}:{x['id']}"
            if key in removed:
                continue
            replies = [{"id": f"{tag}-r{i}", "author": r.get("author") or "Frame.io", "text": r.get("text", ""),
                        "created": r.get("created") or now()} for i, r in enumerate(x.get("replies") or [])]
            if key in have:
                n = have[key]
                old = {(r["author"], r["text"]) for r in n.get("replies", [])}
                new = [r for r in replies if (r["author"], r["text"]) not in old and f"{key}|{r['author']}|{r['text']}" not in removed]
                if new:
                    n.setdefault("replies", []).extend(new); updated += 1
                continue
            n = {"id": f"fio{int(time.time() * 1000):x}{added}", "src": key, "author": x.get("author") or "Frame.io",
                 "text": x.get("text", ""), "frame": frame(x, "seconds", "frame"), "created": x.get("created") or now(),
                 "done": bool(x.get("done")), "replies": replies}
            end = frame(x, "end_seconds", "end")
            if end is not None and n["frame"] is not None and end > n["frame"]:
                n["end"] = end
            d["notes"].append(n); added += 1

    rd.update_doc(a.root, a.file, fn)
    # put it in Frameback directly: register the video and tell the open player to show it
    file = rd.safe_name(a.file)
    s = rd.load_stacks(a.root)
    if not rd.stack_of(s, file):
        s["stacks"][os.path.splitext(file)[0]] = [file]
    s["last"] = file
    s["open"] = {"file": file, "at": now(), "note": f"{added} new comment(s) from Frame.io" + (f", {updated} with new replies" if updated else "")}
    rd.save_stacks(a.root, s)
    print(f"imported {added} new comments, {updated} got new replies. The open player will switch to {file}.")


def cmd_resolve(a):
    rd.update_doc(a.root, a.file, lambda d: find_note(d, a.ref).__setitem__("done", not a.reopen))
    print("reopened" if a.reopen else "resolved")


def cmd_next_name(a):
    print(rd.next_version_name(rd.load_stacks(a.root), rd.safe_name(a.file)))


def cmd_add_version(a):
    s = rd.load_stacks(a.root)
    old, new = rd.safe_name(a.file), rd.safe_name(a.new)
    if not os.path.isfile(os.path.join(a.root, new)):
        sys.exit(f"{new} is not in {a.root}")
    key = rd.stack_of(s, old) or os.path.splitext(old)[0]
    s["stacks"].setdefault(key, [old])
    for k in s["stacks"]:
        s["stacks"][k] = [f for f in s["stacks"][k] if f != new]
    s["stacks"][key].append(new)
    s["last"] = new
    rd.save_stacks(a.root, s)
    print(f"{new} added as v{len(s['stacks'][key])} of {key}. The open player will switch to it and play.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=os.getcwd(), help="folder with the videos")
    p.add_argument("--agent", default=AGENT, help="your name on replies and the Send button (default: $FRAMEBACK_AGENT or Claude)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=8765); s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("start", help="start the server detached and check it answers (use this from agents)"); s.add_argument("--port", type=int, default=8765); s.set_defaults(fn=cmd_start)
    s = sub.add_parser("launcher"); s.add_argument("--port", type=int, default=8765); s.set_defaults(fn=cmd_launcher)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("listen", help="background listener: heartbeat + one SEND line per Submit"); s.add_argument("--timeout", type=float, default=0, help="seconds, 0 = forever"); s.set_defaults(fn=cmd_listen, once=False)
    s = sub.add_parser("wait", help="like listen, but exits after the first Submit"); s.add_argument("--timeout", type=float, default=0, help="seconds, 0 = forever"); s.set_defaults(fn=cmd_wait)
    for name, fn in (("notes", cmd_notes), ("stills", cmd_stills)):
        s = sub.add_parser(name); s.add_argument("file"); s.add_argument("--all", action="store_true", help="include resolved")
        if name == "stills":
            s.add_argument("--out")
        s.set_defaults(fn=fn)
    s = sub.add_parser("working"); s.add_argument("file"); s.set_defaults(fn=cmd_working)
    s = sub.add_parser("done"); s.add_argument("file"); s.add_argument("--note", required=True); s.set_defaults(fn=cmd_done)
    s = sub.add_parser("reply"); s.add_argument("file"); s.add_argument("ref", help="#number or id"); s.add_argument("text"); s.add_argument("--resolve", action="store_true"); s.set_defaults(fn=cmd_reply)
    s = sub.add_parser("import-notes", help="merge comments from Frame.io (JSON) into a video's notes"); s.add_argument("file"); s.add_argument("json"); s.set_defaults(fn=cmd_import_notes)
    s = sub.add_parser("resolve"); s.add_argument("file"); s.add_argument("ref"); s.add_argument("--reopen", action="store_true"); s.set_defaults(fn=cmd_resolve)
    s = sub.add_parser("next-name"); s.add_argument("file"); s.set_defaults(fn=cmd_next_name)
    s = sub.add_parser("add-version"); s.add_argument("file", help="the version the comments were on"); s.add_argument("new"); s.set_defaults(fn=cmd_add_version)

    a = p.parse_args()
    a.root = os.path.abspath(a.root)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a.fn(a)


if __name__ == "__main__":
    main()
