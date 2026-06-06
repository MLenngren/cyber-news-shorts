---
name: cyber-news-shorts
description: Write satirical cyber news scripts and customize the HyperFrames composition for ThreatNoir Cyber News shorts (~60-90s vertical, dry-anchor delivery). Default render mode = talking-head (HeyGen Tyler avatar over Decart-animated cyber-newsroom). Opt-in modes: stock-broll (Pexels/Storyblocks + 1 AI hero + chyrons + chrome) and b-roll (Runware stills + hero clip).
user-invocable: true
disable-model-invocation: false
---

# ThreatNoir Cyber News — Shorts skill

Vertical 1080×1920 cyber news shorts in the voice of a dry-sarcastic British anchor.

Default is **talking-head mode** (HeyGen Tyler over a Decart-animated cyber-newsroom background). Three opt-in modes exist:

- **talking-head-hybrid**: HeyGen Tyler + Pexels cutaways (Tyler shrinks to bottom-right PIP during b-roll windows; audio stays continuous)
- **stock-broll**: Pexels/Storyblocks stock clips + 1 AI hero clip + center chyrons + chrome
- **b-roll**: Runware-generated stills + 1 hero animated clip (no avatar)

**Project root:** repo root (this repository).

## Format

- **Length:** 60-90 seconds (6-10 lines, 180s max per Shorts spec)
- **Aspect:** 1080×1920 vertical
- **Speaker:** `ANCHOR` (single speaker, no dialogue partner)
- **Voice:** Nathaniel — `voice_id 7S3KNdLDL7aRgBVRQb1z`. Settings: `stability=0.30, similarity_boost=0.75, style=0.55`
- **Render modes:**
  - **`talking-head` (default)** — HeyGen Tyler in Casual Suit (`Tyler-incasualsuit-20220721`) over Decart-animated cyber-newsroom bg
  - **`talking-head-hybrid` (opt-in)** — HeyGen Tyler + Pexels cutaways (PIP during cutaways), renders via `hyperframes/compositions/talking-head-hybrid.html`
  - **`stock-broll` (opt-in)** — Pexels/Storyblocks + 1 AI hero + center chyrons + chrome (no captions)
  - **`b-roll` (opt-in / experimental)** — Runware-generated stills + 1 hero animated clip, no avatar, per-word kinetic captions
- **Subtitles:**
  - `talking-head`: per-line subtitle band (from timing.json)
  - `talking-head-hybrid`: per-word RGB caption stack (from transcript.json)
    - **Subtitles (v3.3, 2026-05-24):** Transparent RGB-glitch-per-word caption stack at `top: 14%`. Each word appears at its Whisper-aligned `start` time from `<slug>.transcript.json`: 0.18s entry with chromatic fringe (red + cyan offset) + scale, tiny glitch pulse, then R/C layers fade out leaving clean white text. Words accumulate top-to-bottom; auto-line-break on ≥0.25s pause gaps. Bracket-marked words from `subtitles:` frontmatter (`[word]` markup) render with yellow `<mark>` highlight. Subtitle window: PIP_START_TIME → final_line.start - 0.3s (no subs when Tyler is full-bleed). Composition adds 3s tail past audio end so the climax can complete before the end card.
  - `stock-broll`: none (format uses center chyrons + optional card)
  - `b-roll`: per-word kinetic captions (from ElevenLabs alignment in timing.json)
- **Cost cap:** $0.50/short (hard cap). Stock-broll and b-roll both enforce this during paid media generation.

## Voice rules — the ANCHOR persona

The ANCHOR is **not** doing a Max Headroom impression. He is a dry-sarcastic British news presenter, in the spirit of Charlie Brooker on Newswipe or David Mitchell. Tone:

1. **Dry sarcasm delivered straight.** No exclamations, no audible laughs, no "oh boy". Like he's reporting an overcrowded train, not the apocalypse.
2. **News-anchor cadence.** Short declarative sentences. Pause-heavy. Each sentence lands.
3. **No stutter, no glitch in the voice itself.** Visual glitches/scanlines belong to the composition; the voice is even.
4. **The punchline is the closing line.** Land the irony at the end. Don't burn it earlier.
5. **Specific facts, not generic posturing.** CVE numbers, threat actor IDs, deadlines, vendor names — the satire works because the absurdity is real.
6. **Customer-shocked / analyst-not-shocked rhythm.** Two-clause sentences where the second clause undercuts the first are the ANCHOR's signature.

### Script structure (bity v3 — tightened 2026-05-15)

Editorial bar: **edgy, bity, to-the-point.** Reference cut: `short-001-three-hours.mp4` (not included in this OSS snapshot). Short-037 ("Counts As Success") was the closest production run; this v3 trims ~15% further and pushes for more sarcasm.

