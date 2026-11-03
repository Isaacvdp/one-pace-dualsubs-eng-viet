# One Pace dual subs (English + Vietnamese)

Takes One Pace's English release subtitles from
[one-pace-public-subtitles](https://github.com/one-pace/one-pace-public-subtitles)
and adds a Vietnamese line under every spoken line. The English keeps its
original font (Impress BT, embedded in the One Pace .mkv), timing, signs and
karaoke; the Vietnamese uses Arial in pale yellow.

## Workflow (one arc at a time)

1. `python dualsub.py export 1-48` - downloads the English subs to `english/`
   and writes `work/Dressrosa NN.en.txt` (numbered dialogue lines).
2. Claude Code translates each file to `work/Dressrosa NN.vi.txt` with the same
   line numbers, following [glossary.md](glossary.md).
3. `python dualsub.py build 1-48 --video-dir "D:\One Pace\Dressrosa"` - writes
   `<video name>.vi.ass` next to each video. Without `--video-dir` the files go to `out/`.

Other arcs: add `--arc "Wano"` (the name as used in One Pace's file names).

Vietnamese goes on top at size 40 (English is 55). Options: `--order en-vi`
puts English on top, `--size 46` changes the Vietnamese size, `--font "Segoe UI"`
changes its font.

## One file per episode (recommended)

Drag the video folder onto `make_videos.bat` and type the episodes (e.g. `16-48`).
Same as running:

    python dualsub.py mux 16-48 --video-dir "D:\One Pace\Dressrosa"

Builds the subs and writes a copy of each video to `D:\One Pace\Dressrosa\dual\`
with "Tiếng Việt + English" as the first, default subtitle track. The original
English track stays in the file but is no longer default, and the embedded
fonts are kept. Nothing is re-encoded, so it takes seconds per episode. The
originals are left alone; delete them once you're happy with the copies.
It also writes `dual\<Arc>.m3u8`: double-click it and VLC plays the episodes
back to back.
Needs MKVToolNix (`winget install MoritzBunkus.MKVToolNix`).

## Watching in VLC (separate .ass file)

Put the `.vi.ass` next to the .mkv with the same name in front (the
`--video-dir` option does this). VLC loads it automatically; if it shows the
built-in English track instead, pick it under Subtitle > Sub Track. Or drag the
.ass file onto the playing video.
