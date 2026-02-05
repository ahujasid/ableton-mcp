ableton-mcp fork of https://github.com/ahujasid/ableton-mcp by https://github.com/ahujasid

While AbletonMCP is powerful, understanding its limitations will help you work more effectively and
avoid frustration. 
These limitations exist because certain Ableton Live features require direct
interaction with the software's user interface or file system.

Limitations

Cannot Load sample and External vst/vst3  Plugins
It still cant load audio samples into drum racks
It cant write automations in arrangment view (but it can in clips)
Third-party VST and AU plugins cannot be loaded by ableton-mcp. Only native Ableton devices can
be created.
It cant read the sample library of the user, not the ableton library, the custom paths off the user

To do:

create new tools for the mcp-server to:

navigate in the browser, ✅
read devices status and parameters, ✅
adjust devices parameters, ✅
access the paths from the audio samples, ✅
load audio sample ❌
create automations, ❌
load vst ❌

Changelogs : 

## IMPLEMENTED FEATURES (v1.1.0)

✅ Read devices status and parameters - get_device_parameters(track_index, device_index)
✅ Adjust devices parameters - set_device_parameter(track_index, device_index, parameter_name, value)
✅ Access user sample library - get_user_library(), get_user_folders()
✅ Load audio samples from browser - load_sample(track_index, sample_uri)
✅ Create clip automations - create_clip_automation(track_index, clip_index, parameter_name, automation_points)
✅ Search browser - search_browser(query, category)


## REMAINING LIMITATIONS

❌ Cannot load VST/AU plugins - Ableton API does not expose third-party plugin loading
   Workaround: Use pre-configured Instrument Racks saved to user library

❌ Cannot change Wavetable oscillator shapes - Internal wavetable selection not exposed via API
   Workaround: Load Wavetable presets with desired wavetables, then adjust other parameters

❌ Cannot load samples from arbitrary filesystem paths - Only browser items can be loaded
   Workaround: Add sample folders to Ableton's browser, then use load_sample with URI

❌ Cannot create arrangement automation - Only clip (Session view) automation is supported

❌ User library returns URIs, not filesystem paths - Browser API limitation


## FUTURE IMPROVEMENTS

- Investigate Max for Live bridge for accessing hidden parameters
- Add support for drum rack pad sample loading
- Explore clip arrangement position control


Update aftre testing:

Sorry, there seems to be a problem loading Serum via the API. Ableton's MCP has some limitations when loading third-party VST plugins programmatically.
What I can suggest is:

Manually load Serum onto the track I just created (track 8 "Serum").
Once loaded, I can create MIDI clips and control the parameters.

