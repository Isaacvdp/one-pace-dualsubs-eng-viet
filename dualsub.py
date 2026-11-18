"""English + Vietnamese dual subtitles for One Pace.

Keeps One Pace's English subtitles untouched (same font, timing and
typesetting) and puts the Vietnamese translation above every spoken line.

    python dualsub.py mux --video-dir "D:\\One Pace\\Dressrosa"   # what make_videos.bat runs
    python dualsub.py export 1-30 --arc Wano    # write work/<arc>/NN.en.txt for translating
    (translate each work/<arc>/NN.en.txt into work/<arc>/NN.vi.txt, same line numbers)
    python dualsub.py build 1-30 --arc Wano     # just the .ass files, into out/<arc>/
"""
import argparse
import difflib
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
DIALOGUE_STYLES = re.compile(r"^(main|secondary|flashbacks?|thoughts|narrator|note|captions\d*"
                             r"|default|defaultlow|italics|on top|os)(-[\w+]+)?$", re.I)
# Regular anime releases instead of One Pace: "[Anime Time] One Piece - 1086.mkv"
ANIME_EPISODE = re.compile(r"One Piece\W{0,5}(\d{3,4})(?!\d)", re.I)
VI_STYLE = "Vietnamese"

# Matching reworded lines by timing: seconds of slack for retimed lines, and how alike the
# wording must be at minimum.
TIMING_SLACK = 0.5
MIN_SIMILARITY = 0.4


def http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "onepace-dualsubs"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_episodes(spec, arc):
    if spec.strip().lower() in ("", "all"):  # every translated episode of the arc
        return sorted(int(f.name.split(".")[0]) for f in (WORK / arc).glob("*.vi.txt"))
    eps = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        eps.update(range(int(a), int(b or a) + 1))
    return sorted(eps)


def english_subs(arc, episodes, download=True):
    """Episode -> local English .ass, downloading any that aren't cached yet."""
    # "[720p].ass" only: some episodes also have e.g. "[720p] Arabic.ass" next to the English file.
    pattern = re.compile(rf"\] {re.escape(arc)} (\d+) \[[^\]]*\]\.ass$", re.I)
    folder = ENGLISH / arc
    have = {int(m.group(1)): f for f in folder.glob("*.ass") if (m := pattern.search(f.name))}
    missing = [ep for ep in episodes if ep not in have]
    if missing and download:
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
            print(f"  ! {arc} {ep:02d}: " + ("not found in the One Pace subtitle repo" if download
                                             else "no video with English subtitles"))
    return {ep: have[ep] for ep in episodes if ep in have}


def working_subs(arc, episodes, video_dir=None):
    """Episode -> English .ass from One Pace's working folders ("main/32 Wano/02/wano 02 en.ass"),
    for videos with the English burned in. These are numbered like the current releases, and
    Extended Cut videos get the "extended" file. Cached in english/<arc>/working/."""
    folder = ENGLISH / arc / "working"
    extended = set()
    if video_dir:
        for v in video_dir.iterdir():
            m = re.search(rf"{re.escape(arc)} 0*(\d+)\D", v.name, re.I)
            if m and "extended cut" in v.name.lower():
                extended.add(int(m.group(1)))

    def name(ep, ext):
        return f"{arc.lower()} {ep:02d} {'extended ' if ext else ''}en.ass"

    out, tree = {}, None
    for ep in episodes:
        # English read off the video by hand (episodes the repo doesn't have) is kept in git.
        transcribed = WORK / arc / f"{ep:02d}.en.ass"
        if transcribed.exists():
            out[ep] = transcribed
            continue
        # Without the videos, whichever version was fetched before (when they were there) is used.
        names =[name(ep, True), name(ep, False)] if ep in extended or not video_dir else [name(ep, False)]
        cached = [folder / n for n in names if (folder / n).exists()]
        if cached:
            out[ep] = cached[0]
            continue
        if tree is None:
            tree = {Path(i["path"]).name.lower(): i["path"] for i in json.loads(http(TREE_API))["tree"]
                    if re.match(rf"main/\d+ {re.escape(arc)}/\d+/", i["path"], re.I)}
        for n in names:
            if n in tree:
                folder.mkdir(parents=True, exist_ok=True)
                (folder / n).write_bytes(http(RAW + urllib.parse.quote(tree[n])))
                out[ep] = folder / n
                break
        else:
            print(f"  ! {arc} {ep:02d}: no English subtitles in One Pace's subtitle repo yet")
            continue
        if ep in extended and "extended" not in out[ep].name:
            print(f"  ! {arc} {ep:02d}: no Extended Cut subtitles, using the regular ones")
    return out


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


