#!/usr/bin/env bash
# Cyber News Shorts cron example — daily morning + evening editions
#
# This script is an OSS-friendly EXAMPLE runner for the autonomous producer.
# It does not assume any private repos, home-directory paths, or operator IDs.
#
# Pass morning|evening as the first arg (default: auto from $HOUR).
# Logs to /tmp/cyber-news-{morning,evening}-YYYY-MM-DD.log
# If OPERATOR_DISCORD_ID is set (non-empty), it will send a best-effort Discord
# DM via scripts/discord_notify.py on completion or error.

set -euo pipefail

# Resolve edition from arg or current hour
EDITION="${1:-}"
if [ -z "$EDITION" ]; then
  H=$(date +%H)
  if [ "$H" -lt 12 ]; then EDITION="morning"; else EDITION="evening"; fi
fi
case "$EDITION" in morning|evening) ;; *) echo "edition must be morning|evening" >&2; exit 2 ;; esac

LOG=/tmp/cyber-news-${EDITION}-$(date +%Y-%m-%d).log
PROJ=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
CLAUDE_BIN=${CLAUDE_BIN:-$(command -v claude || true)}

# OSS safety: default is empty, so no DMs are sent.
OPERATOR_DISCORD_ID=${OPERATOR_DISCORD_ID:-}

# Best-effort Discord DM; no-op unless OPERATOR_DISCORD_ID is set.
notify() {
  [ -z "$OPERATOR_DISCORD_ID" ] && return 0
  "$PYTHON_BIN" "$PROJ/scripts/discord_notify.py" \
    --user-id "$OPERATOR_DISCORD_ID" --message "$1" >/dev/null 2>&1 || true
}

# Mean Y-average luma (0-255) across a clip; prints -1 if unmeasurable.
# ~24 = black, 50-130 = normal SDR content.
luma_of() {
  local out
  out=$(ffmpeg -hide_banner -nostats -i "$1" \
    -vf "signalstats,metadata=print:key=lavfi.signalstats.YAVG" -f null - 2>&1) || true
  printf '%s\n' "$out" | grep -oE "YAVG=[0-9.]+" \
    | awk -F= '{s+=$2;n++} END{ if(n>0) printf "%.1f", s/n; else printf "-1" }'
}

# Auto-publish after render (opt-in; default off)
export THREATNOIR_PUBLISH=${THREATNOIR_PUBLISH:-0}

# Edition flavor: render_short.py picks bg + the producer agent picks
# greeting + climax style based on this env var.
export THREATNOIR_EDITION="$EDITION"

cd "$PROJ" || exit 1

