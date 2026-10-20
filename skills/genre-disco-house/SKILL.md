---
name: genre-disco-house
description: Use for disco, nu-disco, disco house, French filter house and jazz-inflected house: drum, bass, guitar, string and chord writing, DJ-ready arrangement and mix conventions, layered on the base production skills.
---

# Genre: disco house and its family

This is a genre layer. Use it with `music-production-craft`, `bell-curve-breakers` and `ableton-mcp-studio`. Everything here is idiom: typical, not prescriptive. The curveballs are at the end.

**Lineage, so the choices make sense:**
- **Disco:** Chic, Philadelphia International / MFSB, Salsoul. Live rhythm sections, orchestral strings.
- **Tom Moulton's extended mixes and breaks:** the "disco break" that DJs mix on.
- **Chicago and New York house:** drum machines plus disco loops.
- **French filter house:** filtered disco samples pumping against the kick.
- **Deep and jazz house:** Larry Heard, Kerri Chandler, Masters at Work. Rhodes, extended chords, swing.

## 1. Tempo and feel

| Style | BPM (typical) | Swing |
|---|---|---|
| Disco / nu-disco | 110–125 | Straight to 54 % |
| Disco house | 120–126 | Straight to 54 % (hats can sit at 56–57) |
| French filter house | 120–128 | Straight, the movement is the pump |
| Jazz / deep house | 118–124 | 54–58 % on hats and shakers |

## 2. Drums

**Core pattern (beats in a bar):**
- Kick: 0, 1, 2, 3.
- Snare and/or clap: 1, 3. Disco house often layers both.
- **Open hat on every off-beat 8th (0.5, 1.5, 2.5, 3.5).** This is the disco signature; give it a slightly long decay.
- Closed hats or shaker: 16ths with an accent map (e.g. 100 / 55 / 80 / 50).
- Tambourine: 8ths or 16ths. Congas and bongos answer the hats.

**Feel:**
- Kick on the grid.
- Clap +0.01 to +0.02 beat in jazz house; on the grid in filter house.
- Open hat 0 to −0.005.

**Fills.** Drummer-style tom fills or a snare pickup in the last half-bar of 8- and 16-bar phrases. Vary them, and avoid a snare roll before every section.

## 3. Bass (the Bernard Edwards grammar)

From Edwards himself, Jerry Barnes and Guitar World's lessons on his lines:
- "My basslines are usually a reaction to [Nile's] guitar rhythms" (Edwards);
- octaves are a flourish, not the whole line;
- staccato downbeats alternate with slides;
- open strings are ghosted;
- "equally important to the pitches are the durations" (Barnes).

The canonical study is "Good Times": a vamp in E minor with a Dorian (i–IV7) flavour.

**In MIDI** (register E0–E2, MIDI 28–52):

| Element | How to write it |
|---|---|
| Staccato hits | 0.12–0.2 beat |
| Held notes | Full value, for contrast |
| Dead notes | Velocity 20–35, 0.05–0.08 beat, at the next real note's pitch or an octave below |
| Slides | A grace note 1–2 semitones below, 0.06 beat early, about 20 velocity softer. Or, on a mono synth, glide on with overlapping legato notes |
| "Chuck" | A muted attack on the 16th before a downbeat |
| Pushes | The next chord's root on 3.75 |

**Choosing a line:**
- **Driving octave bass** (root low/high 8ths): energy and the peak sections.
- **Edwards-style syncopated line:** groove sections.
- **Filter house:** the bass is often inside the sample loop. Keep a sub underneath, sidechained.

## 4. Guitar, clav and keys rhythm

- **Chicken scratch:** muted 16ths at velocity 30–50, with chord stabs (0.08–0.15 beat) on accents. Nile Rodgers-style voicings sit high (9ths and 13ths on the top strings).
- **Write it first, then the bass answers it** (call and response). Check that together they cover most 16ths and share mostly downbeats.
- **Clavinet or Rhodes:** off-beat stabs (0.5, 1.5 …) or 16th comping.
- **Jazz house Rhodes:** min9 and maj9 voicings, tremolo or chorus, stabs held just under a beat.