def is_romaji(f, styles_at):
    """Crunchyroll song lyrics come in pairs: the English in Default and the Japanese sung words
    in romaji, in italics "On Top" at the same moment. The romaji isn't translated."""
    return (f[3].strip().lower() == "on top" and f[9].startswith(r"{\i1}")
            and len(styles_at[(f[1], f[2])]) > 1)


def translatable(lines):
    """[(line index, plain English)] for every dialogue line worth translating."""
    dialogue = {i: split_dialogue(line) for i, line in enumerate(lines) if line.startswith("Dialogue: ")}
    styles_at = {}
    for f in dialogue.values():
        styles_at.setdefault((f[1], f[2]), set()).add(f[3].strip().lower())
    # The opening and ending songs aren't translated at all: their English lyrics are the lines
    # sung at the same moment as a romaji line, in the first or last four minutes.
    sung = {(f[1], f[2]) for f in dialogue.values() if is_romaji(f, styles_at)}
    end = max((seconds(f[2]) for f in dialogue.values()), default=0)
    theme = {t for t in sung if seconds(t[0]) < 240 or seconds(t[0]) > end - 240}
    out = []
    for i, f in dialogue.items():
        text = plain_text(f[9])
        # Events shorter than 0.25s are frame-by-frame animated typesetting, not dialogue.
        if (DIALOGUE_STYLES.match(f[3].strip()) and text and r"\p1" not in f[9]
                and seconds(f[2]) - seconds(f[1]) >= 0.25 and not is_romaji(f, styles_at)
                and (f[1], f[2]) not in theme):
            out.append((i, text))
    return out


def vi_style_line(font, size, scale=1.0, margin=120):
    # Pale yellow, same outline/shadow feel as the One Pace "Main" style.
    # Sizes are for a 720-line script; scale fits them to scripts drawn on another canvas (Wano: 1080).
    r = lambda v: f"{v * scale:g}"
    m = round(margin * scale)
    return (f"Style: {VI_STYLE},{font},{round(size * scale)},&H00A0F0FF,&H000000FF,&H00000000,&H78000000,"
            f"0,0,0,0,100,100,0,0,1,{r(2.2)},{r(0.6)},2,{m},{m},{round(18 * scale)},1")


def play_res(lines):
    """(width, height) of the script's canvas."""
    res = {"x": 0, "y": 0}
    for line in lines:
        m = re.match(r"PlayRes([XY]):\s*(\d+)", line)
        if m:
            res[m.group(1).lower()] = int(m.group(2))
    y = res["y"] or 720
    return res["x"] or round(y * 16 / 9), y


def canvas_scale(lines):
    """Script height / 720: the --size and margins are meant for One Pace's usual 720-line scripts."""
    return play_res(lines)[1] / 720


# Bump when burned_top changes, so measurements from the old version aren't reused.
POSITIONS_VERSION = 5


def burned_top(frame, cv2, np, max_lines=3):
    """Top edge of the burned-in English in a frame, as a fraction of the height; None if there's none.
    The English is white with a black outline near the bottom: find bands of rows dense with
    white-next-to-black pixels, and walk up from the lowest through the ones shaped like text lines
    (a sign's border or a busy picture above stops it)."""
    h, w = frame.shape[:2]
    y_band = h // 2
    band = frame[y_band:, int(w * 0.12):int(w * 0.88)]
    g = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    dark = cv2.dilate((g < 80).astype(np.uint8), np.ones((5, 5), np.uint8))
    rows = ((g > 200).astype(np.uint8) & dark).sum(1)
    low = rows[int(h * 0.38):]  # the last line sits in the bottom 12%
    if low.max() < 25 * w / 1920:
        return None
    dense = np.nonzero(rows > max(15 * w / 1920, 0.2 * low.max()))[0]
    if dense[-1] + y_band < h * 0.88:
        return None
    blocks = [[dense[0], dense[0]]]  # runs of dense rows: a text line, or two touching
    for y in dense[1:]:
        if y - blocks[-1][1] <= 0.012 * h:
            blocks[-1][1] = y
        else:
            blocks.append([y, y])
    top, prev, n = None, None, 0
    for y0, y1 in reversed(blocks):
        if y1 - y0 < 0.02 * h:  # a sliver: the tails of g, p, y, or a thin line in the picture
            continue
        n += 2 if y1 - y0 > 0.07 * h else 1  # a tall run is two lines that touch
        if ((top is not None and n > max_lines) or y1 - y0 > 0.2 * h
                or (prev is not None and prev - y1 > 0.065 * h)):
            break
        top = prev = y0
    return None if top is None else (top + y_band) / h


