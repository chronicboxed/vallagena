#!/usr/bin/env python3
"""
generate_m3u.py
================

Builds a Kodi/VLC/Jellyfin-compatible extended M3U (.m3u / .m3u8) playlist
for movies and TV series.

Two ways to feed it content:

1) SCAN a local folder of video files
   ----------------------------------
   python generate_m3u.py scan --root "/path/to/media" --out playlist.m3u \
       --base-url "https://yourserver.com/media"

   Expected folder layout (flexible, but this works best):

       media/
         Movies/
           Some Movie (2024)/
             Some Movie (2024).mp4
             poster.jpg            <- optional, used as tvg-logo
         Series/
           Some Show/
             Season 01/
               Some Show S01E01.mp4
               Some Show S01E02.mp4
             poster.jpg            <- optional

   Series episodes are auto-detected via "SxxEyy" in the filename and
   grouped together under the show name (group-title).

2) JSON source list (e.g. your own licensed/remote URLs)
   -------------------------------------------------------
   python generate_m3u.py json --input sources.json --out playlist.m3u

   sources.json format:
   [
     {
       "title": "Some Movie (2024)",
       "url": "https://example.com/movie.mp4",
       "group": "Movies",
       "logo": "https://example.com/poster.jpg"
     },
     {
       "title": "Some Show S01E01 - Pilot",
       "url": "https://example.com/show-s01e01.mp4",
       "group": "Some Show",
       "logo": "https://example.com/poster.jpg"
     }
   ]

Only point this at content you actually have the rights to stream
(your own media, public domain works, or a licensed service's URLs).
"""

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm", ".ts"}
EPISODE_PATTERN = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})")
POSTER_NAMES = {"poster.jpg", "poster.png", "folder.jpg", "folder.png", "cover.jpg", "cover.png"}


def find_poster(folder: Path):
    """Look for a poster/cover image directly inside a folder."""
    for name in POSTER_NAMES:
        candidate = folder / name
        if candidate.exists():
            return candidate
    return None


def to_url(base_url: str, local_path: Path, root: Path) -> str:
    """Turn a local file path into a URL relative to base_url, URL-encoding each segment."""
    rel = local_path.relative_to(root)
    encoded_parts = [urllib.parse.quote(part) for part in rel.parts]
    return base_url.rstrip("/") + "/" + "/".join(encoded_parts)


def scan_folder(root: Path, base_url: str):
    """
    Walk the root folder and produce a list of entries:
    { "title": ..., "url": ..., "group": ..., "logo": ... }
    """
    entries = []

    for video_file in sorted(root.rglob("*")):
        if not video_file.is_file() or video_file.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        parent = video_file.parent
        poster = find_poster(parent) or find_poster(parent.parent)
        logo_url = to_url(base_url, poster, root) if poster else ""

        episode_match = EPISODE_PATTERN.search(video_file.stem)

        if episode_match:
            # Treat as a series episode. Group title = show folder name.
            # Walk up until we're out of a "Season XX" style folder, if present.
            show_folder = parent
            if re.match(r"(?i)^season\s*\d+$", show_folder.name):
                show_folder = show_folder.parent

            group = show_folder.name
            title = video_file.stem.replace(".", " ").replace("_", " ").strip()
        else:
            # Treat as a standalone movie. Group title = parent category
            # (e.g. "Movies"), or just the folder name if there's no clear category.
            group = parent.parent.name if parent.parent != root else "Movies"
            title = video_file.stem.replace(".", " ").replace("_", " ").strip()

        entries.append({
            "title": title,
            "url": to_url(base_url, video_file, root),
            "group": group,
            "logo": logo_url,
        })

    return entries


def load_json(input_path: Path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        sys.exit("JSON input must be a list of entry objects.")
    return data


def write_m3u(entries, out_path: Path):
    lines = ["#EXTM3U"]
    for entry in entries:
        title = entry.get("title", "Untitled")
        url = entry.get("url", "")
        group = entry.get("group", "")
        logo = entry.get("logo", "")

        if not url:
            continue

        attrs = []
        if logo:
            attrs.append(f'tvg-logo="{logo}"')
        if group:
            attrs.append(f'group-title="{group}"')

        attr_str = (" " + " ".join(attrs)) if attrs else ""
        lines.append(f"#EXTINF:-1{attr_str},{title}")
        lines.append(url)

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate a movies/series M3U playlist.")
    sub = parser.add_subparsers(dest="mode", required=True)

    scan_p = sub.add_parser("scan", help="Scan a local media folder.")
    scan_p.add_argument("--root", required=True, help="Path to the media folder to scan.")
    scan_p.add_argument("--out", required=True, help="Output .m3u file path.")
    scan_p.add_argument("--base-url", required=True,
                         help="Public base URL where these files are served from, "
                              "e.g. https://yourserver.com/media")

    json_p = sub.add_parser("json", help="Build from a JSON source list.")
    json_p.add_argument("--input", required=True, help="Path to JSON source list.")
    json_p.add_argument("--out", required=True, help="Output .m3u file path.")

    args = parser.parse_args()

    if args.mode == "scan":
        root = Path(args.root).expanduser().resolve()
        if not root.is_dir():
            sys.exit(f"Root folder not found: {root}")
        entries = scan_folder(root, args.base_url)
    else:
        input_path = Path(args.input).expanduser().resolve()
        if not input_path.is_file():
            sys.exit(f"JSON input not found: {input_path}")
        entries = load_json(input_path)

    if not entries:
        print("No entries found — nothing written.")
        return

    write_m3u(entries, Path(args.out).expanduser().resolve())


if __name__ == "__main__":
    main()
