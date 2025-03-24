# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install build dependencies
python -m pip install --upgrade pip
pip install build

# Build the package
python -m build

# Install the package in development mode
pip install -e .

Write-Host "Package built and installed successfully!"
Write-Host "The path to the executable is: $((Get-Command ableton-mcp).Source)" 