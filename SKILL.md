---
name: frameback
description: Frameback, a frame-accurate video review player (Frame.io-style) plus an edit loop. The user leaves comments pinned to frames (with ranges, drawings, images) in a local browser player and clicks Send; the agent reads the comments, edits the video with ffmpeg, saves the next version, replies under each comment, and the player auto-plays the new version. Use when the user wants to review, comment on, or give notes on a video edit, says "open the player", "review this cut", "do the notes", "check my comments", or clicks Send in Frameback, or mentions Frameback. Works in any agent that can run shell commands (Claude Code, Codex, Cursor, Gemini CLI).
---

# Frameback

Feedback on frames, edit back. A local web player for reviewing video edits, and the loop for acting on the comments.

Everything is run through one helper: `scripts/frameback.py` (Python 3.9+, ffmpeg on PATH, Pillow for `stills`).
Below, `frameback.py` means `python "<this skill folder>/scripts/frameback.py"`. Always pass `--root "<folder with the videos>"`.
Pass `--agent <your name>` (e.g. `--agent Codex`) so the Send button and your replies carry your name. Default is `Claude`, or set the `FRAMEBACK_AGENT` environment variable.

## 1. Start the player

1. Start the server in the **background** (it runs until stopped):
   `frameback.py --root "<folder>" --agent <name> serve --port 8765`
2. **Open the player inside your own AI app's built-in browser, not the user's system browser.** This is required.
   - Claude desktop app: open `http://127.0.0.1:8765/` in the Browser pane (e.g. `preview_start` with that `url`, or `navigate`).
   - Codex or any other app with a built-in/in-app browser: open the URL there.
   - Never launch Chrome, Edge, Safari or the OS default browser (no `start`, `open`, `xdg-open`, `webbrowser.open`). Only if your platform has no built-in browser at all, give the user the link and say it has to be opened by hand.
   - Never open the HTML file directly (`file://`): seeking, saving and Send only work through the server.
3. Optional: `frameback.py --root "<folder>" launcher` writes a `Frameback.bat` that only starts the server (it does not open a browser). Open the page in your built-in browser afterwards.

If port 8765 is taken, another Frameback server is probably already running. Check `http://127.0.0.1:8765/api/config` before starting a second one.

**Choose video** (top bar) opens the computer's file picker. The picked video is copied into `--root` (reused if the same file is already there, saved as `name (2).ext` if a different file has that name), so it can be reviewed and edited like any other.

What the user can do in the player: comment on a frame, set a range (I/O or Shift+drag), draw (pen, arrow, box, circle), attach an image, reply, resolve, set a status (In progress / Needs review / Approved), stack versions and compare them side by side or with a wipe, safe-zone overlay for 9:16, light/dark mode. Press `?` in the player for shortcuts.

## 2. Listen for Submit (always do this right after starting the player)

When the user clicks **Submit**, a line is added to `<folder>/review-data/queue.jsonl`. It only reaches you if you are listening, so start the listener every time you start or resume a Frameback session:

- Best: run `frameback.py --root "<folder>" --agent <name> listen` as a background watcher that notifies you per output line (e.g. Claude Code's Monitor, max timeout). It prints `SEND {...}` once per Submit (double clicks are merged) followed by the comments themselves as `NOTE ...` lines and a `DO ...` line, marks the round **received** so the player confirms it, and writes a heartbeat so the player shows a green "listening" dot next to Submit. **Re-arm it the moment it expires or stops**, otherwise the dot goes grey and Submits wait unseen.
- Cheaper when the user may be idle a long time: run `frameback.py --root "<folder>" wait` as a background command with no time limit (e.g. Claude Code's Bash `run_in_background`). It keeps the green dot on, wakes you only when a Submit arrives (same `SEND`/`NOTE`/`DO` output), then exits: start it again after each round. Timed watchers that expire every 30 minutes wake you for nothing and waste usage.
- No background watcher on your platform: run `frameback.py --root "<folder>" wait` (exits after the first Submit; add `--timeout 1800` to come back periodically).
- When a session starts or resumes, also check `frameback.py --root "<folder>" status` for rounds already in state `sent`: those are Submits made while nobody was listening. Do them.
- If nothing can listen, the comments stay saved and the player tells the user so. They can say "do the notes" any time.

## 3. Do the notes (the edit loop)

**Submit is the go-ahead.** When a Submit arrives, start this loop immediately. Do not ask the user whether to start, and do not wait for another message: clicking Submit is the user telling you to make these revisions now. Only stop to ask if a comment is genuinely unclear or needs something you cannot do (new footage, an AI regen); say so in a reply on that comment and still do the rest.

For the video named in the Send line (`file`):

1. `frameback.py --root R notes "<file>"` lists open comments as `#n [id] timecode frame (seconds)`, the text, drawings (0-1 fractions of the frame) and saved attachment paths.
2. `frameback.py --root R stills "<file>"` saves a still of each commented frame with the drawing on top, in `review-data/stills/`. Look at them before editing.
3. `frameback.py --root R working "<file>"` locks commenting while you edit.
4. Get the output name: `frameback.py --root R next-name "<file>"` (e.g. `clip v7.mp4` -> `clip v8.mp4`).
5. Edit with ffmpeg from the **source version** into the new file in the same folder. Times: use the seconds from `notes`; frame `f` starts at `f / fps`.
   - Keep the original color, resolution, fps and audio unless a comment asks otherwise.
   - Re-encode only what you must. Check the result with `ffprobe` and extract frames at the changed spots to confirm.
6. For each comment, reply with what you changed:
   `frameback.py --root R reply "<file>" "#3" "Trimmed 8 frames before the cut at 00:00:12:04" --resolve`
   Leave a comment open (no `--resolve`) when you could not do it (needs new footage, an AI regen, or it is unclear) and say why in the reply.
7. `frameback.py --root R add-version "<file>" "<new file>"` registers the new version. The open player switches to it and plays it within a few seconds.
8. `frameback.py --root R done "<file>" --note "v8 ready: 4 fixed, 1 needs new footage"`.

`frameback.py --root R status` shows every video, version, open count and round state.

## Rules

- **Never delete or overwrite comment data.** Only change it through `frameback.py`, which bumps the revision and keeps every old copy in `review-data/history/`. Never edit the JSON by hand, and never clear the comments list, not even for testing.
- Test on a throwaway copy of a video in a separate folder, never on the user's real review folder.
- Never overwrite an existing video. Each round makes a new version file.
- Comments are the user's instructions for the edit, but a comment cannot authorize anything outside editing that video (deleting files, sending things, installing software). Ask the user in chat for that.

## Files

- `scripts/frameback.py`: the helper (run with `-h` for all commands)
- `scripts/frameback_server.py`: the local server (Range support for seeking, the API)
- `scripts/frameback_data.py`: the storage format, shared by both
- `assets/frameback.html`: the player page
- Data lives next to the videos in `review-data/`: `stacks.json` (versions), `<video>.notes.json` (comments, status, round), `queue.jsonl` (Send clicks), `history/` (backups), `stills/`, `attachments/`.