def english_lines(ass_text):
    """How many lines an English subtitle takes: its line breaks, plus one where a long line wraps."""
    text = re.sub(r"\{[^}]*\}", "", ass_text).replace(r"\n", r"\N")
    wraps = "q2" not in ass_text  # q2: never wrapped
    return sum(1 + (wraps and len(part) > 40) for part in text.split(r"\N"))


def burned_positions(video, lines, indexes):
    """Line index -> y (script pixels) where the burned-in English starts while that line is on
    screen, measured in the video. Lines where no English shows up are left out."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("  ! OpenCV isn't installed, so the Vietnamese is placed by estimate: "
              "python -m pip install opencv-python-headless")
        return {}
    cache_file = ENGLISH / "positions" / f"{video.stem}.v{POSITIONS_VERSION}.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    res_y = play_res(lines)[1]
    cap, out = None, {}
    for i in indexes:
        f = split_dialogue(lines[i])
        if re.search(r"\\(an[4-9]|pos|move)\b", f[9]):  # English moved off the bottom: not measured
            continue
        start, end = seconds(f[1]), seconds(f[2])
        key = f"{start:.2f}-{end:.2f}"
        if key not in cache:
            if cap is None:
                print("  measuring where the English sits in the video (about a minute)...")
                cap = cv2.VideoCapture(str(video))
            tops = []
            for k in (0.3, 0.5, 0.7):
                cap.set(cv2.CAP_PROP_POS_MSEC, (start + (end - start) * k) * 1000)
                ok, frame = cap.read()
                top = burned_top(frame, cv2, np, english_lines(f[9])) if ok else None
                if top is not None:
                    tops.append(top)
            # the middle of the samples; of two, the higher one (a gap is better than overlapping)
            cache[key] = sorted(tops)[(len(tops) - 1) // 2] if tops else None
        if cache[key] is not None:
            out[i] = round(cache[key] * res_y)
    if cap is not None:
        cap.release()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache), encoding="utf-8")
    return out


def is_effect(line):
    """Events generated by a karaoke/effects template ("fx" in the Effect field): animated song
    lyrics and frame-by-frame signs. Thousands of them at once make VLC stop drawing an
    embedded subtitle track, so the dual track leaves them out (the original English keeps them)."""
    return line.startswith("Dialogue: ") and split_dialogue(line)[8].strip().lower() == "fx"


def hardsub_lines(lines, vi_by_line):
    """On-screen captions are signs, often stacked in layers: with the English burned in, they're
    in the picture already and get no Vietnamese."""
    return {i: t for i, t in vi_by_line.items()
            if not split_dialogue(lines[i])[3].strip().lower().startswith("captions")}


def build_dual(lines, vi_by_line, order, font, size, hardsub=False, positions=None):
    """With hardsub (English burned into the video), only the Vietnamese is shown, just above the
    burned-in English: at the height measured in the video (positions), or else on top of an
    invisible copy of the English line. Signs, songs and untranslated lines are left out."""
    out = list(lines)
    positions = positions or {}
    if hardsub:
        vi_by_line = hardsub_lines(lines, vi_by_line)
    res_x = play_res(lines)[0]
    gap = round(6 * canvas_scale(lines))
    for i, text in vi_by_line.items():
        text = text.replace("{", "(").replace("}", ")").replace("\\", "/")
        f = split_dialogue(out[i])
        if hardsub and i in positions:
            f[9] = f"{{\\r{VI_STYLE}\\an2\\pos({res_x // 2},{positions[i] - gap})}}{text}"
        elif hardsub:
            f[9] = f"{{\\r{VI_STYLE}}}{text}\\N{{\\r{f[3]}\\alpha&HFF&}}{f[9]}"
        elif order == "en-vi":
            f[9] = f"{f[9]}\\N{{\\r{VI_STYLE}}}{text}"
        else:
            f[9] = f"{{\\r{VI_STYLE}}}{text}\\N{{\\r{f[3]}}}{f[9]}"
        out[i] = "Dialogue: " + ",".join(f)
    if hardsub:
        out = [line for i, line in enumerate(out) if i in vi_by_line or not line.startswith("Dialogue: ")]
    # Register the Vietnamese style right after the styles' Format line.
    in_styles = False
    for j, line in enumerate(out):
        if line.strip().lower() in ("[v4+ styles]", "[v4 styles]"):
            in_styles = True
        elif in_styles and line.startswith("Format:"):
            # With only Vietnamese on screen it can use nearly the full width, so it wraps less.
            out.insert(j + 1, vi_style_line(font, size, canvas_scale(lines), 40 if hardsub else 120))
            break
    return [line for line in out if not is_effect(line)]


# ---------- work files: "N|text" per line ----------

def read_numbered(path):
    out = {}
    for row in path.read_text(encoding="utf-8-sig").splitlines():
        n, sep, text = row.partition("|")
        if sep and n.strip().isdigit() and text.strip():
            out[int(n)] = text.strip()
    return out


def translations(arc, ep):
    """English line -> its Vietnamese translations in order of appearance, or None if not translated yet.
    Lines translated in another episode of the arc (left out of this one's export) come after."""
    en_file, vi_file = WORK / arc / f"{ep:02d}.en.txt", WORK / arc / f"{ep:02d}.vi.txt"
    if not vi_file.exists():
        return None
    en, vi = read_numbered(en_file), read_numbered(vi_file)
    out = {}
    for n, text in en.items():
        if n in vi:
            out.setdefault(text, []).append(vi[n])
    for other in sorted((WORK / arc).glob("*.vi.txt")):
        if other != vi_file:
            o_en, o_vi = read_numbered(other.with_name(other.name.replace(".vi.", ".en."))), read_numbered(other)
            for n, text in o_en.items():
                if n in o_vi and text not in out:
                    out[text] = [o_vi[n]]
    return out


def reusable(text, ass_text):
    """Lines worth translating once per arc: songs and narration (whole line in italics), and
    longer lines (recaps). Short ones like "What?!" are left to each episode: the Vietnamese
    pronouns depend on who says them."""
    return ass_text.startswith(r"{\i1}") or len(text) >= 20


def earlier_lines(arc, ep):
    """English lines already exported for earlier episodes of the arc."""
    seen = set()
    for f in (WORK / arc).glob("*.en.txt"):
        if int(f.name.split(".")[0]) < ep:
            seen.update(read_numbered(f).values())
    return seen


def chapters(name):
    """'700-701' from "[One Pace][700-701] Dressrosa 01 ..." or "[One Pace] Chapter 700-701 ...", else None."""
    m = re.search(r"(?:\]\[|Chapter )(\d+(?:-\d+)?)(?![\d-])", name)
    return m.group(1) if m else None


def english_from_videos(arc, video_dir):
    """Episodes newer than One Pace's subtitle repo: take the English out of the videos themselves.

    Videos that don't belong to a known episode and come after its last chapter are numbered
    on from the last known episode (or by "Wano 47" in their name), and their English is saved
    in english/<arc>/ under a repo-style name, so every other step treats them like the rest."""
    pattern = re.compile(rf"\] {re.escape(arc)} (\d+) \[[^\]]*\]\.ass$", re.I)
    folder = ENGLISH / arc
    known = {int(m.group(1)): f for f in folder.glob("*.ass") if (m := pattern.search(f.name))}
    if not known:
        return
    matched = {find_video(video_dir, arc, ep, f) for ep, f in known.items()}
    last_chapter = max(int(c.split("-")[-1]) for f in known.values() if (c := chapters(f.name)))
    new = []
    for v in video_dir.iterdir():
        c = chapters(v.name)
        if (v.suffix.lower() in (".mkv", ".mp4") and v not in matched and c
                and int(c.split("-")[0]) > last_chapter):
            new.append((int(c.split("-")[0]), c, v))
    ep = max(known)
    for _, c, video in sorted(new):
        m = re.search(rf"{re.escape(arc)} 0*(\d+)\D", video.name, re.I)
        ep = int(m.group(1)) if m else ep + 1
        with tempfile.TemporaryDirectory() as tmp:
            src = extract_english(video, video_tracks(video), tmp)
            if not src:
                print(f"  ! {video.name} has no English subtitles")
                continue
            shutil.copyfile(src, folder / f"[One Pace][{c}] {arc} {ep:02d} [video].ass")
        print(f"  {arc} {ep:02d}: English taken from {video.name} (not in One Pace's subtitle repo yet)")


def is_anime_release(video_dir):
    """Regular anime episodes (numbered like "One Piece - 1086") rather than One Pace."""
    names = [v.name for v in video_dir.iterdir() if v.suffix.lower() in (".mkv", ".mp4")]
    return bool(names) and not any("one pace" in n.lower() for n in names) and any(
        ANIME_EPISODE.search(n) for n in names)


def anime_english(arc, video_dir):
    """Regular anime releases: episodes keep the anime's numbers (1086 ...) and the English comes
    out of the videos, saved in english/<arc>/ under a repo-style name like the other arcs."""
    folder = ENGLISH / arc
    for video in sorted(video_dir.iterdir()):
        m = ANIME_EPISODE.search(video.name)
        if video.suffix.lower() not in (".mkv", ".mp4") or not m:
            continue
        ep = int(m.group(1))
        dest = folder / f"[Anime][{ep}] {arc} {ep} [video].ass"
        if dest.exists():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            src = extract_english(video, video_tracks(video), tmp)
            if not src:
                print(f"  ! {video.name} has no English subtitles")
                continue
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)


