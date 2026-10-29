# Explained by Simulation: long-form video factory

Makes **two** fully unique long-form science videos a day (12-15 min, longer when a topic deserves it) for
[@ExplainedBySimulation](https://www.youtube.com/@ExplainedBySimulation) and uploads them as **private**. Your
phone gets a notification for each; you check it and set it to Public, the same as your Shorts. It runs on GitHub's
free servers, so your Mac can stay off.

**How videos stay different:** most scenes use one of **48 scene templates** (`esim/templates/`): space
simulations, whiteboard diagrams in 4 board styles, data reveals and cinematic titles. Each is randomised per video
(layout, colours, camera, effects) and filled in with that scene's facts. The 3-6 biggest moments per video get
**custom animation code** written by Claude. That hybrid keeps Claude's daily usage low enough for 2 videos a day
on a Max 5x plan. `uv run python -m esim.templates` lists every template.

```
 Claude (your Max plan)            esim engine (this repo)                YouTube
 ─────────────────────             ───────────────────────                ───────
 research → plan → script   ──▶   voice (Kokoro, offline)          ──▶   upload as private
           + scenes.py             animation + VFX (Skia)                 + thumbnail + captions
                                   SFX (synthesised per video)            │
                                   music (your Audio Library tracks,      ▼
                                     beat-synced phonk-style edit)        ntfy push to your phone
                                   uniqueness check
```

Everything private (scripts, plans, research, logs, music) is stored **encrypted** in `vault.tar.enc` and
`music.vault/`, so the repo can be public (public repos get unlimited free GitHub Actions minutes).

## Setup checklist (one time, about an hour)

**0. Put sleep back to normal** (if you ran the lid-closed command): `sudo pmset -a disablesleep 0`

**1. Apple's developer tools.** In Terminal: `xcode-select --install`, then click Install. This gives the Mac
`git`, which is needed to push to GitHub.

**2. Music: real phonk you've picked yourself, from sources that won't get the video claimed**

Only download tracks you'd actually want on the channel. The system plays exactly what you import and nothing else.
**Don't use mainstream songs** (Kordhell, INTERWORLD, Dxrk and so on): they're copyrighted, YouTube's Content ID
would claim the video, and the ad money would go to the label, which defeats the point of monetising.

| Source | Phonk? | Rules |
|---|---|---|
| [Pixabay Music](https://pixabay.com/music/search/phonk/) | lots: search "phonk", "drift phonk", "aggressive phonk" | free, no credit needed, allowed in monetised videos |
| [YouTube Studio > Audio library](https://studio.youtube.com) | some: Genre *Hip Hop & Rap* or *Dance & Electronic*, Mood *Dark*/*Angry* | free, safest of all; filter **Attribution: not required** |
| [NCS (NoCopyrightSounds)](https://ncs.io) | some phonk and bass releases | free, but needs a credit line (the importer adds it) |

Aim for **about 40 hype tracks and 20 calmer ones** (for the whiteboard breathers). More tracks means fewer
repeats. Keep each source in its own folder, then import:
```bash
uv run python -m esim.music add ~/Downloads/pixabay-phonk
uv run python -m esim.music add ~/Downloads/yt-audio-library
uv run python -m esim.music add ~/Downloads/ncs --credit "{title} [NCS Release] - Music provided by NoCopyrightSounds (ncs.io)"
```
Each track gets analysed for tempo, beats, bar lines, drops and energy. `uv run python -m esim.music list` shows the
library. To drop a track you've gone off, delete it from `music/` and from `music/library.json`.

**3. GitHub**
1. Create a free account at github.com, or recover your old one with "Forgot password".
2. Create a **public** repository called `explained-by-simulation` with nothing in it.
3. Push this folder to it. Claude can do this with you once git is installed.

**4. YouTube upload access (Google Cloud, free)**
1. Go to [console.cloud.google.com](https://console.cloud.google.com), create a project, and enable **YouTube Data API v3**.
2. **OAuth consent screen**: choose External, fill in the app name and your email, and add yourself as a test user.
   Then click **Publish app** (to "In production"). If it stays in "Testing", the login expires every 7 days.
3. **Credentials > Create credentials > OAuth client ID > Desktop app**, then download the JSON file.
4. Run this. A browser opens; sign in with the channel's Google account and click Allow:
   ```bash
   uv run python -m esim.youtube auth ~/Downloads/client_secret_XXXX.json
   ```
   It prints `YT_CLIENT_ID`, `YT_CLIENT_SECRET` and `YT_REFRESH_TOKEN`.
5. **Credentials > Create credentials > API key**. That's `YOUTUBE_API_KEY`, used for niche research.

**5. Claude token (uses your Max plan, no API bill).** Install Claude Code from claude.ai/download (the CLI) and run
`claude setup-token`. That's `CLAUDE_CODE_OAUTH_TOKEN`.

**6. Phone notifications.** Install the **ntfy** app and subscribe to the topic name in the `.ntfy-topic` file
(it's random so nobody else can guess it). That's `NTFY_TOPIC`.

**7. GitHub secrets.** Repo > Settings > Secrets and variables > Actions > New repository secret, one for each:

| Secret | Where it comes from |
|---|---|
| `CONTENT_KEY` | the `.content-key` file in this folder (never share it, and keep a backup: without it the vault can't be opened) |
| `CLAUDE_CODE_OAUTH_TOKEN` | step 5 |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | step 4 |
| `YOUTUBE_API_KEY` | step 4.5 |
| `NTFY_TOPIC` | step 6 |

**8. First run.** Repo > Actions > **daily-video** > Run workflow, with *dry run* ticked. When that works, run it
again without dry run and check that a private video appears in YouTube Studio. After that it runs by itself every
morning at 05:00 UTC.

**Check the first upload carefully.** Videos from a brand-new Google project can come out "locked as private". If
yours can't be switched to Public, apply for Google's free API audit (YouTube API Services audit form); it takes
a few days to a few weeks.

## Day to day

- **Every morning:** two notifications say "New video ready to review". Tap each, watch it, set it to Public.
- **Claude keeps a reserve of 10 finished videos** (5 days), writing up to 3 new ones a day, so a bad day never stops uploads.
- **Warnings you might get:** "Only N scripts left" (Claude has been failing, so check the Actions log), "Upload
  failed: invalid_grant" (redo step 4.4 and update `YT_REFRESH_TOKEN`), "music library is empty" (step 2).

## Working on it from the Mac

```bash
uv run python -m esim.vault unlock                       # get the private files (after git pull)
uv run python -m esim.render videos/<slug> --preview     # quick check of a video
uv run python -m esim.render videos/<slug>               # full 1080p render
uv run python -m esim.vault lock                         # re-encrypt before git push
```

| Folder | What's in it |
|---|---|
| `esim/` | the engine: `engine.py` (drawing), `templates/` (48 scene templates), `audio.py` (SFX + mix), `music.py` (music library), `voice.py`, `render.py`, `daily.py`, `youtube.py`, `vault.py`, `unique.py` |
| `.claude/skills/` | yt-outlier-research, yt-plan, yt-script, yt-animate (the animation skill has the full engine reference) |
| `channel.md` | the channel profile every skill follows: niche, narrator voice, edit style, rules |
| `prompts/daily.md` | what Claude does on each daily run |
| `videos/`, `plan/`, `research/`, `data/`, `music/` | private, only stored encrypted |
| `tests/` | `make_test_beats.py` (test-only music, never uploaded) and `template_sheet.py` (renders every template into contact sheets) |
