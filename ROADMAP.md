# AbletonMCP Roadmap

Estado actual: **67 herramientas**, conexion async, cache, AI music theory basica.

Cada item tiene un veredicto de viabilidad basado en investigacion de la API de Ableton, complejidad tecnica, y valor para el usuario. Cuando se implemente algo, se tacha de la lista.

---

## v2.0 — IA con contexto (pura computacion, sin cambios en Ableton)

Todas estas mejoras son Python puro — no necesitan nuevos comandos en el Remote Script.

- [ ] **Deteccion de tonalidad (Krumhansl-Schmuckler)** — Analizar notas MIDI y detectar la clave/escala mas probable. Pesar por duracion y posicion metrica. Base para todo lo demas. ~100 lineas.
- [ ] **Templates por genero** — `create_template("trap")` crea toda la estructura de tracks con nombres, volumenes y panning adecuados. Usa comandos existentes (create_track, set_name, set_volume, set_pan). ~200 lineas. Generos: trap, house, lo-fi, rock, ambient, reggaeton, dnb, jazz.
- [ ] **Variaciones de clips (rule-based)** — Dado un clip, generar variaciones: transponer, invertir, retrogradar, desplazar ritmicamente, simplificar, ornamentar. ~150 lineas.
- [ ] **Sugerencias de mezcla** — Clasificar cada track por su rol (kick, bass, pad, vocal...) y sugerir volumen/panning/sends segun el genero. ~250 lineas.
- [ ] **Analisis ritmico** — Detectar grid, swing ratio, densidad, syncopation a partir de notas MIDI. ~200 lineas.
- [ ] **Clasificacion de genero** — Heuristica basada en tempo, nombres de tracks/dispositivos, time signature, numero de tracks. ~150 lineas.
- [ ] **Variaciones con Markov** — Construir cadena de Markov desde notas existentes y generar secuencias similares. ~200 lineas.

---

## v2.1 — Nuevos comandos de Ableton (requieren cambios en Remote Script)

Funcionalidades confirmadas como viables via la API de Ableton.

### Automation (Session clips)

- [ ] **Crear automation envelope** — `create_automation(track, clip, device, param, breakpoints)`. Usa `clip.automation_envelope(param)` + `insert_step()`. Solo funciona en session clips (arrangement devuelve None).
- [ ] **Leer automation** — `get_automation(track, clip, device, param, time)`. Usa `value_at_time()`.
- [ ] **Limpiar automation** — `clear_automation(track, clip, device, param)` y `clear_all_automation(track, clip)`. Usa `clip.clear_envelope()` / `clip.clear_all_envelopes()`.

### Audio clips

- [ ] **Propiedades de audio** — `get_audio_clip_info()` / `set_audio_clip_properties()`: warping on/off, warp mode (beats/tones/texture/re-pitch/complex/complex pro), pitch coarse (-48 a +48 semitonos), pitch fine (-50 a +49 cents), gain.
- [ ] **Warp markers** — `add_warp_marker()`, `move_warp_marker()`, `remove_warp_marker()`, `get_warp_markers()`.

### Arrangement view

- [ ] **Leer clips de arrangement** — `get_arrangement_clips(track)`. Usa `track.arrangement_clips`. Devuelve nombre, start_time, end_time, length.
- [ ] **Crear clips en arrangement** — `create_arrangement_midi_clip(track, position, length)` y `create_arrangement_audio_clip(track, file_path, position)`.
- [ ] **Duplicar clip a arrangement** — `duplicate_clip_to_arrangement(track, clip, destination_time)`.
- [ ] ~~Mover clips en arrangement~~ — **NO VIABLE**: `start_time` es read-only. Workaround: duplicar + borrar (pierde automation).

### Return tracks

- [ ] **Crear return track** — `create_return_track()`. Usa `song.create_return_track()`.
- [ ] **Borrar return track** — `delete_return_track(index)`. Usa `song.delete_return_track()`.
- [ ] **Routing** — `set_track_routing(track, input_type, output_type)`. Usa `track.input_routing_type` / `track.output_routing_type`.

### Groove pool