def find_video(video_dir, arc, ep, src):
    """Match by chapter range ("Chapter 700-701", "[700-701]"), else by "Dressrosa 01"."""
    m = re.search(r"\]\[(\d+(?:-\d+)?)\]", src.name)
    patterns = [re.compile(rf"(?<![\d-]){m.group(1)}(?![\d-])")] if m else []
    patterns.append(re.compile(rf"{re.escape(arc)} 0*{ep}\D", re.I))
    videos = [v for v in sorted(video_dir.iterdir()) if v.suffix.lower() in (".mkv", ".mp4")]
    for pattern in patterns:
        for v in videos:
            if pattern.search(v.name):
                return v
    return None


def export(arc, ep, src, args):
    """With --video-dir, export the English inside the video itself: the repo's copy can be
    worded differently from what a given release contains."""
    if args.video_dir:
        video = find_video(args.video_dir, arc, ep, src)
        if not video:
            print(f"  ! no video for {arc} {ep:02d} in {args.video_dir}")
            return
        with tempfile.TemporaryDirectory() as tmp:
            src = extract_english(video, video_tracks(video), tmp) or src
            lines = src.read_text(encoding="utf-8-sig").splitlines()
    else:
        lines = src.read_text(encoding="utf-8-sig").splitlines()
    items = translatable(lines)
    (WORK / arc).mkdir(parents=True, exist_ok=True)
    out = WORK / arc / f"{ep:02d}.en.txt"
    if out.with_name(f"{ep:02d}.vi.txt").exists():
        # The .vi.txt is matched to this file line by line; re-exporting could renumber it.
        print(f"  {arc}/{out.name}: already translated, left as is")
        return
    seen = earlier_lines(arc, ep)
    new = [(i, text) for i, text in items
           if not (text in seen and reusable(text, split_dialogue(lines[i])[9]))]
    out.write_text("".join(f"{n}|{text}\n" for n, (_, text) in enumerate(new, 1)), encoding="utf-8")
    reused = f" ({len(items) - len(new)} more already in earlier episodes)" if len(new) < len(items) else ""
    print(f"  {arc}/{out.name}: {len(new)} lines{reused}")


