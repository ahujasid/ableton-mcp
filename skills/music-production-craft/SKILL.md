---
name: music-production-craft
description: Use when writing, arranging, sound-designing or mixing a track: applied theory, groove, arrangement and mix technique, and how each choice ripples through the others.
---

# Music production craft

Production is one set of decisions seen from four sides: **harmony, rhythm, sound/register and structure/energy**, plus the mix that reveals them. Change one side and the others move. A dense chord is a mix problem, a busy bassline is a kick problem, and a weak drop is an arrangement problem.

This skill is genre-neutral. Genre conventions (tempos, signature parts, references) live in the `genre-*` and `colour-*` skills. Execution in Live is `ableton-mcp-studio`; avoiding the average is `bell-curve-breakers`.

## 1. How the layers interact

| If you change… | …it affects | So |
|---|---|---|
| Chord voicing density or register | Low-mid mud (200–500 Hz), space for bass and vocal | Thin or raise the voicing (drop the root or 5th, move it up) before you reach for EQ. |
| Bass rhythm | The kick, how much sidechain is needed, the pocket | Decide first: the bass avoids the kick (off-beats) or locks with it (same hits, ducked). |
| The rhythm section's onset grids | Groove density, clarity | Instruments should answer each other: together they cover most 16ths, but share mostly downbeats (section 3). |
| Microtiming profile | Feel (laid-back vs urgent) | Make offsets systematic per role. Uniform timing across every role is what sounds programmed, not the grid itself. |
| Harmonic rhythm | Energy, "song vs groove", how long a section can run | Slow = hypnotic, so long sections work. Fast = song-like, so it needs more arrangement change. |
| Tempo | Swing amount, delay and reverb times, note lengths | Slower tempos take more swing and longer tails. Recompute synced times after a tempo change. |
| Mode or key | Colour note, which notes clash, sub frequency, kick tuning | Feature the colour note. Tune the kick to the root or 5th. Low keys (E, F) put the sub around 41–44 Hz. |
| Articulation | Groove tightness, how reverb reads | Short notes + reverb = space and bounce. Long notes + reverb = wash. |
| Velocity | Timbre (most sounds brighten with velocity), groove | Accent maps are timbral, so shape them. |
| Arrangement density | Every mix decision | If a part needs heavy EQ to fit, the register is overcrowded: mute or move something. |
| Melody register | Vocal space, lead presence (2–5 kHz) | Keep the lead and the top chord voice in different octaves, or have them take turns. |

**Diagnose by layer before fixing:**
- Muddy: register and voicing first, EQ last.
- Weak drop: what was removed before it, not what gets added.
- Boring: harmonic rhythm, rhythmic displacement, timbral movement.
- Busy: more than three foreground parts, or parts colliding on the same 16ths in the same register.
- Lifeless: flat velocity, static sounds, no automation.
- Cheap: root-position triads, untouched presets, every phrase resolving to the tonic on beat 1.

**Decision order for a new track:**
1. A one-sentence brief: feel, 2–3 references, where it will be played.
2. Tempo and groove.
3. **A 4-bar rhythm-section loop that already grooves** (drums, bass, one chord-rhythm part), before any colour. Chic cut records this way: the rhythm section went in first, live, then strings, horns and vocals.
4. Harmony.
5. Hook or motif.
6. Arrangement.
7. Sound.
8. Mix.
9. Master.

## 2. Harmony

**Modes and their colour notes** (A as the tonic):
- Dorian, F♯: the bright minor.
- Aeolian, F: dark.
- Phrygian, B♭: tense, flat 2nd.
- Phrygian dominant, B♭ + C♯: flat 2nd with a major 3rd. This is the equal-tempered stand-in for maqam Hijaz; for the real thing see `colour-maqam-fusion`.
- Mixolydian, G over A major: bluesy major.
- Lydian, D♯: floating.

**Voicings:**
- 7ths and 9ths are the default; 11ths and 13ths add colour.
- Rootless voicings when the bass has the root:
  - min9 = ♭3 5 ♭7 9 (Am9 → C E G B)
  - maj9 = 3 5 7 9
  - dom13 = 3 13 ♭7 9 or ♭7 9 3 13
- min11 stacked in 4ths (A D G C E) gives a modern stab.
- Quartal stacks sound modal: "So What" = E A D G B.
- Voice-lead by common tones and steps. Parallel motion (planing) is a deliberate effect.

