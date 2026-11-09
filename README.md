# Frameback

Feedback on frames, edit back. A local, Frame.io-style video review player plus an AI edit loop.

You leave comments pinned to frames (ranges, drawings, images) in the player and click **Submit**. Your AI agent reads the comments, edits the video with ffmpeg, saves the next version, replies under each comment, and the player auto-plays the new version.

Works as a skill in any agent that can run shell commands: Claude Code, Codex, Cursor, Gemini CLI.

## Requirements

- Python 3.9+
- ffmpeg and ffprobe on PATH
- Pillow (`pip install pillow`), only for `stills`

## Install as a skill

Clone into your agent's skills folder:

```bash
git clone https://github.com/daenhiell/frameback ~/.claude/skills/frameback
```

For Codex use `~/.codex/skills/frameback`. Other agents: tell them to read `SKILL.md` and follow it.

## Quick start

```bash
python scripts/frameback.py --root "/path/to/videos" --agent Claude serve --port 8765
```

Open `http://127.0.0.1:8765/` in your AI app's built-in browser. Then ask your agent to listen for Submit (see `SKILL.md`).

## Privacy

Everything runs locally. Videos and comments stay in your folder (`review-data/` next to the videos) and are never uploaded. This repo contains only the tool.

## Files

- `SKILL.md`: instructions for the agent
- `assets/frameback.html`: the player
- `scripts/frameback.py`: the CLI (`-h` for all commands)
- `scripts/frameback_server.py`: the local server
- `scripts/frameback_data.py`: the storage format