def similarity(a, b):
    return difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


def timed_lines(path, found):
    """(start, end, English, Vietnamese) for each translated line of the file the translation was made from."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    out = []
    for i, en in translatable(lines):
        if en in found:
            f = split_dialogue(lines[i])
            out.append((seconds(f[1]), seconds(f[2]), en, found[en][0]))
    return out


def local_offset(start, anchors):
    """How far this video runs ahead of the reference around `start`: the median shift of the
    nearest lines that match word for word. Handles re-cut episodes where the shift changes."""
    near = sorted(anchors, key=lambda a: abs(a[0] - start))[:7]
    shifts = sorted(video - ref for video, ref in near)
    return shifts[len(shifts) // 2] if shifts else 0.0


def by_timing(start, end, en, reference):
    """Vietnamese of the reference line on screen at the same moment with the closest wording.

    A re-release often rewords lines ("Mistress Smoothie" -> "Smoothie-sama") but they stay where
    they were, so a line overlapping in time with similar wording is the same line."""
    best_score, best = 0.0, None
    for ref_start, ref_end, ref_en, vi in reference:
        overlap = min(end, ref_end) - max(start, ref_start) + TIMING_SLACK
        if overlap <= 0:
            continue
        sim = similarity(en, ref_en)
        if sim >= MIN_SIMILARITY and sim > best_score:
            best_score, best = sim, vi
    return best


def build(arc, ep, src, args, out=None, reference=None, video=None):
    """Write the dual .ass. src may be the repo file or the track pulled from the video:
    translations are matched by English text, and lines worded differently in the video are
    matched by timing against reference (the file the translation was made from)."""
    found = translations(arc, ep)
    if found is None:
        print(f"  ! {arc} {ep:02d} isn't translated yet, skipped")
        return None
    lines = src.read_text(encoding="utf-8-sig").splitlines()
    items = translatable(lines)
    ref = timed_lines(reference, found) if reference else []
    ref_starts = {}
    for ref_start, _, ref_en, _ in ref:
        ref_starts.setdefault(ref_en, []).append(ref_start)
    times = {i: (seconds(f[1]), seconds(f[2])) for i, _ in items for f in [split_dialogue(lines[i])]}
    # Lines matching word for word anchor the timing between the video and the reference.
    anchors, counts = [], {}
    for i, en in items:
        if en in ref_starts:
            k = counts[en] = counts.get(en, -1) + 1
            if k < len(ref_starts[en]):
                anchors.append((times[i][0], ref_starts[en][k]))

    vi_by_line, seen, timed, missing = {}, {}, 0, []
    for i, en in items:
        options = found.get(en)
        if options:
            k = seen[en] = seen.get(en, -1) + 1
            text = options[min(k, len(options) - 1)]
        else:
            start, end = times[i]
            shift = local_offset(start, anchors)
            text = by_timing(start - shift, end - shift, en, ref)
            if not text:
                missing.append(en)
                continue
            timed += 1
        # Lines that read the same in both languages ("Luffy!", "Zou?") are shown once.
        if text.casefold() != en.casefold():
            vi_by_line[i] = text
    if timed:
        print(f"  {timed} of {len(items)} lines are worded differently in this video, matched by timing")
    if missing:
        print(f"  ! {len(missing)} of {len(items)} lines have no Vietnamese, e.g. {missing[:3]}")

    if out is None:
        video = find_video(args.video_dir, arc, ep, src) if args.video_dir else None
        out = video.with_suffix(".vi.ass") if video else out_file(arc, ep, args)
    positions = {}
    if args.hardsub and video:
        shown = hardsub_lines(lines, vi_by_line)
        positions = burned_positions(video, lines, shown)
        if len(positions) < len(shown):
            print(f"  {len(shown) - len(positions)} of {len(shown)} lines placed by estimate "
                  "(no burned-in English found under them)")
    out.write_text("\n".join(build_dual(lines, vi_by_line, args.order, args.font, args.size, args.hardsub,
                                        positions)) + "\n", encoding="utf-8-sig")
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


def video_info(video):
    return json.loads(subprocess.run([mkvtool("mkvmerge"), "-J", str(video)], capture_output=True, text=True,
                                     encoding="utf-8", check=True).stdout)


def video_tracks(video):
    info = video_info(video)
    if "tracks" not in info:  # e.g. a torrent that hasn't finished: full size, but zeros
        print(f"  ! {video.name} can't be read - is it fully downloaded?")
    return info.get("tracks", [])


# One Pace's dialogue fonts. Releases with burned-in English (mp4) carry no fonts, so the player
# would draw our subs in a stand-in font; for the invisible English spacer that wraps differently
# from the burned-in text and leaves a gap under the Vietnamese.
FONT_FILES = ["Impress BT.TTF", "ImpressBT-Pace-Regular.ttf", "ImpressBT-Pace-Italics.ttf"]


def dialogue_fonts():
    folder = ENGLISH / "fonts"
    paths = []
    for name in FONT_FILES:
        path = folder / name
        if not path.exists():
            folder.mkdir(parents=True, exist_ok=True)
            path.write_bytes(http(RAW + urllib.parse.quote(f"main/Other/Common Fonts/{name}")))
        paths.append(path)
    return paths


def extract_english(video, tracks, folder):
    """Write the video's own English .ass track into folder; None if it has none."""
    english = sorted((t for t in tracks if t["type"] == "subtitles" and t["codec"] == "SubStationAlpha"),
                     key=lambda t: t["properties"].get("language") != "eng")
    if not english:
        return None
    path = Path(folder) / "english.ass"
    subprocess.run([mkvtool("mkvextract"), str(video), "tracks", f"{english[0]['id']}:{path}"],
                   capture_output=True, check=True)
    return path


