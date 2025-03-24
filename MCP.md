### Browser Integration

#### search_browser_items(query: string, category_type: string = "all", max_results: int = 50)
Search for browser items matching a query string.

**Parameters:**
- query: Search string to match against item names
- category_type: Type of categories to search ("all", "instruments", "sounds", "drums", "audio_effects", "midi_effects")
- max_results: Maximum number of results to return (default: 50)

**Returns:**
```json
{
    "query": string,
    "category_type": string,
    "total_results": int,
    "results": [
        {
            "name": string,
            "path": string,
            "is_folder": boolean,
            "is_device": boolean,
            "is_loadable": boolean,
            "uri": string
        }
    ]
}
```

// ... existing browser integration documentation ...