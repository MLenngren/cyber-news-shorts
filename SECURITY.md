# Security Policy

## Reporting a vulnerability

Please report security issues **privately**, not as a public issue.

Use GitHub's private reporting: **Security tab → "Report a vulnerability"** (private security advisory). We'll acknowledge and work a fix before any public disclosure.

## Secrets and credentials

This pipeline integrates with several third-party APIs (ElevenLabs, HeyGen, Runware, Pexels, Storyblocks, OpenRouter, YouTube, Discord, Decart). **All credentials are read from environment variables** (or optional 1Password `op://` references when `OP_SERVICE_ACCOUNT_TOKEN` is set). 

- Never commit `.env` or real API keys. `.env` is gitignored.
- CI rejects commits containing secret-like strings.
- The pipeline never DMs or emails anyone by default — operator-specific identifiers (e.g. `OPERATOR_DISCORD_ID`) default to empty.

## Supported versions

The current `main` (v0.1) is the supported line.