- **Cold-open:** Line 1 is a one-liner that lands before any setup. No "Today we look at...", no "Good morning", no throat-clearing. Sharp, declarative, slightly sarcastic. The story's hardest fact, naked.
- **Line length:** ≤12 words per line. Hard cap. If a line is longer, split it or cut filler.
- **Lines per short:** 6-7 total. Not 8, not 9. Tight beats trim flab.
- **TWO sarcastic beats minimum:** One mid-script, one in the close. The mid-beat undercuts the threat; the close undercuts the defender. Both must read as observations, not jokes.
- **Every line earns its place.** Each line carries either a fact-with-edge OR a beat. Lines that just inform without a tilt get cut or merged.
- **Filler clauses banned:** "in a single day", "no matter how", "this week", "technically", "literally", "as it turns out", "you would think". These signal a writer reaching for cadence. Compress instead.
- **Defensive close (mandatory):** Last line is a security awareness takeaway baked into the joke. Two-clause sentence — concede the chaos, then leave the listener with one actionable thing. Examples:
  - "Rotate your keys. Or wait for the next disclosure to remind you."
  - "Patch on Tuesday. Restore on Wednesday. Not the other way around."
  - "An error is not consent."
- **Stories per short:** Either ONE long story OR TWO short beats with a named shared spine. Never three.

### Evening editorial bar (longform analytical, 2026-05-17)

**For evening talking-head-hybrid renders ONLY. Morning stock-broll keeps bity v3 unchanged.**

Evening shorts should develop the value/risk story and end with a concrete takeaway — analyst tone over comedian tone.

- **Length:** 10-14 lines, ≤16 words/line hard cap, runtime 60-80s
- **Structure:**
  1. **Cold-open one-liner** — story's hardest fact naked. No greeting, no "Good evening".
  2. **2-3 lines WHAT HAPPENED** — tech translated to business terms
  3. **2-3 lines WHO'S AT RISK** — concrete industries, blast radius, attacker gain, defender loss
  4. **2-3 lines WHY IT MATTERS** — business / regulatory / reputational angle
  5. **Optional ONE sarcastic beat** — not mandatory; evening is more analytical than morning
	  6. **Explicit takeaway (final 1-2 lines):** Use ONE archetype (rotate across days; avoid repeats). Must be one concrete action (or two max in a checklist), no hedging. Doubles as final chyron text.
	     - (A) "Do this now: <action>. Because <reason>."
	     - (B) "Your 30-minute check: <action>; <action>."
	     - (C) "If you can only do one thing: <action>."
	     - (D) "Detection angle: <monitor>; <alert>."
	     - (E) "Risk trade: <action>, or accept <consequence>."
	     - Hard bans: never start the takeaway with "If you run" and never end it with "tonight".
- **BANNED filler clauses (same as morning):** "in a single day", "no matter how", "this week", "technically", "literally", "as it turns out", "you would think"
- **NEVER speak raw IOCs** — IPs, ports, hashes, file paths, binary names with underscores/dots/dashes, fully-qualified API/function names, version-as-phonetic. They belong on the CVE card or a chyron only.
- **If a story is mostly an IOC dump**, pick a DIFFERENT story.

Examples of good takeaway lines:
- "Do this now: rotate every staff API key. Because token reuse is the whole attack chain."
- "Your 30-minute check: disable WAN management; review admin logins for the last 72 hours."
- "Detection angle: alert on new OAuth apps; hunt for sudden token spikes in one tenant."

### Spoken-line content rules (added 2026-05-16 after short-040 review)

**NEVER speak the following aloud.** Nathaniel reads them out phonetically and the cadence collapses ("Win dot Kernel underscore Svc"; "sixty-eight point two-one-nine, port four-four-four-four"):

- Raw IP addresses or domain strings
- Port numbers
- Hex strings, hash fragments, signatures
- File paths or filenames with underscores/dots/dashes
- Binary names or process names with non-spoken characters
- Fully-qualified API/function names (`AmsiScanBuffer.dll`, `wp_authenticate_application_password()`)
- Version strings spelled phonetically ("seven point four", "three point four point one")

**Where these go instead:**
- CVE numbers, version strings, function names → the HTML CVE card (`kind: card_cve` in `shots:`)
- IP / port / file path / hash → a chyron for that shot (e.g. `chyron: "C2: 68.219.X.X:4444"` rendered visually, never spoken)
- If a fact has no spoken equivalent and no card/chyron home, cut it

**Translate to business impact instead.** If the story's only hook is technical IOCs, either pick a different story, or restate the tech as human consequence: "the malware turns off the antivirus and Windows believes it" — not "patches AmsiScanBuffer in memory before it unpacks".

If a story is mostly an IOC dump (malware analysis with binary names, IPs, hashes) and has no human angle, it does not fit the ANCHOR format. Pick a different beat from the day's news.

### Reference cadence (short-001 outro)

> The lesson is clear.
> The thing keeping the attackers out... may already be inside.

Two short sentences. Pause. Punchline. The trailing ellipsis cues a beat of silence before the kicker. The anchor never raises his voice to deliver it.

## Script structure

```markdown
---
title: "..."
runtime_estimate: 1:10
edition: morning   # or evening
source: "..."
source_url: "..."
hero_still_index: 5
hero_motion: "slow zoom into the rack, scanlines flicker"
hosts:
  - ANCHOR (voice Nathaniel — voice_id 7S3KNdLDL7aRgBVRQb1z)
---

# Short NNN — "<Headline>"

> One-paragraph intent line.

---

**ANCHOR:**
[visual: dim data center aisle, scanlines, racks fading into haze]
Another patch. Another disclosure.

**ANCHOR:**
[visual: fragmenting glass padlock, magenta shards on near-black]
The fix arrived. The breach already happened.

**ANCHOR:**
[visual: cold-blue dashboard glow, red alert tiles multiplying]
Customers are shocked. Analysts have already scheduled the meeting.

**ANCHOR:**
[visual: gloved hands swapping cables, a keyring slipping loose]
Rotate your keys. Or wait for the next disclosure to remind you.
```