def mux(arc, ep, src, args):
    """Copy the video into <video-dir>/dual/ with our subs as the first, default subtitle track."""
    video = find_video(args.video_dir, arc, ep, src)
    if not video:
        if not args.all_episodes:
            print(f"  ! no video for {arc} {ep:02d} in {args.video_dir}")
        return
    print(f"{arc} {ep:02d}: {video.name}")
    exe = mkvtool("mkvmerge")
    info = video_info(video)
    tracks = info["tracks"]

    # Base the subs on the English track inside this video, so the timing always fits it.
    with tempfile.TemporaryDirectory() as tmp:
        ass = build(arc, ep, extract_english(video, tracks, tmp) or src, args,
                    out=out_file(arc, ep, args), reference=src, video=video)
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
            "--default-track-flag", "0:yes", str(ass)]
    if not info.get("attachments"):  # mkv releases bring their own fonts
        for font in dialogue_fonts():
            cmd += ["--attachment-mime-type", "font/ttf", "--attach-file", str(font)]
    cmd += ["--track-order", ",".join([f"0:{t}" for t in others] + ["1:0"] + [f"0:{t}" for t in subs])]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode >= 2:  # 1 = finished with warnings
        print(result.stdout[-500:])
        raise SystemExit(f"mkvmerge failed on {video.name}")
    # The same subs as a file next to the video: VLC loads it automatically, and it still shows
    # if VLC ever fails to draw the embedded track.
    shutil.copyfile(ass, target.with_suffix(".ass"))
    print(f"  -> {target}")