## 5. Strings, horns and the orchestral layer

**Strings:**
- **Lines in octave unison** (violins doubled an octave up) for themes and counter-melodies.
- **Sustained pads** in close voicings above C3 with a slow attack, high-passed around 250 Hz.
- **Fast scalar runs into downbeats:** 16ths or 32nds over the last beat, landing on the new section.
- **Off-beat staccato stabs.**
- **Swells into sections:** `write_clip_automation` on volume or filter with an `s_curve`.
- Keep strings out of the bass and keys registers. They should be bright and wide.

**Horns:** unison stabs and short riffs on off-beats, as answers to the vocal or lead.

## 6. Harmony

- **Vamps:** maj7, min7, 9 and 11 chords over one or two chords:
  - Dorian i–IV7 (Em7–A7, Am9–D9);
  - min9 to maj7 a 4th up (Am9–Dmaj7 is a bright lift);
  - descending maj7 chains.
- **Turnarounds:** ii–V and iii–vi–ii–V, plus chromatic passing chords in the last bar of a phrase.
- **Disco house and French house:** loops of 1–2 chords; planed chords; a filter carries the development, not the harmony.
- **Jazz house:**
  - extended ii–V–I with tritone subs;
  - min11 stabs voiced in 4ths;
  - a pedal under moving Rhodes chords.

## 7. Arrangement (DJ-ready)

| Section | Bars | Content |
|---|---|---|
| Intro | 16–32 | Kick, hats, percussion (mixable, no harmony) |
| Groove A | 16 | + bass |
| Groove A′ | 16 | + guitar or keys rhythm |
| Break | 8–16 | Moulton-style: strip to percussion + bass, then rebuild layer by layer; strings or keys theme |
| Build | 8 | Filter opening (`exp` curve), string run, fills |
| Main | 32 | Everything; strings theme or vocal hook |
| Mid-break | 8 | Rhythm-section-only break or filtered drop |
| Main′ | 16 | Variation: counter-line, octave bass |
| Outro | 16–32 | Back to rhythm for the DJ |

Filter house builds by sweeping a low-pass on the loop over 8–16 bars, then dropping to the full band.

## 8. Mix

- **Disco bass** needs mid presence (roughly 700 Hz–1.5 kHz: the finger and pick attack) to read; the sub alone won't carry the line.
- **Sidechain:** light in disco and jazz house; heavy, audible pump in French house.
- **Hats and strings:** bright, with wide strings. Keep the kick and the bass fundamental mono.
- **Loudness:** for club use, the club master range in `music-production-craft`.

## 9. Genre curveballs (with `bell-curve-breakers` rules)

- **Edwards break:** 4 bars with only bass and chord guitar, kickless, the bass carrying the groove.
- **String run into an early drop**, 4 bars ahead of where the build points.
- **Up-a-whole-step last main section** (classic disco lift), bass and chords only.
- **Jazz reharmonisation of the hook in the breakdown:** tritone subs, chromatic mediants.
- **Pump on the wrong source:** pads ducked by the off-beat hat instead of the kick.
- **Swing contrast:** straight drums with 56–58 % shakers and Rhodes (`transform_clip_notes` for exact values).

## 10. Starting template (our tools)

1. **Tracks:** Kick, Clap, Hats, Perc, Bass, Guitar/Clav, Keys, Strings, FX, plus returns A (short room) and B (1/8-dotted Echo).
2. **Grooves:** "Swing MPC 3000 16ths 54" (or Basic "Swing 16ths 54") on hats and percussion, none on kick and bass. In jazz house, try 57 on shakers and keys, or exact 56–58 via `transform_clip_notes`.
3. **Bass:** Compressor keyed from the kick via `set_sidechain` (light: 1–3 dB of ducking).
4. **First render:** the main section, compared to the user's reference. Then the kick + bass stem.
