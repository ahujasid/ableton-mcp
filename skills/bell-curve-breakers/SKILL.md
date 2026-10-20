---
name: bell-curve-breakers
description: Use when a track or part sounds generic, predictable, cheesy or AI-average, or when the user asks for curveballs: spot the clichés, then pick, place and test concrete unexpected moves.
---

# Breaking the bell curve

Default choices drift to the middle of the distribution, and generated music shows measurable versions of that drift. Audits of text-to-music systems found:
- Google's Lyria 3 narrowed acoustic variety *within* genres;
- Suno blurred the differences *between* genres (Slendebroek & Metaxa, AIES 2026, four genres);
- in some cases, generated regional styles moved toward mainstream ones (Solak et al. 2025).

So treat generated material (Suno, model-written MIDI, including your own first drafts) as raw material, never as the style reference. This skill finds where a track sits on the average and moves it off on purpose, without breaking the genre the user asked for.

Pairs with:
- `music-production-craft`: the theory behind each move;
- `ableton-mcp-studio`: building, rendering and A/B-ing it in Live;
- `genre-*` and `colour-*` skills: what is idiomatic, so you know what bending it means.

## 1. Spot the average

Run `review_clip` on each part and listen through the brief. Flag:

**The generic-prompt test.** Would a one-line prompt for this genre ("disco house with strings") produce exactly this section? If yes, it's a candidate.

**Timing and velocity.**
- Every part shares the same timing and velocity profile: same offsets, same accents.
- Velocity standard deviation under ~6 in any non-pad part.
- Being on the grid is not a problem by itself; uniformity across roles is.

**Harmony.**
- The genre's most common progression, unaltered.
- Root-position triads.
- Every phrase resolving to the tonic on beat 1.
- No borrowed or chromatic chord anywhere.

**Melody.**
- Stepwise inside one octave, starting and ending on the root.
- The same rhythm every bar, no rests.

**Sound.**
- Untouched presets; nothing moving.
- One shared reverb, everything centred.

**Structure.**
- Every section 8 or 16 bars, with every element playing all the time.
- **The same transition device into every section** (one riser is fine; a riser every time is the cliché).

**Mix.** Everything equally loud and equally wide.

## 2. Rules

1. **Anchor, then bend.** Keep most of the genre's anchors (tempo, kick pattern, key centre, core palette) while one thing moves. The stranger the move, the more familiar its surroundings need to be.
2. **One per section.** At most one structural curveball plus one local detail per section.
3. **Say it twice.** A surprise heard once sounds like a mistake; heard again, it sounds intended. Repeat or call back every curveball.
4. **Deny, then pay off.** Huron's ITPRA model (*Sweet Anticipation*) offers an account of why a delayed or denied resolution can be pleasurable: the prediction error is reappraised as safe. The payoff has to arrive eventually.
5. **Don't over-syncopate.** Witek et al. (2014) found pleasure peaks at medium syncopation, though later evidence is mixed. Displace one layer, not all of them.
6. **Every card has three parts:**
   - **where**: bars or section;
   - **how much**: a number;
   - **undo**: a variant slot or a render label.
7. **Offer, don't impose.** Give 2–3 options, each with its effect and its risk. Let the user choose, and remember the verdicts.
8. **Use a different layer from last time.**

## 3. The deck

A minor, 4/4, beats from the start of the bar, Live note names. Cards marked *(stock)* are already common; use them only with a twist.

### Harmony
- **Chromatic mediant shift.**
  - Where: the first bar of a new section.
  - How: move the root a third and keep the quality (Am9 → Cm9 or Fm9; Cmaj7 → E♭maj7 or A♭maj7). It leaves the key and shares one common tone. Return within 8 bars.
- **Planing.** Slide one lush voicing in parallel, including outside the key (an Am11 shape up a minor 3rd and back) for 1–2 bars before a turnaround.
- **Pedal drift.**
  - Where: a breakdown (8–16 bars).
  - How: freeze the bass on the tonic while the chords wander, clashes included. Release the pedal at the drop.