# Double-click to keep watching an arc in VLC: starts the playlist at the episode VLC played
# last (from VLC's recently played list), and VLC offers to resume where it stopped.
# The PowerShell after "exit /b" is run by the first lines; cmd never reaches it.
CONTINUE_BAT = r"""@echo off
set "SELF=%~f0"
set "PLAYLIST={playlist}"
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((Get-Content -LiteralPath $env:SELF -Encoding UTF8 | Select-Object -Skip 5) -join [char]10)"
exit /b
$dir = Split-Path -LiteralPath $env:SELF
$playlist = Join-Path $dir $env:PLAYLIST
$episodes = @(Get-Content -LiteralPath $playlist -Encoding UTF8 | Where-Object { $_ -and -not $_.StartsWith('#') })
$start = 0
$ini = Join-Path $env:APPDATA 'vlc\vlc-qt-interface.ini'
if (Test-Path -LiteralPath $ini) {
    $section = ''
    $recent = @()
    foreach ($line in Get-Content -LiteralPath $ini -Encoding UTF8) {
        if ($line -match '^\[(.+)\]$') { $section = $matches[1] }
        elseif ($section -eq 'RecentsMRL' -and $line.StartsWith('list=')) { $recent = $line.Substring(5) -split ',' }
    }
    $found = $false
    foreach ($mrl in $recent) {
        $mrl = $mrl.Trim().Trim('"')
        if ($found -or -not $mrl.StartsWith('file:///')) { continue }
        $path = [uri]::UnescapeDataString($mrl.Substring(8)).Replace('/', '\')
        for ($i = 0; $i -lt $episodes.Count; $i++) {
            if ($path -ieq (Join-Path $dir $episodes[$i])) { $start = $i; $found = $true; break }
        }
    }
}
$vlc = @("$env:ProgramFiles\VideoLAN\VLC\vlc.exe", "${env:ProgramFiles(x86)}\VideoLAN\VLC\vlc.exe") |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $vlc) {
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\VideoLAN\VLC' -ErrorAction SilentlyContinue
    if ($reg) { $vlc = $reg.'(default)' }
}
if (-not $vlc) { Start-Process -FilePath $playlist; return }
$files = $episodes[$start..($episodes.Count - 1)] | ForEach-Object { '"' + (Join-Path $dir $_) + '"' }
Start-Process -FilePath $vlc -ArgumentList $files
"""


