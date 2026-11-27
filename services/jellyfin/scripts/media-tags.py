#!/usr/bin/env python3
"""Edit audio tags through a TOML file, one [[albums]] entry per work.

  media-tags.py export <root> > tags.toml     # current tags, gaps filled from folder names
  media-tags.py apply [tags.toml] [--dry-run]  # rewrite tags with ffmpeg (stream copy)

The tags file defaults to $XDG_CONFIG_HOME/media-tags/tags.toml.

album_artist / artist are set once per album and applied to every track under
it. artist and album_artist take a string or a list; a track-level artist
overrides the album's, and an empty album_artist falls back to artist.
cover is an image path copied as folder.<ext> next to each album's audio files,
which Jellyfin shows as the album artwork; export guesses one from the images
inside the work's folder.
album defaults to the first folder under <root>/<category>/ (or the file stem
for loose files), title to the file stem without a leading track number.
"""
import filecmp
import json
import os
import shutil
import re
import subprocess
import sys
import tomllib

AUDIO = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus"}
LEADING_NUM = re.compile(r"^\s*(\d{1,3})[\s._-]+")
IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
COVER_HINT = re.compile(r"package|jacket|cover|artwork|keyvisual|key_visual|メインビジュアル|ジャケット|サムネ", re.I)


def guess_cover(work_dir):
    images = [
        os.path.join(d, f)
        for d, _, fs in os.walk(work_dir)
        for f in fs
        if os.path.splitext(f)[1].lower() in IMAGE and not f.lower().startswith("folder.")
    ]
    if not images:
        return ""
    return max(images, key=lambda p: (bool(COVER_HINT.search(os.path.basename(p))), os.path.getsize(p)))


def default_tags_file():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "media-tags", "tags.toml")


def q(s):
    # A JSON string is a valid TOML basic string.
    return json.dumps(s, ensure_ascii=False)


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format_tags", "-of", "json", path],
        capture_output=True, text=True, check=True,
    ).stdout
    tags = json.loads(out).get("format", {}).get("tags", {})
    return {k.lower(): v for k, v in tags.items()}


def export(root):
    root = os.path.realpath(root)
    files = sorted(
        os.path.join(d, f)
        for d, _, fs in os.walk(root)
        for f in fs
        if os.path.splitext(f)[1].lower() in AUDIO
    )
    albums = {}
    for path in files:
        rel = os.path.relpath(path, root).split(os.sep)
        stem = os.path.splitext(rel[-1])[0]
        key = rel[1] if len(rel) > 2 else stem
        t = probe(path)
        work_dir = os.path.join(root, rel[0], rel[1]) if len(rel) > 2 else None
        album = albums.setdefault(key, {
            "name": t.get("album") or key,
            "cover": guess_cover(work_dir) if work_dir else "",
            "album_artist": t.get("album_artist", ""),
            "artist": t.get("artist", ""),
            "tracks": [],
        })
        m = LEADING_NUM.match(stem)
        tagged = t.get("track", "").split("/")[0]
        album["tracks"].append({
            "track": int(tagged) if tagged.isdigit()
            else int(m.group(1)) if m else len(album["tracks"]) + 1,
            "title": t.get("title") or (stem[m.end():] if m else stem),
            "path": path,
        })
    for a in albums.values():
        print("[[albums]]")
        for k in ("name", "cover", "album_artist", "artist"):
            print(f"{k} = {q(a[k])}")
        for tr in a["tracks"]:
            print("\n  [[albums.tracks]]")
            print(f"  track = {tr['track']}")
            print(f"  title = {q(tr['title'])}")
            print(f"  path = {q(tr['path'])}")
        print()


def names(v):
    # Jellyfin splits artist tags on ";", so a list becomes one joined tag.
    return "; ".join(v) if isinstance(v, list) else (v or "")


def place_cover(album, dry_run):
    src = album.get("cover")
    if not src:
        return 0
    if not os.path.isfile(src):
        print(f"FAIL: cover not found: {src}", file=sys.stderr)
        return 1
    ext = os.path.splitext(src)[1].lower()
    failed = 0
    for d in sorted({os.path.dirname(t["path"]) for t in album.get("tracks", [])}):
        dst = os.path.join(d, "folder" + ext)
        if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
            continue
        print(("would copy cover: " if dry_run else "copy cover: ") + dst)
        if dry_run:
            continue
        try:
            shutil.copyfile(src, dst)
        except OSError as e:
            failed += 1
            print(f"FAIL: {dst}: {e}", file=sys.stderr)
    return failed


def apply(tags_file, dry_run):
    with open(tags_file, "rb") as fh:
        doc = tomllib.load(fh)
    failed = 0
    for a in doc.get("albums", []):
        failed += place_cover(a, dry_run)
        for tr in a.get("tracks", []):
            path = tr["path"]
            want = {
                "album": a.get("name", ""),
                "album_artist": names(a.get("album_artist") or a.get("artist")),
                "artist": names(tr.get("artist", a.get("artist"))),
                "track": str(tr.get("track", "")),
                "title": tr.get("title", ""),
            }
            base, ext = os.path.splitext(path)
            cur = probe(path)
            # RIFF INFO has no album_artist, so ffprobe never reports it for wav.
            keys = [k for k in want if not (ext.lower() == ".wav" and k == "album_artist")]
            if all(cur.get(k, "") == want[k] for k in keys):
                continue
            print(("would tag: " if dry_run else "tag: ") + path)
            if dry_run:
                continue
            tmp = f"{base}.tagtmp{ext}"
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", path, "-map", "0", "-c", "copy"]
            for k, v in want.items():
                cmd += ["-metadata", f"{k}={v}"]
            if ext.lower() in (".wav", ".mp3"):
                cmd += ["-write_id3v2", "1", "-id3v2_version", "3"]
            cmd.append(tmp)
            if subprocess.run(cmd).returncode == 0:
                os.replace(tmp, path)
            else:
                failed += 1
                if os.path.exists(tmp):
                    os.remove(tmp)
                print(f"FAIL: {path}", file=sys.stderr)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "export":
        export(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "apply":
        args = [a for a in sys.argv[2:] if a != "--dry-run"]
        apply(args[0] if args else default_tags_file(), "--dry-run" in sys.argv[2:])
    else:
        sys.exit(__doc__)