- [ ] **Leer grooves** — `get_groove_pool()`. Devuelve lista de grooves con sus parametros.
- [ ] **Asignar groove a clip** — `set_clip_groove(track, clip, groove_index)`.
- [ ] **Ajustar groove** — `set_groove_params(groove_index, timing_amount, quantization_amount, velocity_amount, random_amount)`.

### No viable (confirmado)

- ~~Export/render audio~~ — **NO existe en la API**. Solo via GUI.
- ~~Leer MIDI mappings del usuario~~ — **NO expuesto**. Solo mappings del control surface propio.
- ~~Automation en arrangement clips~~ — **API devuelve None** explicitamente.
- ~~Mover clips en arrangement~~ — **start_time es read-only**.

---

## v2.2 — Developer Experience

- [ ] **Structured logging (JSON)** — Reemplazar text logging por JSON formatter. Loggers por modulo (`AbletonMCPServer.tools.session`, etc). Niveles configurables via env vars. ~50 lineas. Esfuerzo: 1 dia.
- [ ] **Protocol framing (length-prefix)** — Prefijo de 4 bytes con longitud del mensaje antes del JSON. Auto-deteccion para backward compatibility (JSON empieza con `{`/`[`, length-prefix no). Mejora robustez, no tanto velocidad. ~100 lineas en cada lado. Esfuerzo: 3 dias.
- [ ] **Plugin system (MCP Server)** — Entry points de setuptools (`ableton_mcp.tools`) para que terceros registren tools sin tocar el core. `importlib.metadata.entry_points()` en el arranque. ~50 lineas. Esfuerzo: 1 dia.
- [ ] ~~Plugin system (Remote Script)~~ — **Dificil**: Ableton carga un solo `__init__.py`. Defer hasta que haya demanda.
- [ ] ~~WebSocket en vez de TCP~~ — **No viable**: Python 2.7 del Remote Script no tiene WebSocket. Alternativa: proxy WebSocket solo en el MCP Server para monitoring UI. Defer.
- [ ] ~~Connection pooling~~ — **No merece la pena**: las llamadas MCP son secuenciales, el overhead del lock es minimo.

---

## v2.3 — Testing

- [ ] **Mock in-process** — `MockAbletonConnection` que simula el estado de Ableton en memoria. Inyectar via `get_connection` (la arquitectura ya lo soporta). ~500-800 lineas para mock stateful. Esfuerzo: 1-2 dias.
- [ ] **Fixtures de pytest** — `conftest.py` con fixtures para sesion vacia, sesion con tracks/clips, estados de error. ~100 lineas.
- [ ] **Tests de tool modules** — Tests para los 8 modulos de herramientas usando el mock. ~400 lineas.
- [ ] **Mock TCP server** — Para testear `AbletonConnection` (reconnect, timeouts, batch). Solo si se necesita testear la capa de conexion. ~300 lineas. Esfuerzo: 1 dia.

---

## Prioridades sugeridas

| Prioridad | Feature | Esfuerzo | Impacto |
|-----------|---------|----------|---------|
| P0 | Deteccion de tonalidad | 1 dia | Base para toda la IA contextual |
| P0 | Templates por genero | 1 dia | Valor inmediato, usa APIs existentes |
| P0 | Variaciones de clips | 1 dia | Workflow de produccion esencial |
| P1 | Sugerencias de mezcla | 1-2 dias | Muy util para principiantes |
| P1 | Automation (session clips) | 2-3 dias | Separa prototipo de produccion real |
| P1 | Mock + tests | 2 dias | Permite iterar rapido |
| P2 | Audio clip properties | 1-2 dias | Expande mas alla de MIDI |
| P2 | Arrangement view | 2 dias | Session + Arrangement = completo |
| P2 | Return tracks + routing | 1 dia | Mezcla profesional |
| P2 | Structured logging | 1 dia | Debugging mas facil |
| P3 | Groove pool | 1 dia | Nicho pero interesante |
| P3 | Protocol framing | 3 dias | Robustez, no velocidad |
| P3 | Plugin system | 1 dia | Ecosistema de terceros |
| P3 | Markov variations | 1-2 dias | "Generar similar" creativo |