def detect_arc(video_dir):
    """The translated arc named in the video folder's path or its video file names."""
    arcs = sorted((f.name for f in WORK.iterdir() if f.is_dir()), key=len, reverse=True)
    names = [str(video_dir.resolve())] + [v.name for v in video_dir.iterdir()]
    for arc in arcs:
        if any(arc.lower() in name.lower() for name in names):
            return arc
    return None


def main():
    p = argparse.ArgumentParser(description="English + Vietnamese dual subs for One Pace.")
    p.add_argument("command", choices=["export", "build", "mux"])
    p.add_argument("episodes", nargs="?", default="all", help="e.g. 16, 1-48 or 3,5,7; default: all translated")
    p.add_argument("--arc", help="arc name as in One Pace's file names; with --video-dir it's found automatically")
    p.add_argument("--video-dir", type=Path, help="folder with the videos; output is saved next to the matching one")
    p.add_argument("--out", type=Path, default=HERE / "out", help="output folder when --video-dir isn't used")
    p.add_argument("--order", choices=["en-vi", "vi-en"], default="vi-en", help="which language goes on top")
    p.add_argument("--font", default="Arial", help="font for the Vietnamese line")
    p.add_argument("--size", type=int, help="Vietnamese font size on a 720-line script, scaled up on 1080-line "
                   "ones like Wano (default 48; 40 when the English is burned in; English is 55)")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.command == "mux" and not args.video_dir:
        p.error("mux needs --video-dir")
    if args.video_dir and not args.video_dir.is_dir():
        p.error(f"folder not found: {args.video_dir}")
    if not args.arc:
        args.arc = detect_arc(args.video_dir) if args.video_dir else None
        if not args.arc:
            arcs = ", ".join(f.name for f in WORK.iterdir() if f.is_dir())
            p.error(f"couldn't tell which arc this is; put the arc name in the folder name "
                    f"or pass --arc. Translated arcs: {arcs}")
        print(f"Arc: {args.arc}")

    # With "all", episodes missing from a partial download are skipped without a warning.
    args.all_episodes = args.episodes.strip().lower() in ("", "all")
    # Videos with the English burned in (no subtitle track) are remembered per arc, so later
    # steps without --video-dir use the same English.
    marker = WORK / args.arc / "hardsub"
    if args.video_dir and not marker.exists():
        videos = [v for v in sorted(args.video_dir.iterdir()) if v.suffix.lower() in (".mkv", ".mp4")]
        if videos and not any(t["type"] == "subtitles" for t in video_tracks(videos[0])):
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("This arc's videos have the English burned in: the English comes from One Pace's "
                              "working folders and the subtitles show Vietnamese only.\n", encoding="utf-8")
    args.hardsub = marker.exists()
    anime = WORK / args.arc / "anime"
    if args.video_dir and not anime.exists() and is_anime_release(args.video_dir):
        anime.parent.mkdir(parents=True, exist_ok=True)
        anime.write_text("This arc's videos are regular anime episodes, not One Pace: episodes keep the "
                         "anime's numbers and the English comes from the videos.\n", encoding="utf-8")
    args.anime = anime.exists()
    args.size = args.size or (40 if args.hardsub else 48)
    episodes = parse_episodes(args.episodes, args.arc)
    if args.hardsub:
        sources = working_subs(args.arc, episodes, args.video_dir)
    elif args.anime:
        if args.video_dir:
            anime_english(args.arc, args.video_dir)
        sources = english_subs(args.arc, episodes, download=False)
    else:
        if args.video_dir:
            english_from_videos(args.arc, args.video_dir)
        sources = english_subs(args.arc, episodes)
    for ep, src in sources.items():
        if args.command != "mux":
            print(src.name)
        if args.command == "export":
            export(args.arc, ep, src, args)
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
            launcher = dual / f"Continue {args.arc}.bat"
            launcher.write_text(CONTINUE_BAT.replace("{playlist}", playlist.name), encoding="ascii", newline="\r\n")
            print(f"Keep watching: {launcher}")


if __name__ == "__main__":
    main()
