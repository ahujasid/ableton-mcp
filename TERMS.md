# AbletonMCP Terms & Data Use

_Last updated: 13 August 2026_

These terms cover the data AbletonMCP collects. The software itself is licensed under [MIT](LICENSE) — that license governs the code and grants no rights over your data. This document covers the data.

Running your own fork with your own Supabase credentials? None of this applies. Nothing reaches us, and you become responsible for your own users' data.

## Who holds the data

AbletonMCP is an independent open-source project maintained by Siddharth Ahuja. There's no company behind it.

Both tiers write to a Supabase project (PostgreSQL) over HTTPS. The anon key shipped in client configs is **insert-only** and can't read rows back; reads require a `service_role` key kept in the maintainer's environment.

**Contact, including deletion requests: ahujasid@gmail.com**

## The two tiers

|  | Anonymous telemetry | Dataset recording |
|---|---|---|
| Default | On | **Off — opt-in** |
| Your content (prompts, MIDI, names) | Never | Yes |
| Device & sound design parameters | Never | Yes |
| Turn on | — | `ABLETON_MCP_ENABLE_DATASET=true`, or say yes when asked in the chat |
| Turn off | `ABLETON_MCP_DISABLE_TELEMETRY=true` | `ABLETON_MCP_DISABLE_DATASET=true` |

**The split is content.** The anonymous tier counts installs and tool calls and carries nothing you made, so it runs by default. Everything that contains your actual work is opt-in and stays off until you say yes.

`ABLETON_MCP_DISABLE_TELEMETRY` turns off both tiers; `ABLETON_MCP_DISABLE_DATASET` turns off dataset recording only and overrides any stored grant.

Neither sends anything unless Supabase credentials are configured. No credentials ship with the package.

### Anonymous telemetry

Collects: a random installation ID, a per-run session ID, package/Python/OS/Ableton versions, which tools ran, success and duration, and error messages with emails and filesystem paths stripped.

Collects no prompts, no musical content, no names, no audio.

The installation ID is a random UUID generated on first run and stored in `customer_uuid.txt` under your OS app-data directory (`~/Library/Application Support` on macOS, `%APPDATA%` on Windows, `~/.local/share` on Linux). It isn't derived from your hardware, username, or any account — it exists to count distinct installs rather than raw events. Delete that file and you get a new identity, unlinked from anything recorded before.

Legal basis: legitimate interest in maintaining the software. Opt out any time with the variable above.

### Dataset recording

Off unless you turn it on. Collects your prompts, your MIDI (pitch, timing, duration, velocity), session structure, track and clip names, preference labels, and browser auditions. No audio is ever recorded or uploaded.

It also records **sound design state**: the full parameter set of every device on every track — including devices nested inside instrument, drum, and audio effect racks, and on the master chain. In practice that means envelope settings (attack, decay, sustain, release), filter and LFO settings, oscillator and synth knob positions, effect parameters, macro values, automation state, and per-clip gain, pitch, and warp settings. If you built a patch or dialled in a mix, the resulting parameter values are recorded alongside the action that produced them.

Generic musical labels (`Bass`, `Drums`, `Verse`) are kept for training signal; other names — including rack chain names — become placeholders like `<name:17>`. Emails and absolute paths are stripped from prompts and errors. This is best-effort pattern matching, not a guarantee — it can't catch personal information typed into a prompt in an unanticipated form.

Recording is off by default and never starts on its own. You are asked once — as a dialog if your client supports it, otherwise as a message in the chat — and recording begins only if you say yes. An unanswered question means no, and on clients that cannot show the prompt nothing is ever recorded. Your answer is stored locally in `~/.ableton-mcp/consent.json`.

Legal basis: consent, given by you before anything is recorded.

Withdraw consent any time by saying so in the chat, deleting `~/.ableton-mcp/consent.json`, or setting `ABLETON_MCP_DISABLE_DATASET=1`, which overrides any stored answer.

## What you grant by turning dataset recording on

A non-exclusive, irrevocable, worldwide, royalty-free license to use your recorded trajectories — prompts, MIDI, session structure, device and sound design parameters, preference labels — to train and evaluate models, and to publish or share datasets derived from them.

Derived datasets may be released publicly or shared with research collaborators. That decision hasn't been made yet; the grant is written to allow it.

**You keep ownership and copyright in your music.** This grants use, not exclusivity. Nothing here limits what you do with your own work.

Only turn this on if you have the right to grant that for everything you record. If you're working on someone else's material, under an NDA, or on a label deal with delivery restrictions, leave it off — it stays off unless you opt in.

## Retention and deletion

Rows are kept **indefinitely**. There's no automatic expiry.

To have yours deleted, email ahujasid@gmail.com with your installation ID (from `customer_uuid.txt`) or your session IDs. No charge, no need to explain why.

**One limit, stated plainly:** data already folded into a trained model can't be pulled back out. Training isn't reversible, and retraining from scratch to exclude one contributor isn't something this project can commit to. Deletion covers the stored rows and any *future* training run — not a model that has already seen them.

If that's not acceptable to you, turn dataset recording off before you start. Deleting afterwards won't fully undo it.

Backups and export snapshots taken before a deletion request may persist until they age out of ordinary rotation.

## Your rights

Depending on where you live (GDPR in the EEA/UK, CCPA/CPRA in California, and comparable laws elsewhere) you may have the right to access, correct, delete, export, or object to processing of your data, and to withdraw consent. Email ahujasid@gmail.com to exercise any of them.

## Children

Not directed at children under 13 (under 16 in the EEA). We don't knowingly collect their data — email us if you believe we have, and it'll be deleted.

## Changes

Material changes get a new date above and a note in the release notes. This is a versioned package, so the terms in effect for you are the ones shipped with the version you're running. If you disagree with a change, disable the relevant tier or stop using the package.

## Summary

- Anonymous telemetry: on, no creative content, one variable away from off.
- Dataset recording: off until you explicitly opt in; you can disable it at any time.
- Nothing is sent without configured credentials.
- You can get your rows deleted; you can't un-train a model.
