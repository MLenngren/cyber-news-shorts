# Cost guide — what a short actually costs

This pipeline talks to several third-party APIs. Most are pay-as-you-go, a couple are free, and one (Storyblocks) is a flat subscription. Prices below are **approximate** and change — always check each provider's current pricing. The intent is *cents per short*, not dollars.

## Per-provider

| Provider | Used for | Pricing model | Rough cost | Get a key |
| --- | --- | --- | --- | --- |
| **ElevenLabs** | Voiceover (TTS / dialogue) | per character / monthly credits | ~$0.05 / short | https://elevenlabs.io |
| **HeyGen** | Talking-head avatar render | per credit / monthly plan | ~$0.30 / short | https://heygen.com |
| **Runware** | AI hero clip (image→video) + stills | per generation | hero ~$0.24, stills ~$0.015 each | https://runware.ai |
| **OpenRouter** | AI keyframe (Gemini image gen) | per token | ~$0.02 / keyframe | https://openrouter.ai |
| **Pexels** | Stock b-roll search/download | **free** (rate-limited) | $0 | https://pexels.com/api |
| **Storyblocks** | Stock fallback (HMAC-signed) | flat **subscription** | flat | https://storyblocks.com |
| **Decart** | Optional animated background | per generation | ~$0.15 (optional) | https://decart.ai |
| **YouTube Data API** | Publishing (optional) | **free** (daily quota) | $0 | https://console.cloud.google.com |
| **Discord** | Optional failure/notify DMs | free (bot token) | $0 | https://discord.com/developers |

## Per-mode (typical total)

| Mode | APIs hit | Rough $/short |
| --- | --- | --- |
| `talking-head` | HeyGen + ElevenLabs (+ optional Decart) | ~$0.35–0.50 |
| `talking-head-hybrid` | HeyGen + ElevenLabs + Pexels (free) | ~$0.35–0.45 |
| `stock-broll` | Pexels (free) + 1 AI hero (Runware) + keyframe (OpenRouter) + ElevenLabs | ~$0.30–0.45 |
| `b-roll` | Runware stills + hero + ElevenLabs | ~$0.40–0.60 |

## The cheapest way to run

- **Cheapest viable short ≈ $0.05:** `stock-broll` with **only stock + card shots** (no `ai_hero` shot in the script's `shots:` list). That uses Pexels (free) + ElevenLabs (~$0.05) and nothing else. The included `shorts/short-001-example.md` is a minimal script you can adapt.
- Avoid `talking-head*` if you don't want the HeyGen cost — it's the single most expensive line.
- Pexels and the YouTube Data API are free; lean on them.

## Cost controls built in

- **Runware hard cap:** the AI-visual step enforces a per-short cost ceiling (default ~$0.50) and will skip/limit generations rather than overspend. See `scripts/render_hero_clip.py` / `scripts/render_visuals.py`.
- **`--force-visuals` off by default:** cached AI assets are reused across renders of the same short — you only pay once unless you force regeneration.
- **Publishing is opt-in:** nothing uploads unless you pass `--publish` (or set `THREATNOIR_PUBLISH=1`). YouTube is free anyway, but it keeps you in control.

## Notes

- Costs scale with **runtime/characters** (TTS) and the **number of AI shots** (Runware/OpenRouter). A 20s short with one AI hero is the figures above; longer scripts cost proportionally more on TTS.
- The biggest swing is `ai_hero` shots (Runware video). Drop them for near-free shorts.
- HeyGen and Runware credits can be exhausted mid-run — keep an eye on your balances; a failed generation aborts the render.