## `cutaways:` frontmatter — talking-head-hybrid mode

**Applies only when rendering with `--mode talking-head-hybrid`.** This mode does **not** use `shots:` and does **not** use `[visual:]` directives.

In talking-head-hybrid mode, the script frontmatter may include a `cutaways:` list. Each cutaway maps to a spoken line via `line_index` (1-based), and will:

- fade in a full-screen Pexels b-roll clip for the cutaway duration (audio stays continuous)
- **does not** bounce Tyler big/small per cutaway
- Tyler uses a simple three-beat PIP rhythm for the whole short:
  1. opener: Tyler full-bleed
  2. story section: Tyler shrinks once to bottom-right and stays there through cutaways
  3. close: Tyler returns to full-bleed once for the final dialogue line

**Worked example (frontmatter only):**

```yaml
---
title: "ThreatNoir Cyber News — Short NNN: <Slug>"
edition: evening
story_date: "YYYY-MM-DD"
hosts:
  - ANCHOR (voice Nathaniel — voice_id 7S3KNdLDL7aRgBVRQb1z)
cutaways:
  - line_index: 3
    pexels_query: "data center aisle blue light slow pan"
    duration: 4.5
  - line_index: 7
    pexels_query: "corporate office laptops security alert"
    duration: 4.0
  - line_index: 11
    pexels_query: "hands rotating keys close-up dark"
    duration: 3.5
---
```

**Note:** The old center info cards (breach-stamp / patch-window / FOLLOW-UPS) have been removed in hybrid. Flash bullets replace their role.

## `subtitles:` frontmatter — talking-head-hybrid mode (optional)

Optional field. In v3.3, this field is **highlight-only**: it does not control
caption text or timing.

- `text`: used only to extract words wrapped in `[brackets]`
- Any bracketed words are highlighted yellow on-screen (Aftonbladet style)
- If omitted/empty, no words are highlighted

**Yellow highlights (v3.3.4):** Producer-authored `[word]` brackets in `subtitles:` are authoritative. Additionally, the renderer auto-highlights power words from the transcript: 4-digit years (2018, 2026), CVE IDs, "million"/"billion"/"thousand", and a small dictionary of cyber-news action verbs (hijacked, breached, exploited, bypassed, patched, etc). Density target: ~1 highlight per 6 words.

All per-word content + timing comes from `<slug>.transcript.json`.

**Example (frontmatter only):**

```yaml
subtitles:
  - line_index: 1
    text: "[8-YEAR] FLAW"
  - line_index: 2
    text: "[RONDODOX] BOTNET"
  - line_index: 3
    text: "1 MILLION [ROUTERS]"
```

### `opener_text:` (optional) — talking-head-hybrid mode

Optional field. If present, renders a **4s editorial poster** at the start (before Tyler enters PIP).

- Type: `string` **or** `list[string]`
- List form: **0–2** lines
- Word cap: **4 words per line** (extra words are truncated with a warning)
- Styling: if a 2-line list is used, the **second** line is rendered with a red accent.

**Explicit-or-nothing:** do **not** auto-default this from hooks. If absent/empty, no poster is shown.

When `opener_text` is present, Tyler’s `PIP_START_TIME` is pushed **after** the poster fades. When absent, Tyler enters PIP at spoken line 2 (existing behavior).

**Example (frontmatter only):**

```yaml
opener_text:
  - "EIGHT YEARS LATE"
  - "ASUS PATCHES THE FLAW"
# OR single-line
opener_text: "RETIRE THE DEVICE"
```

### `ambient_query:` (optional) — talking-head-hybrid mode

Optional Pexels search query string used to fetch a **continuous ambient background loop** behind Tyler during the PIP window.

- Default: `"abstract cyber server room slow motion dim"`
- Notes: the ambient layer is dim/blurred and sits behind cutaways.

**Example (frontmatter only):**

```yaml
ambient_query: "abstract server rack red dim slow pan"
```

### Visual hierarchy contract (hybrid)

One-leader-at-a-time rule:

- **Opener window:** opener poster leads (Tyler full-bleed underneath)
- **PIP window:** Tyler PIP leads; ambient bg runs continuously; cutaways go full-bleed in their windows; flash bullets pop briefly
- **Climax window:** climax glitch leads; Tyler underneath

Z-index stack (must remain stable): `ambient-bg=1 < cutaways=5 < Tyler=10 < captions=15 < flash-bullets=22 < climax=24`.


### `flash_bullets:` (optional) — talking-head-hybrid mode

Optional field. If present, include **0–4** bullets. Each bullet is a quick, center-screen hit that flashes for ~2 seconds.

- `at_line`: 1-based spoken line index
- `text`: required, uppercased, ≤30 chars
- `sub`: optional, uppercased, ≤60 chars