- **Mode pivot over a pedal.** Keep the tonic and move the melody to Phrygian dominant for 8 bars, then back at the drop. From natural minor: lower the 2nd and raise the 3rd. From Dorian, also lower the 6th. Maqam-grade versions are in `colour-maqam-fusion`.
- **Wrong bass note.** Slash chords (F/A, G/A, B♭/C) so the bass moves against the harmony.
- **Deceptive arrival.** Build toward Am, then land the drop on Fmaj7 or B♭maj7. Bring the "right" chord back later (say it twice).
- **Withheld resolution.** Loop on a sus or ♭VII chord, and resolve once, at the end of the last main section.
- **Late key change.** The last main section goes up a whole step (or a tritone for a jolt). Shift bass and chords; leave the drums alone.

### Rhythm
- **Swing contrast, quantified.**
  - Hats at 58 % (d = 0.04).
  - Shaker at 54 % (d = 0.02).
  - Bass straight.

  Do it with `transform_clip_notes`, which gives exact values, or with the nearest library grooves ("Swing 16ths 57" / "54"). The friction between swing levels is the groove.
- **Tempo-relative swing.** In a half-time feel section, raise swing by 2–4 points, then drop back.
- **Polymeter clip.** A percussion or synth clip whose length doesn't divide the bar, placed with `fill_arrangement(step = clip length)`:

  | Clip length | Realigns with the bar every |
  |---|---|
  | 3 beats | 3 bars |
  | 1.25 beats (5 sixteenths) | 5 bars |
  | 2.25 beats (9 sixteenths, an aksak cycle) | 9 bars |
- **Displacement.** Shift one part a 16th or 8th early for one section. Same notes, new feel.
- **Odd bar.** One 6/4 or 2/4 bar before a drop: shift later clips by 2 beats and track the offset.
- **Hard stop.** A beat or a bar of total silence before a section.
- **Dotted-8th motif.** A figure every 0.75 beat (3 against 4).
- *(stock)* **Half-time switch:** clap on 3 only.
- *(stock)* **Kickless peak.**

### Melody
- **Leap language.** Build the hook on 6ths and 7ths.
- **Displaced cell.** A 3-note cell restarting every three 16ths.
- **Tonic avoidance.** Circle the root without landing on it until the very end.
- **Modal argument.** Call and response in different modes.
- **Augmented callback.** The intro motif returns in the outro at double length or inverted.

### Sound
- **Role swap.** A familiar role on an unexpected instrument: a breathy flute patch playing the bassline an octave up, chords on a mallet patch, hats made from filtered noise.
- **Lo-fi intrusion.** One section through Redux, Erosion or Vinyl Distortion, then clean again.
- **Dry/wet flip.** A dry, narrow section against a wide, wet one, in either order.
- **Self-sampling.** The user runs stem separation (Live 12.3+) on *our own* render and resamples the drum stem as a texture. It's on-brief by construction.
- **Found sound.** Build a rhythm part from foley.

### Structure
- **Unusual openings.** Open on the breakdown, or on the hook reharmonised.
- **Asymmetric phrase.** A 12- or 6-bar section between 16s.
- **False ending.**
- **Genre swerve.** 8 bars in a different groove over the same chords.
- **Early drop.** The drop arrives 4 bars before the build says it will.
- **Rhythm-section break.** Everything out except bass and one chord instrument for 4 bars, with the bass carrying the groove.

### Mix
- **One extreme pan.** One element hard left with nothing balancing it.
- **Odd sidechain source.** Duck pads with the hats or the clap instead of the kick.
- **Spotlight mute.** Mute the bass for the first bar of the hook.
- *(stock)* **Reverb throw.**

### Constraint cards (when stuck)
- Remove the element you like most.
- Make the bass the lead for 8 bars.
- Use an "unacceptable" colour.
- Only three sounds for 16 bars.
- Swap the roles of two parts.
- Write the next section without the instrument that's carrying the track.

## 4. Procedure

1. Run the detector (`review_clip` plus the generic-prompt test) and name the two or three most average things in the current section.
2. Pick candidate cards from layers you haven't touched recently. Filter them through the anchor rule and the brief.
3. Offer 2–3 options with a one-line effect and risk each. If the user is away, take the safest and say so.
4. Build the chosen card as a variant: `transform_clip_notes` with `target_clip_index`, or `copy_clip` and edit.
5. Render both versions under different labels with `render_section`.
6. Run `compare_audio` between them to confirm the difference is real and lands where you meant.
7. The user listens and picks.
8. Note the verdict. A rejected card tells you which anchors this user won't bend.
