# Live API Insights

Key discoveries about Ableton Live's Python API.

## Creating Chains in Racks

Empty racks don't have chains by default. To create chains programmatically:

```python
# Use insert_chain() - NOT chains.append()
rack = track.devices[device_index]
chains_before = len(rack.chains)
rack.insert_chain(chains_before)  # Creates a new chain at the end
new_chain = rack.chains[chains_before]
new_chain.name = "My Chain"
```

> ⚠️ **Important:** `rack.chains.append()` does NOT work - use `rack.insert_chain(index)` instead

## Loading Effects into Rack Chains

`browser.load_item()` always loads to the track, ignoring `rack.view.selected_chain`. 

**Solution:** Load to track, then use `song.move_device()` to move into the chain:

```python
# 1. Load effect to track
browser.load_item(effect_item)

# 2. Get the newly loaded device (last on track)
new_device = track.devices[len(track.devices) - 1]

# 3. Move it into the chain
chain = rack.chains[chain_index]
song.move_device(new_device, chain, len(chain.devices))
```

> ⚠️ **Important:** `browser.load_item()` ignores chain selection - must use `move_device()` approach

## Accessing Devices in Chains

When accessing devices inside rack chains, you need both the rack index AND the device index within the chain:

| Parameter | Description |
|-----------|-------------|
| `track_index` | Track containing the rack |
| `rack_device_index` | Index of the rack device on the track |
| `chain_index` | Which chain in the rack (0, 1, 2, ...) |
| `device_index` | Which device within that chain (0, 1, 2, ...) |

Example: To access the first effect in the second chain of an Audio Effect Rack at device index 1 on track 0:
- `track_index=0`
- `rack_device_index=1`
- `chain_index=1`
- `device_index=0`

## Device Parameters

Device parameters are accessed by name and typically use normalized values (0.0-1.0):

```python
# Get all parameters
for param in device.parameters:
    print(f"{param.name}: {param.value} (min={param.min}, max={param.max})")

# Set a parameter
param = next(p for p in device.parameters if p.name == "Filter Freq")
param.value = 0.5  # Normalized value
```