If omitted: the renderer auto-generates **3** bullets from `hooks` + `cves` + `vendors`.

Rules:

- min spacing **4s** between bullets
- cap **4** bullets total

**Example (frontmatter only):**

```yaml
flash_bullets:
  - at_line: 3
    text: "8 YEARS"
    sub: "BUG SAT IN CODE"
  - at_line: 6
    text: "25M ROUTERS"
    sub: "EXPOSED"
  - at_line: 10
    text: "PATCH: 2018"
    sub: "AVAILABLE THE WHOLE TIME"
```

## `shots:` frontmatter — stock-broll mode

**Applies only when rendering with `--mode stock-broll`.** This mode does **not** use `[visual:]` directives.

In stock-broll mode, the script frontmatter must include a `shots:` list. Each shot maps to a spoken line via `line_index` (1-based, as emitted by `parse_script.py`).

**Worked example (frontmatter only):**

```yaml
---
title: "ThreatNoir Cyber News — Short NNN: <Slug>"
runtime_estimate: "0:40"
source: "..."
source_url: "..."
story_date: "YYYY-MM-DD"
hosts:
  - ANCHOR (voice Nathaniel — voice_id 7S3KNdLDL7aRgBVRQb1z)
shots:
  - shot: 1
    line_index: 1
    kind: stock
    query: "person hands typing keyboard low light"
    chyron: "TWO 0-DAYS DROPPED"
  - shot: 2
    line_index: 2
    kind: stock
    query: "wall clock seconds ticking close-up"
    chyron: "THE TIMER STARTED"
  - shot: 3
    line_index: 3
    kind: card_cve
    cve: "CVE-2026-44338"
    line_a: "Disclosed Tuesday"
    line_b: "Exploited by lunchtime"
  - shot: 7
    line_index: 7
    kind: ai_hero
    chyron: "STOPPED WAITING"
    tags: [worm, npm, server-room]
    keyframe_prompt: "Wide cinematic shot, dim server room aisle..."
    hero_motion: "slow forward camera push, scanline flicker, ..."
  - shot: 8
    kind: card_end
---
```

### `tags:` on `ai_hero` shots (AI library reuse)

`ai_hero` shots may include optional `tags: [a, b, c]` (2–4 short **lowercase** keywords). The render pipeline uses tag overlap to **reuse** older AI keyframes/hero clips from `hyperframes/ai/library/` when:

- At least 1 tag overlaps
- The cached asset is **≥ 7 days old** (freshness cooldown)

If multiple candidates match, the pipeline reuses the **oldest** eligible asset.

Suggested tag taxonomy (mix 2–4 across these classes):

- **Story-class:** `breach`, `ransomware`, `worm`, `phishing`, `0day`, `supply-chain`, `ai-fail`, `vendor-irony`, `regulator`
- **Tech-class:** `npm`, `pypi`, `docker`, `windows`, `linux`, `cloud`, `kubernetes`, `mobile`, `firmware`
- **Visual-class:** `server-room`, `keyboard`, `terminal`, `boardroom`, `binary-stream`, `padlock`

Producer may coin new tags freely — matching is simple set overlap.

### Stock query authoring rules

- Concrete nouns + verbs (what is in frame), not vibes
- Good: "USB drive plugged into laptop close-up", "empty office at dawn fluorescent"
- Bad: "cyberpunk neon code wallpaper"

### Chyron authoring rules

- ALL-CAPS
- Five words max
- Fragment punch (not full sentences)
- One chyron per stock shot

## `[visual:]` directives — b-roll mode

**Applies only when rendering with `--mode b-roll`.** For default `talking-head` mode, skip `[visual:]` directives — Tyler renders over the Decart bg.

In b-roll mode, the pipeline generates 8 Runware stills + 1 hero animated clip. To control what each beat looks like, annotate lines in the script markdown with an inline `[visual: <prompt>]` directive. The directive describes the SCENE; the spoken text stays separate.

Example:

```markdown
**ANCHOR:**
[visual: dim data center aisle, scanlines, racks fading into haze, anonymous silhouette walking away]
Another patch. Another disclosure.

**ANCHOR:**
[visual: fragmenting glass padlock, magenta shards on near-black, depth of field]
The fix arrived. The breach already happened.
```

**Rules:**
- NEVER let the spoken text leak into the visual prompt. Runware will render readable text if you do.
- Avoid faces of real people, brand logos, product names, on-screen typography.
- Keep prompts SHORT and visual (8-15 words). Mood + composition + palette.
- The pipeline appends the LOCKED style suffix automatically — do not repeat it in your directive.
- For the hero clip (the 4s animated b-roll), add a frontmatter field `hero_motion: "..."` describing the camera/scene motion AND set `hero_still_index: N` (1-8) to choose which still gets the animated treatment.

**Frontmatter additions for b-roll mode:**

```yaml
---
title: "..."
runtime_estimate: 1:10
edition: morning   # or evening
source: "..."
source_url: "..."
hero_still_index: 5
hero_motion: "slow zoom into the rack, scanlines flicker"
hosts:
  - ANCHOR (voice Nathaniel — voice_id 7S3KNdLDL7aRgBVRQb1z)
---
```