**Low-interval limits.** These are the lowest *bottom* note, in Live naming, at which each interval stays clear:

| Interval | Lowest bottom note |
|---|---|
| m2 | E2 (52) |
| M2 | D♯2 (51) |
| m3 | C2 (48) |
| M3, P4 | A♯1 (46) |
| Tritone | B1 (47) |
| P5 | A♯0 (34) |
| 6ths, 7ths | F1 (41) |
| m9 | E1 (40) |
| M9 | D♯1 (39) |

Two rules matter more than the table:
1. Check rootless voicings against the **implied bass note**, not just between chord tones.
2. Limits are softer for dark, sine-like sounds and stricter for bright, saturated ones.

This is a rule of thumb, and sources differ by a few semitones. Short version: no 2nds below E2, no 3rds or 4ths below A♯1, only 5ths and octaves below about D♯1, octaves only below A♯0. `review_clip` checks the table automatically.

**Progressions and moves:**
- ii–V–I (Dm9–G13–Cmaj9); minor ii–V–i (Bm7♭5–E7♭9–Am9).
- Tritone substitution (D♭7 for G7).
- Backdoor (Fm7–B♭7–C).
- Modal interchange (iv, ♭VI, ♭VII in major).
- Secondary dominants.
- Pedal points (chords move over a held bass).
- Planing.
- Chromatic mediants: move the root a third and keep the chord's quality (Am→Cm, C→E♭). It leaves the key while sharing one common tone.
- Anticipate changes by a 16th or 8th in bass and chords together.

**Harmonic rhythm.** Loop-based music changes chord every 1–2 bars or stays on one. Song-based music changes every bar or faster.

**Melody.**
- Rhythm first: a hook is mostly a rhythm plus one memorable interval.
- Chord tones on strong beats; tensions held as colour; passing notes on weak 16ths.
- Develop 1–2-bar motifs: sequence, invert, displace, augment.
- Give each section its own register or contour.

## 3. Rhythm and groove

