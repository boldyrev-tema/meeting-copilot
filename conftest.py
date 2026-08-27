import sys
from pathlib import Path

# Add the project root to sys.path so tests can `import config`, `import run`, etc.
# directly, matching the flat (non-package) layout used by live_copilot_poc.
sys.path.insert(0, str(Path(__file__).parent))