# Optional: activate venv if present.
if [ -f "$PROJ/venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$PROJ/venv/bin/activate"
fi

# Edition rotation default (override with THREATNOIR_MODE).
if [ -z "${THREATNOIR_MODE:-}" ]; then
  if [ "$EDITION" = "morning" ]; then
    export THREATNOIR_MODE="stock-broll"
  else
    export THREATNOIR_MODE="talking-head-hybrid"
  fi
fi
MODE=${THREATNOIR_MODE}

PUBLISH_INSTR="7. Run scripts/render_short.py --mode ${MODE} --script shorts/short-NNN-<slug>.md."
if [ "${THREATNOIR_PUBLISH:-0}" = "1" ]; then
  PUBLISH_INSTR="7. Run scripts/render_short.py --mode ${MODE} --publish --script shorts/short-NNN-<slug>.md."
fi

BRIEF_HINT=""
if [ -n "${NEWS_BRIEF_URL:-}" ]; then
  BRIEF_HINT="Source a story from NEWS_BRIEF_URL=${NEWS_BRIEF_URL}. If it is empty or unreachable, require --topic and stop."
fi


# Editorial rules are edition-specific.
if [ "$EDITION" = "morning" ]; then
  EDITORIAL_RULES="Morning bar: tight 6–7 lines, ≤12 words/line, cold-open with the hardest fact, two sarcastic beats minimum, defensive close with one actionable takeaway. Do not speak raw IOCs (IPs/ports/hashes/paths) aloud."
else
  EDITORIAL_RULES="Evening bar: 10–14 lines, ≤16 words/line, analytical structure (what happened / who's at risk / why it matters) and a concrete takeaway at the end. Do not speak raw IOCs (IPs/ports/hashes/paths) aloud."
fi

		STORY_COUNT_RULE="Story count discipline (applies to BOTH morning and evening). Before writing any line, write a one-sentence SPINE describing what the short is about (e.g. \"Two MFA-bypass stories that prove the OTP era is over\"). If the spine needs \"and also\" or \"meanwhile\" to fit, the short is over-stuffed — drop the weakest beat. Each short is EITHER (a) ONE LONG story: all lines develop one incident / CVE / actor end-to-end (setup → twist → close), OR (b) TWO SHORT beats: 3-3 split (morning) or 5-5 / 6-6 (evening), and the two beats MUST share a named spine — same actor, same tactic, same week, same vendor, or same victim class. The cold-open names the spine; the close ties both beats back to it. NEVER three or more stories. If you have three good beats, drop the weakest and save it for tomorrow."

PROMPT="Use the cyber-news-shorts-producer agent to produce today's ${EDITION^^} cyber news short.

Edition: ${EDITION} ($(date -Iseconds))
Mode: ${MODE}

Steps for the agent:
1. Fetch fresh news. ${BRIEF_HINT}
   If no NEWS_BRIEF_URL is available, require the caller to provide --topic.
2. Read the last ~10 shorts/short-*.md frontmatter to identify topics already covered (CVE numbers, threat actors, vendor names). Do NOT pick anything that overlaps.
3. Pick the strongest satirical beat per the heuristics in the cyber-news-shorts skill (breach / fine-paid / ironic-vendor / wormable / 0-day / AI-fail).
4. Determine next short id (max(NNN) + 1 from shorts/short-NNN-* files).
5. Draft shorts/short-NNN-<slug>.md in the dry-anchor voice. ${EDITORIAL_RULES} ${STORY_COUNT_RULE}
6. For ${MODE} mode:
	   - stock-broll: ALSO author a shots: list in YAML frontmatter (5-7 stock shots with concrete Pexels queries + ALL-CAPS ≤5-word chyrons, optionally 1 card_cve, 1 ai_hero with keyframe_prompt + hero_motion + tags: [a, b, c], 1 card_end). For ai_hero shots, include tags: [a, b, c] (2-4 short lowercase keywords: story-class + tech-class + visual-class) so the AI library can reuse older hero assets after a 7-day cooldown. NO [visual:] inline directives. See the cyber-news-shorts SKILL for the convention.
   - talking-head: NO shots: list, NO [visual:] directives. Renders via hyperframes/compositions/talking-head.html.
	   - talking-head-hybrid: NO shots: list, NO [visual:] directives. ALSO author cutaways: in YAML frontmatter (2-4 entries with line_index + pexels_query + duration). Renders via hyperframes/compositions/talking-head-hybrid.html.
${PUBLISH_INSTR}
8. Verify output.

Reply with:
- Edition + picked topic + source URL
- Output MP4 absolute path
- Duration + file size
- YouTube URL (if --publish was set)
- Cost summary (Runware + HeyGen + ElevenLabs where applicable)

Keep reply under 30 lines."

# --- Layer 0: pre-flight network check -------------------------------------
# Fail fast (no spend) if the network is down. Probe the paid providers the
# pipeline actually calls; add NEWS_BRIEF_URL when configured. Require >=2 up.
PREFLIGHT_EPS=(https://api.anthropic.com https://api.elevenlabs.io https://api.pexels.com)
[ -n "${NEWS_BRIEF_URL:-}" ] && PREFLIGHT_EPS+=("$NEWS_BRIEF_URL")
PREFLIGHT_UP=0
for EP in "${PREFLIGHT_EPS[@]}"; do
  CODE=$(curl -sS -o /dev/null -m 8 -w '%{http_code}' "$EP" 2>/dev/null || echo 000)
  if [ "$CODE" != "000" ]; then PREFLIGHT_UP=$((PREFLIGHT_UP + 1)); fi
done
if [ "$PREFLIGHT_UP" -lt 2 ]; then
  echo "=== PREFLIGHT FAIL: only ${PREFLIGHT_UP}/${#PREFLIGHT_EPS[@]} endpoints reachable — network looks down; skipping ${EDITION} run ===" | tee -a "$LOG"
  notify "Cyber news ${EDITION} short SKIPPED at $(date -Iseconds) — network unreachable (${PREFLIGHT_UP}/${#PREFLIGHT_EPS[@]} endpoints up). No render attempted, no spend. Log: $LOG"
  exit 1
fi
echo "=== preflight OK: ${PREFLIGHT_UP}/${#PREFLIGHT_EPS[@]} endpoints reachable ===" | tee -a "$LOG"

# Carries the producer exit status out of the (piped -> subshell) run block below.
STATUS_FILE="/tmp/cyber-news-${EDITION}-status.$$"

{
  echo "=== Cyber News Shorts (${EDITION}) — $(date -Iseconds) ==="
  if [ -z "$CLAUDE_BIN" ]; then
    echo "ERROR: claude not found in PATH. Set CLAUDE_BIN or install claude." >&2
    exit 127
  fi
  # Capture the producer's real exit code WITHOUT tripping `set -e` (a non-zero
  # exit must reach the Layer-2 health verdict below, not abort the script).
  STATUS=0
  "$CLAUDE_BIN" -p "$PROMPT" --verbose 2>&1 || STATUS=$?
  echo "=== claude exit status: $STATUS ==="
  echo "$STATUS" > "$STATUS_FILE"
} | tee -a "$LOG"

# Find the most recently produced short MP4 (within last 30 min)
LATEST_MP4=""
if [ -d "$PROJ/shorts" ]; then
  LATEST_MP4=$(find "$PROJ/shorts" -maxdepth 1 -name 'short-*.mp4' -type f -mmin -30 -printf '%T@ %p\n' \
    | sort -nr | head -1 | cut -d' ' -f2-)
fi

# --- Layer 2: health verdict ------------------------------------------------
# Exit code 0 is necessary but NOT sufficient — a render can succeed yet emit a
# black or truncated short (the in-process quality gate is Layer 1). Verify
# substance (producer exit status, file size, mean luma, log error signatures)
# and report an ACCURATE outcome instead of a misleading "success".
STATUS=$(cat "$STATUS_FILE" 2>/dev/null || echo 1); rm -f "$STATUS_FILE"
HEALTH_OK=1
HEALTH_REASON=""
LUMA="n/a"
add_reason() { HEALTH_REASON="${HEALTH_REASON:+$HEALTH_REASON; }$1"; HEALTH_OK=0; }

if [ "${STATUS:-1}" -ne 0 ]; then add_reason "producer exit=$STATUS"; fi
if grep -qiE "PAGEERROR|QUALITY GATE FAILED|RenderQualityError" "$LOG" 2>/dev/null; then
  add_reason "error signature in log"
fi
if [ -n "$LATEST_MP4" ]; then
  SZ=$(stat -c%s "$LATEST_MP4" 2>/dev/null || echo 0)
  if [ "${SZ:-0}" -lt 2000000 ]; then add_reason "tiny file ${SZ}B"; fi
  LUMA=$(luma_of "$LATEST_MP4" || true)
  if awk "BEGIN{exit !(${LUMA:--1} >= 0 && ${LUMA:--1} < 30)}"; then
    add_reason "near-black mean_luma=$LUMA"
  fi
else
  add_reason "no MP4 produced"
fi

if [ "$HEALTH_OK" -eq 1 ]; then
  SIZE=$(du -h "$LATEST_MP4" | cut -f1)
  DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$LATEST_MP4" 2>/dev/null | xargs printf '%.0f')
  echo "=== HEALTH OK: ${EDITION} short ready (mean_luma=$LUMA) ===" | tee -a "$LOG"
  notify "$(printf '**Cyber news %s short ready**\n\nPath: %s\nDuration: %ss\nSize: %s\nLuma: %s\n\nLog: %s' \
    "$EDITION" "$LATEST_MP4" "$DUR" "$SIZE" "$LUMA" "$LOG")"
else
  echo "=== HEALTH FAIL: $HEALTH_REASON ===" | tee -a "$LOG"
  notify "Cyber news ${EDITION} short FAILED at $(date -Iseconds) — ${HEALTH_REASON}. Log: $LOG"
fi
