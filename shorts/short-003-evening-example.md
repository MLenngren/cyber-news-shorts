---
# `title` doubles as the on-screen story-headline card — keep it a real, punchy
# headline (~30 chars renders cleanly), not a file label.
title: "Patch Exists, Nobody Applied It"
edition: evening
elevenlabs_voice_id: "7S3KNdLDL7aRgBVRQb1z"
heygen_avatar_id: "Tyler-incasualsuit-20220721"
hosts:
  - ANCHOR
opener_text:
  - "PATCH SHIPPED"
  - "NOBODY APPLIED IT"
ambient_query: "abstract server rack warm amber dim slow pan data center"
# Pexels b-roll cutaways layered over the avatar at specific spoken lines.
cutaways:
  - line_index: 2
    pexels_query: "data center server racks rows blue light slow pan"
    duration: 4.0
  - line_index: 4
    pexels_query: "system administrator hands typing keyboard close-up dark"
    duration: 3.5
# One short on-screen caption per spoken line ([brackets] highlight in yellow).
subtitles:
  - line_index: 1
    text: "FIX IS [TWO YEARS] OLD"
  - line_index: 2
    text: "[NO PASSWORD] NEEDED"
  - line_index: 3
    text: "RUNS THE [BUSINESS APPS]"
  - line_index: 4
    text: "[EXPLOIT CODE] PUBLIC"
  - line_index: 5
    text: "PATCH [TODAY]"
---

## [SCENE 0 — Cold open]

**ANCHOR:**
A fix shipped two years ago, and the servers are still getting hit.

## [SCENE 1 — What happened]

**ANCHOR:**
A critical flaw in a widely used application server lets an attacker run code with no password.

**ANCHOR:**
That server hosts the business-critical apps, so one exposed box is a foothold into everything behind it.

## [SCENE 2 — Why it matters]

**ANCHOR:**
Public exploit code has existed since disclosure, yet thousands of these servers still sit unpatched on the open internet.

**ANCHOR:**
The takeaway: inventory your internet-facing application servers and apply the vendor patch today. The exploit is not waiting.
