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

{
  echo "=== Cyber News Shorts (${EDITION}) — $(date -Iseconds) ==="
  if [ -z "$CLAUDE_BIN" ]; then
    echo "ERROR: claude not found in PATH. Set CLAUDE_BIN or install claude." >&2
    exit 127
  fi
  "$CLAUDE_BIN" -p "$PROMPT" --verbose 2>&1
  STATUS=$?
  echo "=== claude exit status: $STATUS ==="
} | tee -a "$LOG"

# Find the most recently produced short MP4 (within last 30 min)
LATEST_MP4=""
if [ -d "$PROJ/shorts" ]; then
  LATEST_MP4=$(find "$PROJ/shorts" -maxdepth 1 -name 'short-*.mp4' -type f -mmin -30 -printf '%T@ %p\n' \
    | sort -nr | head -1 | cut -d' ' -f2-)
fi

# Discord notification (best-effort)
if [ -n "$OPERATOR_DISCORD_ID" ]; then
  if [ -n "$LATEST_MP4" ]; then
    SIZE=$(du -h "$LATEST_MP4" | cut -f1)
    DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$LATEST_MP4" 2>/dev/null | xargs printf '%.0f')
    MSG=$'**Cyber news short ready ('"${EDITION}"$')**\\n\\nPath: '"$LATEST_MP4"$'\\nDuration: '"${DUR}s"$'\\nSize: '"$SIZE"$'\\n\\nLog: '"$LOG"
  else
    MSG="Cyber news short FAILED (${EDITION}) at $(date -Iseconds). Log: $LOG"
  fi
  "$PYTHON_BIN" scripts/discord_notify.py --user-id "$OPERATOR_DISCORD_ID" --message "$MSG" >/dev/null 2>&1 || true
fi