If `[visual:]` directives are missing, the pipeline falls back to a curated cyberpunk b-roll prompt bank keyed off scene `title`. Directives produce more specific b-roll; the bank is a safe default.

## Story freshness rule

A short must be built from a story ≤ 48h old. The producer agent must:
- Pull recent items from `list_iocs` + `list_focus_items`, sort by date DESC
- Reject the run if no story ≤ 48h old exists — emit a Discord alert and stop, do NOT ship stale
- Always include one `search_awareness` callout for the defensive close

## News-pick heuristics (what makes a good ANCHOR story)

Satirical hit-rate is highest when the story has at least one of:

1. **The thing meant to protect you is the breach point.** (Firewall backdoors, security vendor breached, MFA bypass via the MFA app's own infra.)
2. **The fix doesn't fix it.** (Patch released → exploit survives. "Customers urged to update" → updates don't help.)
3. **The vendor is *also* the auditor.** (Self-attested compliance, vendor-of-vendor with no oversight.)
4. **The deadline is comically short.** (CISA emergency directive, 72-hour disclosure, "by end of business Friday".)
5. **The numbers speak for themselves.** (1,217 / 19 countries / 5 return a smiley face — let the data deliver the joke.)
6. **Customer reaction predictable.** ("Customers reportedly shocked. Analysts reportedly not.")

If the story has none of these, write a different short. Forcing irony onto a clean story produces a flat read.

## Source: ThreatNoir IOCs MCP

```
mcp__threatnoir-iocs__list_focus_items     # current advisories needing action
mcp__threatnoir-iocs__list_weekly_roundups # weekly TL;DR digests (richest signal)
mcp__threatnoir-iocs__list_iocs            # raw IOCs (CVE, malware, etc.)
mcp__threatnoir-iocs__search_awareness     # past lessons (rarely needed)
```

Recommended order:
1. `list_weekly_roundups limit=2` — read the latest TL;DR bullets, pick a satire-friendly one (see heuristics above)
2. (Optional) Fetch the full weekly write-up via `WebFetch https://threatnoir.com/weekly/YYYY-wNN` for technical details
3. `list_focus_items` if you want a still-active advisory specifically

## Animated background (talking-head mode only)

In `talking-head` mode, the default cyber-newsroom backdrop is **animated**, not a still. (B-roll mode does not use HeyGen backgrounds.) Pipeline:

1. Source still: `assets/backgrounds/cyber-newsroom.png` (768×1376 portrait, generated via gemini-imagegen)
2. Decart Lucy Motion call: `python3 scripts/decart_clip.py --image cyber-newsroom.png --trajectory ken-burns --duration 5 --output cyber-newsroom-decart-16x9.mp4`
   - Decart returns 1280×704 horizontal (it always does, regardless of source aspect)
   - The output has actual generative scene-motion: holographic monitors flicker, audio waveforms render, world-map detail shifts
3. Crop to vertical 9:16 LEFT-third (the side with the most visible motion — audio waveforms):
   ```bash
   ffmpeg -y -i cyber-newsroom-decart-16x9.mp4 \
     -vf "crop=396:704:0:0,scale=720:1280:flags=lanczos" \
     -c:v libx264 -pix_fmt yuv420p -preset slow -crf 18 \
     cyber-newsroom-animated.mp4
   ```
4. Upload to HeyGen as **video asset** (not image): `Content-Type: video/mp4`. Save returned `id` to `assets/backgrounds/cyber-newsroom-animated.heygen-asset-id`.
5. Default `cyber-newsroom.heygen-asset-id` (the file `render_short.py` reads) points to the animated video asset id, so all new shorts get animated bg automatically.
6. HeyGen background spec uses `type: "video"` + `play_style: "loop"` — `render_short.py` does this by default.

**Why static crop, not pan:** Decart provides the scene-motion. A horizontal pan on top of that adds jitter; CSS-overlay animations (light-sweep, glow-pulse, glitch flicker, particles) read as visual noise rather than motion. Keep the camera static, let Decart's content move.

**Why LEFT crop, not center:** Decart's center has empty/dim ambient space. The interesting motion (audio waveforms, hologram edges, data displays) lives on the sides. LEFT third gives the most visible animation through the small bg band visible behind Tyler.

**Cost:** ~$0.15 per fresh Decart clip (5s at 720p). One clip is reused across all shorts via the cached HeyGen video asset.

