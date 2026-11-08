"""English + Vietnamese dual subtitles for One Pace.

Keeps One Pace's English release .ass untouched (same font, timing and
typesetting) and puts the Vietnamese translation right under every spoken line.

    python dualsub.py export 1-48     # download English subs, write work/<arc>/NN.en.txt
    (translate each work/<arc>/NN.en.txt into work/<arc>/NN.vi.txt, same line numbers)
    python dualsub.py build 1-48 --video-dir "D:\\One Pace\\Dressrosa"
    python dualsub.py mux 1-48 --video-dir "D:\\One Pace\\Dressrosa"   # new .mkv files with our subs as default
"""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGLISH = HERE / "english"
WORK = HERE / "work"
TREE_API = "https://api.github.com/repos/one-pace/one-pace-public-subtitles/git/trees/main?recursive=1"
RAW = "https://raw.githubusercontent.com/one-pace/one-pace-public-subtitles/main/"
RELEASE_DIR = "main/Release/Final Subs/"

# Styles that carry dialogue, also in variants like "Main-207+".
# Signs, karaoke, credits and titles stay English-only.
DIALOGUE_STYLES = re.compile(r"^(main|secondary|flashbacks?|thoughts|narrator|note|captions\d*)(-[\w+]+)?$", re.I)
VI_STYLE = "Vietnamese"


def http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "onepace-dualsubs"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_episodes(spec):
    eps = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        eps.update(range(int(a), int(b or a) + 1))
    return sorted(eps)


def english_subs(arc, episodes):
    """Episode -> local English .ass, downloading any that aren't cached yet."""
    # "[720p].ass" only: some episodes also have e.g. "[720p] Arabic.ass" next to the English file.
    pattern = re.compile(rf"\] {re.escape(arc)} (\d+) \[[^\]]*\]\.ass$", re.I)
    folder = ENGLISH / arc
    have = {int(m.group(1)): f for f in folder.glob("*.ass") if (m := pattern.search(f.name))}
    missing = [ep for ep in episodes if ep not in have]
    if missing:
        folder.mkdir(parents=True, exist_ok=True)
        for item in json.loads(http(TREE_API))["tree"]:
            path = item["path"]
            m = pattern.search(path) if path.startswith(RELEASE_DIR) else None
            if m and int(m.group(1)) in missing:
                f = folder / Path(path).name
                f.write_bytes(http(RAW + urllib.parse.quote(path)))
                have[int(m.group(1))] = f
    for ep in episodes:
        if ep not in have:
            print(f"  ! {arc} {ep:02d}: not found in the One Pace subtitle repo")
    return {ep: have[ep] for ep in episodes if ep in have}


# ---------- .ass handling ----------

def split_dialogue(line):
    """'Dialogue: 0,start,end,style,...,text' -> list of the 10 fields."""
    return line[len("Dialogue: "):].split(",", 9)


def plain_text(ass_text):
    text = re.sub(r"\{[^}]*\}", "", ass_text)
    text = text.replace(r"\N", " ").replace(r"\n", " ").replace(r"\h", " ")
    return re.sub(r"\s+", " ", text).strip()


def seconds(ass_time):
    h, m, s = ass_time.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def translatable(lines):
    """[(line index, plain English)] for every dialogue line worth translating."""
    out = []
    for i, line in enumerate(lines):
        if not line.startswith("Dialogue: "):
            continue
        f = split_dialogue(line)
        text = plain_text(f[9])
        # Events shorter than 0.25s are frame-by-frame animated typesetting, not dialogue.
        if (DIALOGUE_STYLES.match(f[3].strip()) and text and r"\p1" not in f[9]
                and seconds(f[2]) - seconds(f[1]) >= 0.25):
            out.append((i, text))
    return out


def vi_style_line(font, size):
    # Pale yellow, same outline/shadow feel as the One Pace "Main" style.
    return (f"Style: {VI_STYLE},{font},{size},&H00A0F0FF,&H000000FF,&H00000000,&H78000000,"
            "0,0,0,0,100,100,0,0,1,2.2,0.6,2,120,120,18,1")


