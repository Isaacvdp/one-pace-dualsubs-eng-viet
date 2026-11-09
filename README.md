# One Pace with English + Vietnamese subtitles

Watch [One Pace](https://onepace.net) in Japanese with Vietnamese and English
subtitles on screen at the same time:

```
Ta sẽ nhấn chìm ngươi trong bóng tối, Mũ Rơm!      <- Vietnamese (pale yellow)
I'll engulf you in darkness, Straw Hat!             <- One Pace's English, unchanged
```

The English keeps One Pace's own font, timing, signs and song lyrics. The
Vietnamese is added above every spoken line.

## Arcs translated so far

| Arc | Episodes |
|---|---|
| Dressrosa | 1, 16–48 |
| Zou | 1–10 |
| Whole Cake Island | 1–39 |

The Vietnamese is translated by AI (Claude), following a shared
[glossary](glossary.md) so names, terms and pronouns stay consistent.

## One-time setup (Windows)

1. **Python**: install it from [python.org](https://www.python.org/downloads/).
   During installation, tick **"Add python.exe to PATH"**.
2. **MKVToolNix**: install it from [mkvtoolnix.download](https://mkvtoolnix.download/downloads.html#windows).
   It's the free tool that puts the subtitles into the video files.
3. **This project**: on this page click **Code → Download ZIP** and unzip it anywhere.
   (Or use `git clone` if you know git.)

## Make your videos

1. Download the One Pace episodes and keep each arc in its own folder.
   The folder name must contain the arc's name, like One Pace's own downloads do,
   for example `[One Pace][823-902] Whole Cake Island [720p]`.
2. **Drag that folder onto `make_videos.bat`** (in the project folder).
3. When it asks which episodes, **press Enter** to do all of them, or type a range like `1-19`.

That's it. It takes a few seconds per episode. Your original videos aren't
changed: the new ones go into a `dual` folder inside your video folder:

```
[One Pace][823-902] Whole Cake Island [720p]\
    [One Pace] Chapter 823-824 [720p][...].mkv      your original files
    ...
    dual\
        Whole Cake Island 01.mkv                     with Vietnamese + English
        Whole Cake Island 02.mkv
        ...
        Whole Cake Island.m3u8                       playlist
```

## Watch

Double-click the `.m3u8` playlist in the `dual` folder. VLC plays the episodes
in order, one after another, with the Vietnamese + English subtitles already
on. Opening a single `.mkv` works too.

The original English-only subtitles are still in each file if you ever want
them: in VLC, **Subtitle → Sub Track**.

## What the messages mean

| Message | Meaning |
|---|---|
| `Arc: Whole Cake Island` | The arc it found from the folder name. |
| `62 of 365 lines are worded differently in this video, matched by timing` | Fine. Your download has slightly different English wording than the version that was translated (One Pace sometimes revises subtitles). Those lines got the Vietnamese of the line shown at the same moment. |
| `! 6 of 580 lines have no Vietnamese` | Those lines show in English only, usually short on-screen captions or lines that are new in your version. |
| `couldn't tell which arc this is` | Rename the folder so it contains the arc name, e.g. `Zou`. |
| `isn't translated yet` | That episode has no Vietnamese yet (see the table above). |

## Changing how it looks

From a command prompt in the project folder:

```
python dualsub.py mux --video-dir "D:\One Pace\Zou" --size 44        bigger Vietnamese (default 40; English is 55)
python dualsub.py mux --video-dir "D:\One Pace\Zou" --order en-vi    English on top
python dualsub.py mux --video-dir "D:\One Pace\Zou" --font "Segoe UI"
```

## Translating a new arc

New arcs are translated with [Claude Code](https://claude.com/claude-code).
Open Claude Code in this project folder and type, for example:

```
/translate-arc Wano 1-30
```

It downloads the arc's English subtitles from One Pace's
[public subtitle repository](https://github.com/one-pace/one-pace-public-subtitles),
translates them into `work/<Arc>/`, checks every line is there and updates the
glossary. If your videos are on the same computer, it can take the English from
your videos instead, so the wording matches your download exactly:

```
python dualsub.py export 1-30 --arc Wano --video-dir "D:\One Pace\Wano"
```

## Project layout

```
dualsub.py           the tool
make_videos.bat      drag-and-drop wrapper
glossary.md          translation rules: terms, names, pronouns
work/<Arc>/          NN.en.txt (English lines) and NN.vi.txt (Vietnamese, same line numbers)
english/, out/       downloaded and generated files (not in git)
```

English subtitles are by the One Pace team. This project only adds the Vietnamese.