**Lessons learned (do not retry):**
- ffmpeg `zoompan` Ken Burns on a still: too subtle, reads dead.
- Center vertical crop from Decart 16:9: empty bg behind Tyler.
- ping-pong horizontal pan over Decart: jittery on every loop boundary.
- CSS overlays (light-sweep, glow-pulse, glitch RGB flicker, ambient particles): looked like "white sides" / visual noise, not motion. Rejected in prior iterations.
- Desk-line + dark fade above subtitle: tried at multiple positions (under Tyler's hands, at chrome boundary, at frame bottom). All rejected — "Tyler floats" was real but the line was the wrong fix. Removed in v11.

## Composition customization (talking-head mode)

Default (`talking-head`) mode renders via `hyperframes/compositions/talking-head.html` (selected automatically by `render_short.py`). You may tweak overlays/timings there if needed.

`b-roll` mode uses the b-roll template in `hyperframes/index.html` and reads `hyperframes/broll.json` + `hyperframes/timing.json` + `hyperframes/transcript.json` written by the pipeline; you generally do **not** hand-edit the HTML per short.

### 1. Subtitle data (JS array `SUBS`)

From `shorts/short-NNN-slug.timing.json` per-line entries, build:
```js
const SUBS = [
  { start: 0.00, end: 0.93, text: "Good evening." },
  ...
];
```

### 2. Card content (per scene)

| Card | Element | Customize |
|---|---|---|
| Scene 1 | `#breaking` | "▌ BREAKING" — usually keep; adjust label only if non-breaking story |
| Scene 1 | `#headline-card .headline` | Big 2-line headline — strongest punch, accent on second line |
| Scene 1 | `#headline-card .subhead` | One-line subhead with vendor / CVE / threat actor |
| Scene 2 | `#cve-cluster` chips | List CVE numbers + threat actor + technique tag (max 4 chips) |
| Scene 2 | `#survives` text | The "wait, it's worse" stamp — short, all caps, 2 lines max |
| Scene 3 | `#directive` | Either CISA directive number, vendor advisory, or "regulator response". Adjust label, title, deadline |
| Scene 4 | `#punchline` | The closing line, 3 lines max, accent on punchline phrase |

### 3. Card timings (data-start / data-duration)

Match scene boundaries from timing.json. Same-track clips (track-index 2 and 3) need ≥0.3s gap to pass lint.

### 4. Ticker strip items

`#ticker-strip` `.item` elements — list the CVEs, threat actor IDs, advisory IDs from this story. ~6-8 items, repeated for the looping scroll. Ticker is 60px tall, 18px font (sized up since v11 — the original 42px/13px was on the small side).

### 5. End card tagline

Tagline must be **story-specific and short** (≤10 words). Examples:
- "If the firewall is the trust boundary, the trust boundary just moved."
- "The phishing kit had better OPSEC than the bank."
- "Sometimes the vendor is the threat model."

### 6. Audio + avatar duration

Update `data-duration` on:
- `#root` — `audio_duration + 1.5s buffer`
- `#master` and `#avatar` — `audio_duration` (rounded to 2 decimals)
- All overlay clips' `data-start` and `data-duration` to match scene boundaries

## Edition flavor (morning vs evening, since short-004)

The cron runs daily at 08:00 + 18:00 CET. `THREATNOIR_EDITION` env var is set to `morning` or `evening`. Both render_short.py and the producer agent honor it.

| Aspect | Morning (08:00) | Evening (18:00) |
|---|---|---|
| Background asset | `cyber-newsroom.heygen-asset-id` (cool blue/magenta) | `cyber-newsroom-evening.heygen-asset-id` (warm amber/violet, dimmer) |
| Greeting (line 1 of script) | `Good morning.` | `Good evening.` |
| Story-tag color (CSS) | cyan border `#5BB7E0` | amber border `#F2B855` |
| Source feed | ThreatNoir Morning Brief (05:00 UTC) + last-12h /api/articles, /api/legal | ThreatNoir Afternoon Brief (15:00 UTC) + last-12h /api/articles, /api/legal |
| Vibe | "daytime briefing — sharp" | "end-of-day debrief — muted" |

When the agent customizes `hyperframes/index.html`, swap the story-tag border color and adjust greeting text accordingly. `render_short.py` picks the bg automatically from the env var.

## Climax animation variety (since short-004)

Don't end every short with the same red rotating stamp — gets stale fast. Pick climax style by **story type**:

| Story type | Climax | When to use | Visual |
|---|---|---|---|
| **A. Numeric / monetary / volume / time** | **Ticker count-up** | Fines (€40M), data volumes (1.9M records), durations (5 years), counts (100+ companies) | Big number rolls up from 0 to the final value over ~1.5s; freezes; pulses once |
| **B. Trusted entity failed** | **Strikethrough reveal** | Vendor compromised, password manager backdoored, "the firewall worked" | Word appears clean (e.g., "PROTECTED"); 0.3s pause; red diagonal slash draws across; word stays |
| **C. AI-fail / wormable / 0-day / system-fail** | **Glitch RGB-shift burst** | Cursor AI wiped DB, Shai-Hulud worm, npm supply chain | Word appears; RGB channels split horizontally for 0.4s with chromatic aberration; reseats |
| **D. Regulatory / verdict / status** | **Red rotating stamp** (current) | "FINED", "EXPIRED", "COMPLIANCE FAILURE", "PASSED EVERY CHECK" | Stamp drops in, scales 0.7→1.0 with `back.out(2)`, rotates -5°, wobbles once |

Agent picks based on story-frontmatter signals:
- `fines:` array present → A (number ticker on the fine amount)
- "wormable" / "AI" / "agent" / "deleted" / "wiped" in `incident:` → C
- Vendor-name in `source:` + breach context → B
- Regulator (CISA, ED, GDPR action, court ruling) without specific number → D

If the story has both numeric and AI-fail angles, prefer A (ticker on the number) — the data carries more weight than a glitch effect.

### Climax CSS/JS snippets

### CRITICAL: GSAP transform conflict

When animating ANY transform property (`scale`, `rotation`, `x`, `y`, `xPercent`, `yPercent`) on an element that has a CSS `transform: translate(-50%, -50%)` for centering, GSAP overwrites the entire transform — your centering disappears and the element's TOP-LEFT corner ends up at `top:50%; left:50%` instead of its center. **Observed bug in short-005** where €12,501,000 ticker was shoved offscreen-right.

Fix: do not use CSS `transform: translate(-50%, -50%)` for centering on GSAP-animated elements. Use `tl.set(selector, { xPercent: -50, yPercent: -50 }, 0)` at the start of the timeline. GSAP then composes its own transform correctly with all later tweens.

**A. Ticker count-up (centered, GSAP-safe):**
```html
<div id="climax-ticker" class="clip floater" data-start="X" data-duration="Y" data-track-index="3"
     style="top:50%;left:50%;
            font-family:'Space Grotesk',sans-serif;font-weight:900;font-size:160px;
            color:#F2B855;text-shadow:0 0 60px rgba(242,184,85,0.7);
            letter-spacing:-0.04em;text-align:center;opacity:0;">€0</div>
```
```js
// Center via GSAP — NOT CSS transform — so later scale/rotation tweens preserve centering
tl.set("#climax-ticker", { xPercent: -50, yPercent: -50, rotation: -3 }, 0);
const tk = {val:0};
tl.fromTo("#climax-ticker", {opacity:0,scale:0.8},
  {opacity:1,scale:1.0,duration:0.4,ease:"back.out(2)"}, climaxStart);
tl.to(tk, {val:40000000, duration:1.6, ease:"power2.out",
  onUpdate: function() {
    const el = document.querySelector("#climax-ticker");
    if (el) el.innerText = "€" + Math.round(tk.val).toLocaleString("en-US");
  }}, climaxStart + 0.2);
tl.to("#climax-ticker", {scale:1.08,duration:0.2,yoyo:true,repeat:1}, climaxStart + 1.9);
tl.to("#climax-ticker", {opacity:0,duration:0.4}, climaxEnd);
```

**B. Strikethrough reveal (centered, GSAP-safe):**
```html
<div id="climax-strike" class="clip floater" data-start="X" data-duration="Y" data-track-index="3"
     style="top:50%;left:50%;position:relative;
            font-family:'Space Grotesk',sans-serif;font-weight:900;font-size:120px;
            color:#F4F1EA;letter-spacing:-0.03em;opacity:0;">PROTECTED
  <div id="strike-line" style="position:absolute;left:-12px;right:-12px;top:55%;height:8px;
       background:#FF3355;box-shadow:0 0 20px rgba(255,51,85,0.7);
       transform:scaleX(0);transform-origin:left;"></div>
</div>
```
```js
tl.set("#climax-strike", { xPercent: -50, yPercent: -50 }, 0);
tl.fromTo("#climax-strike", {opacity:0,y:20}, {opacity:1,y:0,duration:0.45,ease:"power3.out"}, climaxStart);
tl.to("#strike-line", {scaleX:1,duration:0.5,ease:"power2.inOut"}, climaxStart + 0.6);
tl.to("#climax-strike", {opacity:0,duration:0.4}, climaxEnd);
```

**C. Glitch RGB-shift burst (centered, GSAP-safe):**
```html
<div id="climax-glitch" class="clip floater" data-start="X" data-duration="Y" data-track-index="3"
     style="top:50%;left:50%;position:relative;
            font-family:'Space Grotesk',sans-serif;font-weight:900;font-size:140px;
            color:#F4F1EA;letter-spacing:-0.04em;opacity:0;">WIPED</div>
<div id="glitch-r" style="position:absolute;top:50%;left:50%;
     font-family:'Space Grotesk',sans-serif;font-weight:900;font-size:140px;
     color:#FF3355;letter-spacing:-0.04em;opacity:0;mix-blend-mode:screen;
     pointer-events:none;z-index:18;">WIPED</div>
<div id="glitch-c" style="position:absolute;top:50%;left:50%;
     font-family:'Space Grotesk',sans-serif;font-weight:900;font-size:140px;
     color:#5BB7E0;letter-spacing:-0.04em;opacity:0;mix-blend-mode:screen;
     pointer-events:none;z-index:18;">WIPED</div>
```
```js
// Centering via GSAP — NOT CSS — so later x animations preserve x-centering
tl.set("#climax-glitch", { xPercent: -50, yPercent: -50 }, 0);
tl.set("#glitch-r",      { xPercent: -50, yPercent: -50 }, 0);
tl.set("#glitch-c",      { xPercent: -50, yPercent: -50 }, 0);
tl.fromTo("#climax-glitch", {opacity:0,scale:0.9}, {opacity:1,scale:1.0,duration:0.3,ease:"power2.out"}, climaxStart);
// RGB-shift: x animations now offset from -50% center (not absolute)
tl.fromTo("#glitch-r", {x:-50,opacity:0}, {x:-12,opacity:0.85,duration:0.08}, climaxStart + 0.4);
tl.fromTo("#glitch-c", {x:50,opacity:0}, {x:12,opacity:0.85,duration:0.08}, climaxStart + 0.4);
tl.to("#glitch-r", {x:-4,duration:0.32,ease:"power3.out"}, climaxStart + 0.5);
tl.to("#glitch-c", {x:4,duration:0.32,ease:"power3.out"}, climaxStart + 0.5);
tl.to(["#climax-glitch","#glitch-r","#glitch-c"], {opacity:0,duration:0.4}, climaxEnd);
```

**D. Stamp (current pattern, see short-002/003 for reference)** — keep as-is.

## Story count discipline (1 long OR 2 spine-shared; never 3)

**Applies to BOTH morning bity v3 AND evening longform.** Replaces the old "Two-story morning brief" rule (2026-05-18).

Before writing any line, write a one-sentence **spine** describing what the short is about. The spine is what the viewer should be able to summarize back in one sentence after watching.

Examples of good spines:
- "Two MFA-bypass stories that prove the OTP era is over"
- "NGINX shipped a critical bug that lived in the codebase for sixteen years"
- "Three vendors, one shared dependency, one outage week"

**Litmus test:** if your spine needs "and also" or "meanwhile" to fit, the short is over-stuffed. Drop the weakest beat.

Each short is EITHER:
- **(a) ONE LONG story** — all lines develop one incident / CVE / actor end-to-end (setup → twist → close), OR
- **(b) TWO SHORT beats** — 3-3 split (morning bity v3) or 5-5 / 6-6 (evening longform), AND the two beats MUST share a named spine. The cold-open names the spine; the close ties both beats back to it. Valid shared axes:
  - Same actor (e.g. two Scattered Spider intrusions)
  - Same tactic (e.g. two device-code phishing variants)
  - Same week (e.g. two patches Tuesday CVEs from same vendor)
  - Same vendor (e.g. two Microsoft 365 incidents)
  - Same victim class (e.g. two pharma breaches)

**NEVER three or more stories.** If you have three good beats, drop the weakest and save it for tomorrow. Three threads in 6 lines reads as switchy and viewers lose the through-line (see short-045 2026-05-18 as a counter-example).

Rank ordering when in doubt: single-strong > two-spine-shared > don't publish three.

## Lessons baked in (do not relearn)

1. **Story freshness is enforced (≤48h) — do not ship stale.** If nothing is fresh, alert Discord and stop.
2. **Cost cap is $0.50/short.** The pipeline aborts + alerts Discord if exceeded.
3. **`[visual:]` directives must NEVER include spoken text.** Runware will happily render readable on-screen typography if you leak it.
4. **The LOCKED style suffix is appended automatically.** Do not repeat it in prompts/directives.
5. **Per-word kinetic captions come from ElevenLabs timestamp alignment.** Keep spoken lines clean; avoid stage directions inside spoken text.
6. **`render_short.py` wipes per-line audio before re-rendering.** Do not disable — stale WAVs cause mismatched captions.
7. **Talking-head mode is the default.** It ignores `[visual:]` and uses HeyGen Tyler; in talking-head, HeyGen audio is the master (lip-sync). B-roll is opt-in/experimental.

## Cost guardrail

Per short:
- ElevenLabs TTS: ~$0.05
- Runware stills: ~8 × $0.015 ≈ $0.12
- Runware hero clip: ≈ $0.24

**Target:** ~$0.41/short. **Hard cap:** $0.50/short. Abort + alert Discord if exceeded.

## Pipeline (single command)

```bash
cd /path/to/cyber-news-shorts
python3 scripts/render_short.py --script shorts/short-NNN-slug.md
# default mode is talking-head; for experimental b-roll:
python3 scripts/render_short.py --mode b-roll --script shorts/short-NNN-slug.md
# for stock-broll:
python3 scripts/render_short.py --mode stock-broll --script shorts/short-NNN-slug.md
```

This handles parse → wipe → render audio → visuals (Runware, b-roll mode) → HyperFrames render (and HeyGen only in talking-head mode).

## Reference: short-001 (canonical single-story)

`shorts/short-001-firewall-inside.md` — Cisco ASA/Firepower CVE-2025-20333 / CVE-2025-20362 backdoor surviving firmware updates (UAT-4356, LINA process hooking, CISA ED 25-03). All four heuristics in one story:
- Firewall = trusted protector → compromised
- Firmware update = the fix → doesn't actually fix it
- CISA Emergency Directive = comically short deadline (Apr 30)
- "Working for someone else" = data-driven punchline

End render: `shorts/short-001-firewall-inside-v3.mp4` — 48s, 1080×1920, 18.6 MB. Static cyber-newsroom bg (pre-animated-bg pipeline).

## Reference: short-002 (canonical two-story morning brief)

`shorts/short-002-inside-jobs.md` — DPRK IT-worker infiltration (W16, 100+ US companies including Fortune 500) + Bitwarden CLI npm package compromised (W17, Shai-Hulud worm, wormable, exfiltrates GitHub/SSH/cloud creds). Closes with "Sometimes you hire it. Sometimes you install it." — meta kicker tying inside-threat from both stories.

End render: `shorts/short-002-inside-jobs.mp4` — 52s, 1080×1920, 31.7 MB. **Animated bg** (Decart static LEFT-crop), 60px ticker, no desk-line. This is the template to mimic for new shorts.
