---
name: colour-maqam-fusion
description: Use when adding Arabic, Turkish/Anatolian or wider Middle-Eastern colour to any genre: maqam and jins choices, microtones, usul and iqa' rhythms, ney, saz, oud and darbuka writing, without pastiche.
---

# Colour: maqam fusion

This is a colour layer that sits on top of a genre skill. Maqam is not just "an exotic scale". It is a family of modes built from small cells (*ajnas*) with characteristic notes, directions, ornaments and modulations. Done well, it gives a track a real second identity. Done badly, it's a snake-charmer cliché. This skill aims for the former.

## 1. Ajnas, the building blocks

Tonics are shown on D or C for readability. 𝄳 = half-flat, about a quarter tone low.

| Jins | Notes | Character |
|---|---|---|
| Hijaz | D E♭ F♯ G | Augmented 2nd (E♭–F♯), tense, "classic Middle-Eastern" |
| Kurd | D E♭ F G | Dark, Phrygian-like |
| Nahawand | C D E♭ F G | Minor, close to Western minor |
| Ajam | B♭ C D (E♭) | Major |
| Rast | C D E𝄳 F (G) | Neutral 3rd, the centre of Arabic music |
| Bayati | D E𝄳 F G | Neutral 2nd, soulful and sung |
| Saba | D E𝄳 F G♭ | Lamenting, very characteristic |
| Sikah | E𝄳 F G | Starts on a half-flat |

Ajnas combine into maqamat:
- **Hijaz** = Hijaz on D, plus Nahawand or Rast on G.
- **Bayati** = Bayati on D, plus Nahawand or Rast on G.
- **Hijazkar** ≈ the double harmonic scale (C D♭ E F G A♭ B).

Turkish makam theory uses its own comma-based intervals (Hicaz, Uşşak, Rast, Hüzzam…), so its "half-flats" differ from the Arabic quarter-tone approximation. Pick one tradition per track.

**Equal-tempered Hijaz** (Phrygian dominant: 1 ♭2 3 4 5 ♭6 ♭7) works in 12-TET, and the Hijaz and Kurd ajnas need no microtones. Rast, Bayati, Saba and Sikah do. Tempered Hijaz is usable, but players hear its intervals as slightly off from the real intonation.

## 2. Getting microtones in Live

1. **Half-flat track (safest, 12-TET everywhere else):**
   1. `duplicate_track` the lead.
   2. Set the copy's instrument fine-tune or detune to −50 cents with `set_device_parameters`.
   3. Move only the half-flat degrees (e.g. the E𝄳 in Bayati) onto the copy, written as the natural note.

   Everything else stays in standard tuning.
2. **Audio:** a sampled ney or saz phrase, tuned with `set_clip_properties` `pitch_fine` (−50 = a quarter tone down).
3. **Live 12 Tuning Systems:**
   - Live 12 ships maqam presets by Sami Abu Shumays (with Dennis DeSantis), e.g. "Hijaz 1" and "All Maqamat 24EDO". The user loads them from the browser's Tunings.
   - Tunings work with native instruments except Drum Synths, and with MPE plug-ins set to ±48 semitones of pitch bend. Scala `.scl`/`.ascl` files can be imported.
   - A tuning is stored with the Set, but **every MIDI track has a Bypass Tuning switch** (Drum Rack tracks bypass automatically). So the lead can play the maqam tuning while pads and keys bypass it and stay 12-TET.
   - A tuning with more than 12 notes per octave maps each step to the next key. Read the tuning's note list before writing the lead's MIDI. The half-flat track is easier to drive from tools.

**Rules:**
- Never harmonise a half-flat degree with a 12-TET chord tone a semitone or tone away.
- Keep pads and keys on notes the maqam shares, or on a drone.

## 3. Harmony with Western parts

Maqam music is mostly melodic and heterophonic, so harmony is the fusion problem. Options:
- **Drone or pedal** on the tonic, plus the 5th, under the maqam line.
- **i–♭II movement** (D–E♭) for Hijaz or Kurd sections. Avoid major- or minor-2nd clashes against the ♭2.
- **Switch the section's harmony** when the maqam line enters. A busy I–vi–ii–V under a Hijaz line clashes; move to a pedal or i–♭II, then back for the main groove.
- **Shared-note pivots:** Dorian and Bayati share most notes except the 2nd, so a Dorian groove can host a Bayati phrase if the chords avoid the 2nd.

