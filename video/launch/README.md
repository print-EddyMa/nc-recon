# Groma launch film

A 72 second launch film made only from real material: Civil Air Patrol photos
from two days after Hurricane Helene, NC OneMap before and after imagery, the
Swannanoa assessment's own footprints and calls, the 2025 lidar ground change,
and the Groma app. Original score; open-licence voice. Sources and licences:
[CREDITS.md](CREDITS.md).

## Shots

| Time | Picture | Voice / text |
|---|---|---|
| 0 to 5 | CAP oblique, Swannanoa, 28 Sep 2024 | "Swannanoa, North Carolina" |
| 5 to 12 | Two CAP obliques, debris and river | "After a disaster, every county needs the same answer. Fast." |
| 12 to 20 | Before / after swipe, a manufactured-home park gone; the model's footprints | "Which buildings are damaged? And how badly?" |
| 20 to 26 | All 893 Swannanoa structures by level | "Groma reads every structure. Before, and after." |
| 26 to 32 | Lidar ground change, scour and deposit, flagged buildings | "Even the ground itself." |
| 32 to 38 | The app: overview, Swannanoa, review queue | Lower thirds: FEMA disaster number; 893 buildings in 88 seconds; hard calls first |
| 38 to 48 | Verify with a Civil Air Patrol photo | "The hard calls go to people, who judge the evidence without seeing the model's answer." |
| 48 to 55 | 15 of 19, with its caveat | silence |
| 55 to 60 | FEMA damage survey columns, real rows, formats | "Out in the formats responders already use." |
| 60 to 65.5 | Who it is for | "For emergency managers. Insurers. And the National Guard." |
| 65.5 to 72 | The groma's plumb lines settle; wordmark | "Groma. Disaster assessment, building by building." |

## Build

Run from the repo root with the pipeline venv (`pipeline/.venv/bin/python`) unless noted.

1. `python video/launch/fetch_assets.py <cap keys...>`: plates and Civil Air Patrol originals.
2. `python video/launch/lidar_plate.py`: lidar relief and change plates.
3. `python video/launch/prep.py`: reduced photos, footprint overlays, survey rows.
4. `python3 video/launch/capture.py`: app screens. Start the scratch servers first
   (`.claude/launch.json`: `ncrecon-api-photos` on :8003 with a scratch registry,
   jobs, truth, labels, audit and cache, and `ncrecon-web-photos` on :5176).
5. Voice: Kokoro in its own venv (see CREDITS.md). Lines live in `assets/vo/lines.json`.
6. `python3 video/launch/compose.py`, then `python3 video/launch/render.py`
   (`--stills 3,16.5` for review frames): picture, about 6 minutes.
7. `python video/launch/score.py`: score, voice placement, ducking, -16 LUFS
   master, and the final mux to `build/groma_launch.mp4`.
