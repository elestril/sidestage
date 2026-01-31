import os
import subprocess
import sys
from pathlib import Path

def test_logging_to_campaign_server_log(tmp_path):
    # Use a temporary directory for the test to avoid side effects
    os.chdir(tmp_path)
    
    campaign_name = "test_campaign"
    campaign_dir = tmp_path / ".sidestage" / campaign_name
    log_file = campaign_dir / "server.log"
    
    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"
    
    # Create a small script that initializes Orchestrator and logs a message
    script_content = f"""
import logging
import sys
import os
from pathlib import Path
# Ensure src is in path
sys.path.insert(0, "{src_dir}")
from sidestage.orchestrator import SidestageOrchestrator

# Initialize orchestrator with a custom base_dir
orchestrator = SidestageOrchestrator(
    campaign_name="{campaign_name}",
    base_dir=Path("{tmp_path}") / ".sidestage"
)

logger = logging.getLogger("test_logger")
logger.info("Integration test message in campaign dir")
logging.shutdown()
"""
    script_path = tmp_path / "test_log_script.py"
    with open(script_path, "w") as f:
        f.write(script_content)
    
    # Run the script in a subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{src_dir}:{env.get('PYTHONPATH', '')}"
    
    result = subprocess.run([sys.executable, str(script_path)], env=env, capture_output=True, text=True)
    
    assert log_file.exists(), f"server.log should be created in {campaign_dir}. Stdout: {result.stdout}, Stderr: {result.stderr}"
    
    with open(log_file, "r") as f:
        content = f.read()
        assert "Integration test message in campaign dir" in content
