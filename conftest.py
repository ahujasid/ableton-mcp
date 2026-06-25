# Ensures `import MCP_Server.server` resolves no matter how pytest is invoked.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