## 4. Rhythm: iqa'at and usul

D = dum (low, centre), T = tek (rim, high), k = ka (rim, other hand). Positions are 8ths in a 4/4 bar, written in beats.

| Rhythm | Pattern | Beats |
|---|---|---|
| Maqsum (4/4) | D T . T D . T . | D 0, T 0.5, T 1.5, D 2, T 3 |
| Baladi (4/4) | D D . T D . T . | D 0, D 0.5, T 1.5, D 2, T 3 |
| Saidi (4/4) | D T . D D . T . | D 0, T 0.5, D 1.5, D 2, T 3 |
| Malfuf (2/4) | 3+3+2 sixteenths | D 0, T 0.75, T 1.5 (the tresillo; it bridges straight into house) |

Turkish usul in odd metres:
- Aksak 9/8: 2+2+2+3.
- Devr-i Hindi 7/8: 3+2+2.
- Curcuna 10/8: 3+2+2+3.

Over a 4/4 house grid, put an aksak darbuka in a 2.25-beat (9 sixteenths) clip as polymeter. It realigns every 9 bars.

Fill gaps with ka strokes at velocity 40–60, and add rolls and trills on the last 8th before a dum.

## 5. Instruments and idioms (MIDI-level)

**Ney** (end-blown reed flute):
- Breathy attack, long notes, scoops up into notes, slow wide vibrato from the instrument's LFO.
- Phrases tend to descend to rest on the tonic.
- Without samples: a breathy Wavetable, Drift or Operator patch with noise and a slow attack.

**Saz / bağlama** (long-neck lute):
- Fast tremolo picking: repeated 16ths or 32nds on one pitch at velocity 70–95 with an accent map.
- Open-string drones and quick hammer-on ornaments.

**Oud** (fretless lute): warm low plucks, slides into target notes, short ornamental runs.

**Kanun:** rapid scalar runs and arpeggios.

**Riq and frame drum:** jingle 16ths that answer the darbuka.

**Ornaments without pitch bend:**
- Grace notes 0.03–0.06 beat before the target, a scale step above or below.
- Turns (upper, main, lower, main).
- Trills on long notes.
- For slides: a mono patch with glide and overlapping legato notes.

**Taqsim:** an unmetred solo prelude over a drone. In a dance track, 4–8 bars of free-feeling ney over a pad, with no drums, is a strong breakdown.

## 6. Avoiding pastiche

- **No snake-charmer clichés:** no stock "Arabian riff", no gratuitous augmented-2nd runs used as exotic seasoning.
- **Move by ajnas, not scale runs.** Phrases rest on the jins' strong notes (tonic, 4th, 5th) and turn around them.
- **Use the tradition's rhythms or a deliberate fusion** of them (malfuf ↔ tresillo), not a generic "ethnic" loop.
- **Real performances beat programming.** When the colour matters, suggest samples (Splice) or a player for the ney, saz or oud line.
- **References for how fusion is done:**
  - Altın Gün: Anatolian folk-psych.
  - Mercan Dede: ney with electronica.
  - Acid Arab: Arabic and acid house.
  - Omar Souleyman: electronic dabke.
  - Bedouin and organic house generally.
  - Khruangbin: Middle-Eastern-inflected grooves.

## 7. Fusion curveballs

- **Maqam pivot over a pedal:** 8 bars where the lead moves from Dorian to Hijaz on the same tonic (lower the 2nd, raise the 3rd, lower the 6th), back to Dorian at the drop.
- **Microtonal intrusion:** one phrase of Bayati's half-flat 2nd on the half-flat track; everything else stays 12-TET.
- **Aksak polymeter:** a 9-sixteenth darbuka clip over four-on-the-floor.
- **Taqsim breakdown:** drums out, drone in, free ney phrase, then malfuf percussion leads back into the groove.
- **Saz tremolo as the riser** instead of white noise.
