# Adding New MCP Tools

When adding new MCP tools (functions with `@mcp.tool()` decorator):

## Steps

1. **Add tool function to `MCP_Server/server.py`**
   
   ```python
   @mcp.tool()
   async def my_new_tool(param1: int, param2: str = "default") -> str:
       """Description of what the tool does.
       
       Parameters:
       - param1: Description of param1
       - param2: Optional description
       """
       command = {"type": "my_new_command", "param1": param1, "param2": param2}
       return await send_command(command)
   ```

2. **Add command type to `is_modifying_command` list** (if it modifies state)
   
   ```python
   is_modifying_command = command_type in [
       "create_midi_track",
       "my_new_command",  # Add here if it changes Ableton state
       # ...
   ]
   ```

3. **Add command handler to Remote Script** (`AbletonMCP_Remote_Script/__init__.py`):
   
   - Add to command type list:
     ```python
     elif command_type in ["my_new_command", ...]:
     ```
   
   - Add handler in `main_thread_task()` function:
     ```python
     elif command_type == "my_new_command":
         result = self._my_new_handler(command)
     ```
   
   - Add implementation method:
     ```python
     def _my_new_handler(self, command):
         param1 = command.get("param1")
         param2 = command.get("param2", "default")
         # Implementation using Live API
         return {"status": "success", "result": ...}
     ```

4. **Deploy changes** - See [Running Local Server](./running-local-server.md)

## Naming Considerations

- GitHub Copilot may block tools with certain names for safety reasons
- Known blocked words: "delete", "master" 
- Use alternative names: "remove" instead of "delete", "main" instead of "master"
- Tools must have `@mcp.tool()` decorator to be discovered
- If a new tool appears disabled or won't enable, try renaming it
