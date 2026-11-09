"""Shared storage for Frameback. Used by frameback_server.py and frameback.py.

Layout inside the video folder (ROOT):
  review-data/stacks.json                {"stacks": {name: [file, ...]}, "last": file}
  review-data/<video>.notes.json         {"rev", "fps", "file", "notes": [...], "round": {...}, "status"}
  review-data/queue.jsonl                one line per "Send" click: {"file", "at"}
  review-data/history/                   every previous notes file (never deleted)
"""
import json, os, re, time

VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v", ".mkv")


def data_dir(root):
    d = os.path.join(root, "review-data")
    os.makedirs(d, exist_ok=True)
    return d


def safe_name(name):
    name = os.path.basename(name or "")
    if not name or name.startswith("."):
        raise ValueError("bad file name")
    return name


def doc_path(root, file):
    return os.path.join(data_dir(root), safe_name(file) + ".notes.json")


def stacks_path(root):
    return os.path.join(data_dir(root), "stacks.json")


def queue_path(root):
    return os.path.join(data_dir(root), "queue.jsonl")


def listener_path(root):
    return os.path.join(data_dir(root), "listener.json")


def listener_status(root, stale=15):
    """Is an AI listener alive? (heartbeat written every few seconds by `frameback.py listen`)"""
    d = read_json(listener_path(root), {})
    alive = d.get("state") == "listening" and time.time() - d.get("last_seen", 0) < stale
    return {"listening": alive, "agent": d.get("agent"), "last_seen": d.get("last_seen")}


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def backup(root, path):
    """Move the current file into review-data/history before it is replaced."""
    if not os.path.exists(path):
        return
    hist = os.path.join(data_dir(root), "history")
    os.makedirs(hist, exist_ok=True)
    rev = read_json(path, {}).get("rev", 0)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    os.replace(path, os.path.join(hist, f"{os.path.basename(path)}.rev{rev}.{stamp}.json"))


def load_doc(root, file):
    d = read_json(doc_path(root, file), {"rev": 0, "notes": []})
    d.setdefault("notes", [])
    return d


def save_doc(root, file, doc, expect_rev=None):
    """Save with a higher rev. Returns False if someone saved in between (expect_rev mismatch)."""
    p = doc_path(root, file)
    cur = read_json(p, {"rev": 0})
    if expect_rev is not None and cur.get("rev", 0) != expect_rev:
        return False
    doc["rev"] = max(doc.get("rev", 0), cur.get("rev", 0)) + 1
    doc["file"] = safe_name(file)
    backup(root, p)
    write_json(p, doc)
    return True


def update_doc(root, file, fn, tries=5):
    """Read, change with fn(doc), save. Retries if the player saved at the same moment."""
    for _ in range(tries):
        doc = load_doc(root, file)
        rev = doc.get("rev", 0)
        fn(doc)
        if save_doc(root, file, doc, expect_rev=rev):
            return doc
        time.sleep(0.2)
    raise RuntimeError("could not save: the notes file keeps changing")


def load_stacks(root):
    s = read_json(stacks_path(root), {})
    s.setdefault("stacks", {})
    s.setdefault("last", None)
    return s


def save_stacks(root, s):
    write_json(stacks_path(root), s)


def stack_of(stacks, file):
    for k, files in stacks["stacks"].items():
        if file in files:
            return k
    return None


def next_version_name(stacks, file):
    """'clip v7.mp4' -> 'clip v8.mp4'; 'clip.mp4' -> 'clip v2.mp4' (based on the stack's latest)."""
    key = stack_of(stacks, file)
    latest = stacks["stacks"][key][-1] if key else file
    n = len(stacks["stacks"][key]) + 1 if key else 2
    base, ext = os.path.splitext(latest)
    base = re.sub(r"\s+v\d+$", "", base)
    return f"{base} v{n}{ext}"