def build_dual(lines, vi_by_line, order, font, size):
    out = list(lines)
    for i, text in vi_by_line.items():
        text = text.replace("{", "(").replace("}", ")").replace("\\", "/")
        f = split_dialogue(out[i])
        if order == "en-vi":
            f[9] = f"{f[9]}\\N{{\\r{VI_STYLE}}}{text}"
        else:
            f[9] = f"{{\\r{VI_STYLE}}}{text}\\N{{\\r{f[3]}}}{f[9]}"
        out[i] = "Dialogue: " + ",".join(f)
    # Register the Vietnamese style right after the styles' Format line.
    in_styles = False
    for j, line in enumerate(out):
        if line.strip().lower() in ("[v4+ styles]", "[v4 styles]"):
            in_styles = True
        elif in_styles and line.startswith("Format:"):
            out.insert(j + 1, vi_style_line(font, size))
            break
    return out


# ---------- work files: "N|text" per line ----------

def read_numbered(path):
    out = {}
    for row in path.read_text(encoding="utf-8-sig").splitlines():
        n, sep, text = row.partition("|")
        if sep and n.strip().isdigit() and text.strip():
            out[int(n)] = text.strip()
    return out


def translations(arc, ep):
    """English line -> its Vietnamese translations in order of appearance, or None if not translated yet."""
    en_file, vi_file = WORK / arc / f"{ep:02d}.en.txt", WORK / arc / f"{ep:02d}.vi.txt"
    if not vi_file.exists():
        return None
    en, vi = read_numbered(en_file), read_numbered(vi_file)
    out = {}
    for n, text in en.items():
        if n in vi:
            out.setdefault(text, []).append(vi[n])
    return out


def find_video(video_dir, arc, ep, src):
    """Match by chapter range ("Chapter 700-701", "[700-701]"), else by "Dressrosa 01"."""
    m = re.search(r"\]\[(\d+-\d+)\]", src.name)
    patterns = [re.compile(rf"(?<![\d-]){m.group(1)}(?![\d-])")] if m else []
    patterns.append(re.compile(rf"{re.escape(arc)} 0*{ep}\D", re.I))
    videos = [v for v in sorted(video_dir.iterdir()) if v.suffix.lower() in (".mkv", ".mp4")]
    for pattern in patterns:
        for v in videos:
            if pattern.search(v.name):
                return v
    return None


def export(arc, ep, src):
    items = translatable(src.read_text(encoding="utf-8-sig").splitlines())
    (WORK / arc).mkdir(parents=True, exist_ok=True)
    out = WORK / arc / f"{ep:02d}.en.txt"
    if out.with_name(f"{ep:02d}.vi.txt").exists():
        # The .vi.txt is matched to this file line by line; re-exporting could renumber it.
        print(f"  {arc}/{out.name}: already translated, left as is")
        return
    out.write_text("".join(f"{n}|{text}\n" for n, (_, text) in enumerate(items, 1)), encoding="utf-8")
    print(f"  {arc}/{out.name}: {len(items)} lines")


def build(arc, ep, src, args, out=None):
    """Write the dual .ass. src may be the repo file or the track pulled from the video:
    translations are matched by English text, so small differences between the two don't matter."""
    found = translations(arc, ep)
    if found is None:
        print(f"  ! {arc} {ep:02d} isn't translated yet, skipped")
        return None
    lines = src.read_text(encoding="utf-8-sig").splitlines()
    items = translatable(lines)
    vi_by_line, seen, missing = {}, {}, []
    for i, en in items:
        options = found.get(en)
        if not options:
            missing.append(en)
            continue
        k = seen[en] = seen.get(en, -1) + 1
        text = options[min(k, len(options) - 1)]
        # Lines that read the same in both languages ("Luffy!", "Zou?") are shown once.
        if text.casefold() != en.casefold():
            vi_by_line[i] = text
    if missing:
        print(f"  ! {len(missing)} of {len(items)} lines have no Vietnamese, e.g. {missing[:3]}")

    if out is None:
        video = find_video(args.video_dir, arc, ep, src) if args.video_dir else None
        out = video.with_suffix(".vi.ass") if video else out_file(arc, ep, args)
    out.write_text("\n".join(build_dual(lines, vi_by_line, args.order, args.font, args.size)) + "\n",
                   encoding="utf-8-sig")
    print(f"  -> {out}")
    return out


