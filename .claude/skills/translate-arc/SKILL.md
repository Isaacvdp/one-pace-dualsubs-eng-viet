---
name: translate-arc
description: Translate a One Pace arc's English subtitles to Vietnamese and build the dual subs, using as little usage as possible. Use when the user asks to do a new arc or episodes, e.g. "/translate-arc Wano 1-30".
---

# Translate an arc (low-usage procedure)

Arguments: arc name as in One Pace file names (e.g. `Wano`) and an episode range.

1. Export: `python dualsub.py export <range> --arc <Arc>` from the project folder. Note the line count per episode from the output; don't read the .en.txt files yourself.

2. Translate with helpers. Spawn them in ONE message, all with `model: "sonnet"`, about 3 episodes (~1,100 lines) each. Batching keeps overhead down: every helper pays to read the glossary and system prompt. Use this prompt, filling in ARC and EPISODES:

   > Translate One Pace English subtitles to natural, spoken Vietnamese (viewer hears Japanese audio). Folder: C:\Users\isaac\OneDrive\Dokumenter\Projects\onepace-dualsubs. Read glossary.md once and follow its terms and pronoun rules. For each episode NN in EPISODES: read `work\ARC NN.en.txt` once, then write `work\ARC NN.vi.txt` with the Write tool: same line numbers, format `N|text`, one line per input line, no `|` inside text, keep `--`, `...` and the honorifics. Write each file once; do not read it back, do not run any commands. Reply with at most 8 lines: only new recurring terms as `English = Vietnamese`, or "done".

3. Validate everything in one command: `python dualsub.py build <range> --arc <Arc>`. Any `!` line means missing lines: send only those line numbers back to that helper (SendMessage), don't redo the episode.

4. Consistency pass: collect the new terms from the helpers' replies. Where two helpers translated the same term differently, pick one, fix it with a single regex script over `work\*.vi.txt`, and add it to glossary.md under a section for this arc.

Don't read whole translated files to review them; spot-check 10-20 lines with a script if needed.