**Microtiming.** Studies of expert players (e.g. Kilchenmann & Senn's drum-and-bass recordings) suggest their timing deviations are consistent and style-specific rather than noise. In listening tests, perfectly quantised parts groove about as well as competent performances, while exaggerated timing grooves worst. In Senn et al. 2016 they were rated equal; in Datseris et al. 2019, listeners (mostly jazz musicians) rated quantised versions slightly more swinging than the originals.
- Choose a profile per role and keep it consistent: kick on the grid, backbeat a little late for laid-back, hats pushed for urgency, bass locked or slightly behind.
- Random jitter, if any: about ±2 ms.

**Swing (MPC/Linn scale).** 50 = straight, 66 = perfect triplet swing. Linn: 54 loosens straight 16ths without sounding like swing, and 62 can feel looser than 66 at slow tempos. House rules of thumb: 56–58 reads as loose and natural, 60+ as heavy. Swing feel depends on tempo, so retest after tempo changes.

**Syncopation.** Witek et al. (2014) found an inverted U: pleasure and the urge to move peak at medium syncopation. Later evidence is mixed. A 2023 follow-up only partly supported it, and a 2024 study of idiomatic pop drum patterns found no complexity effect on the urge to move. Use it as a guard-rail against over-syncopating, and trust the genre's idiom first.

**Bass programming grammar.** Note length is half the line.
- **Staccato vs full length:** 0.12–0.2 beat staccato against full-length tied notes, alternated deliberately.
- **Dead notes:** velocity 20–35, length 0.05–0.08, on the pitch of the next real note or an octave below.
- **Slides:** a grace note 1–2 semitones below, 0.06 beat early, about 20 velocity softer.
- **"Chuck":** a muted attack on the 16th before a downbeat.
- **Octaves:** a flourish, not wallpaper.
- **Pushes:** land the next chord's root on the "and-a" of 4 (3.75).

**Call and response in the rhythm section.**
1. Write the chord-rhythm part (guitar, keys, clav) first.
2. Write the bass as an answer in its gaps.
3. Check that together they cover most 16ths, while sharing mostly downbeats.

The same logic applies to percussion layers.

**Patterns worth knowing:**
- Tresillo (3-3-2: 0, 0.75, 1.5).
- Son clave 3-2 (16ths 0, 3, 6, 10, 12).
- Dotted-8th cross-rhythm (every 0.75 beat; realigns every 3 beats).
- Polymeter clips whose lengths don't divide the bar.

## 4. Sound, register and frequency

- **Bands:** sub 30–60 Hz, bass 60–250, mud 250–500, body 500–2k, presence 2–5k, air 8k+. Use them to name problems, not as recipes.
- **Register lanes:** one owner per lane at a time. In Live naming: bass E0–C2, chords C2–C4, lead C3–C5.
- **Kick:** tune it to the key.
- **Bass that translates:** a clean sub plus a saturated mid layer.
- **The crossover region (≈80–120 Hz)**, where club subs and tops hand over, is where kick and bass are won or lost. Check it soloed and in context (a stem render of kick + bass).
- **Every part should stand on its own when soloed.** Kerri Chandler has said he hears music "in pieces", breaking each channel down in his head (DJ Mag). A part that only works buried is filler.
- **Movement:** a static sound is the most common amateur tell. Use filter envelopes and automation, LFOs, sends that open in breakdowns, and velocity mapped to brightness.
- **Layering:** layer by band (transient + body; sub + mid), not by stacking full-range sounds.
- **Presets:** start from one, then change envelope, filter and saturation until it fits its role.

## 5. Arrangement and energy

- **Phrasing:** phrases of 8, 16 or 32 bars. Change something every 8 bars; add or remove a whole element every 16.
- **DJ-functional dance structure:** a 16–32-bar intro and outro that a DJ can mix over (rhythm only, no clashing harmony). Then:
  1. groove A
  2. A′
  3. breakdown
  4. build
  5. main
  6. mid-break
  7. main′
  8. outro

  A demo can run 64–96 bars with the same shape.
- **Energy:** the peak sits about two-thirds of the way through. A drop hits as hard as the breakdown is empty.
- **Subtractive arranging:** build the full loop, then arrange by muting.
- **Transitions:** fills in the last bar or half-bar, crashes, reverse cymbals, filter moves, cutting the kick before a section, delay or reverb throws, silence. Vary the device from section to section.
- **Density:** at most three foreground parts.

## 6. Mixing and loudness

**Starting fader balance** relative to the kick. Instrument output levels vary, so measure and listen.

| Element | Level vs kick |
|---|---|
| Bass | −1 to −3 dB |
| Clap/snare | −3 to −5 |
| Lead | −4 to −8 |
| Chords | −6 to −10 |
| Hats | −8 to −14 |
| Percussion | −10 to −16 |
| Pads/FX | −10 to −18 |

- **EQ:** high-pass what isn't kick or bass; cut mud on chord parts; cut before you boost.
- **Sidechain:** duck bass and pads with the kick. The depth is part of the style.
- **Bus glue:** about 2:1, slow attack, 1–3 dB of gain reduction.
- **Returns:** a short room for drums, a longer space for pads; high-pass them around 200–300 Hz; use pre-delay to keep the source clear.
- **Width:** low end mono, mids moderate, hats, percussion and FX wide. Narrow-to-wide contrast between sections is a tool.
- **Saturation:** helps bass and kick read on small speakers.

**Headroom and masters:**
- Leave the master peaking around −6 to −3 dBFS if a mastering stage follows. That's a handoff convention, not a technical limit.
- Think in two masters:
  - **Streaming:** judged by normalisation to about −14 LUFS integrated (Spotify). Keep true peak ≤ −1 dBTP, or ≤ −2 dBTP if louder than −14.
  - **Club:** louder. Roughly −10 to −6 LUFS integrated, varying by subgenre. Measure the user's references rather than trusting a number.

**Reference workflow:**
1. Pick 2–3 references with the user.
2. Compare the same section type, **loudness-matched** (louder always sounds "better").
3. Change one thing at a time and re-measure.

The numbers point; the ears decide.

## 7. Done checklist

- The rhythm-section loop grooves on its own, the kick–bass relationship is decided, and the kick is tuned.
- Microtiming is systematic per role; velocities have accent maps; no part is flat unless that's the point.
- Voicings respect the low-interval limits against the bass, and the top voice moves like a melody.
- Every sustained sound moves. Each section has a job and a transition, and transition devices vary.
- No more than three foreground parts at once.
- The main section has been rendered and compared to a reference, loudness-matched: no band more than ~3 dB off without a reason, low end mono, true peak within the target.
- There's at least one element someone could hum, recognise or describe afterwards.
- The user has listened and chosen.