def out_file(arc, ep, args):
    folder = args.out / arc
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{arc} {ep:02d}.ass"


def mkvtool(name):
    exe = shutil.which(name) or rf"C:\Program Files\MKVToolNix\{name}.exe"
    if not Path(exe).exists():
        raise SystemExit(f"{name} not found - install MKVToolNix: winget install MoritzBunkus.MKVToolNix")
    return exe


def mux(arc, ep, src, args):
    """Copy the video into <video-dir>/dual/ with our subs as the first, default subtitle track."""
    video = find_video(args.video_dir, arc, ep, src)
    if not video:
        print(f"  ! no video for {arc} {ep:02d} in {args.video_dir}")
        return
    exe = mkvtool("mkvmerge")
    tracks = json.loads(subprocess.run([exe, "-J", str(video)], capture_output=True, text=True,
                                       encoding="utf-8", check=True).stdout)["tracks"]

    # Base the subs on the English track inside this video, so the timing always fits it.
    english = sorted((t for t in tracks if t["type"] == "subtitles" and t["codec"] == "SubStationAlpha"),
                     key=lambda t: t["properties"].get("language") != "eng")
    with tempfile.TemporaryDirectory() as tmp:
        if english:
            src = Path(tmp) / "english.ass"
            subprocess.run([mkvtool("mkvextract"), str(video), "tracks", f"{english[0]['id']}:{src}"],
                           capture_output=True, check=True)
        ass = build(arc, ep, src, args, out=out_file(arc, ep, args))
    if not ass:
        return
    subs = [t["id"] for t in tracks if t["type"] == "subtitles"]
    others = [t["id"] for t in tracks if t["type"] != "subtitles"]

    target = args.video_dir / "dual" / f"{arc} {ep:02d}.mkv"
    target.parent.mkdir(exist_ok=True)
    cmd = [exe, "-o", str(target)]
    for t in subs:  # the original English stays available, just not default
        cmd += ["--default-track-flag", f"{t}:no", "--forced-display-flag", f"{t}:no"]
    cmd += [str(video),
            "--language", "0:vi", "--track-name", "0:Tiếng Việt + English",
            "--default-track-flag", "0:yes", str(ass),
            "--track-order", ",".join([f"0:{t}" for t in others] + ["1:0"] + [f"0:{t}" for t in subs])]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode >= 2:  # 1 = finished with warnings
        print(result.stdout[-500:])
        raise SystemExit(f"mkvmerge failed on {video.name}")
    print(f"  -> {target}")


def main():
    p = argparse.ArgumentParser(description="English + Vietnamese dual subs for One Pace.")
    p.add_argument("command", choices=["export", "build", "mux"])
    p.add_argument("episodes", help="e.g. 16, 1-48 or 3,5,7")
    p.add_argument("--arc", default="Dressrosa")
    p.add_argument("--video-dir", type=Path, help="folder with the videos; output is saved next to the matching one")
    p.add_argument("--out", type=Path, default=HERE / "out", help="output folder when --video-dir isn't used")
    p.add_argument("--order", choices=["en-vi", "vi-en"], default="vi-en", help="which language goes on top")
    p.add_argument("--font", default="Arial", help="font for the Vietnamese line")
    p.add_argument("--size", type=int, default=40, help="Vietnamese font size (English is 55)")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.command == "mux" and not args.video_dir:
        p.error("mux needs --video-dir")

    for ep, src in english_subs(args.arc, parse_episodes(args.episodes)).items():
        print(src.name)
        if args.command == "export":
            export(args.arc, ep, src)
        elif args.command == "build":
            build(args.arc, ep, src, args)
        else:
            mux(args.arc, ep, src, args)

    if args.command == "mux":
        # Playlist of this arc's videos in dual/, in episode order: VLC plays one after another.
        dual = args.video_dir / "dual"
        videos = sorted(v.name for v in dual.glob(f"{args.arc} *.mkv")) if dual.exists() else []
        if videos:
            playlist = dual / f"{args.arc}.m3u8"
            playlist.write_text("#EXTM3U\n" + "".join(f"{v}\n" for v in videos), encoding="utf-8")
            print(f"Playlist: {playlist}")


if __name__ == "__main__":
    main()
