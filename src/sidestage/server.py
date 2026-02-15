import atexit
import argparse
import os
import sys
import logging
import uvicorn
from pathlib import Path
from sidestage.orchestrator import SidestageOrchestrator
from sidestage import config
from typing import Optional

_pid_file: Optional[Path] = None

def _remove_pid_file():
  global _pid_file
  if _pid_file is None:
    return
  try:
    path = _pid_file
    _pid_file = None
    if path.exists() and path.read_text().strip() == str(os.getpid()):
      path.unlink()
      logging.info(f"PID file {path} removed")
  except OSError as e:
      logging.error(f"Cannot remove PID file: {e}")
 
def _create_pid_file():
  global _pid_file
  _pid_file = config.SIDESTAGE_DIR / "sidestage.pid"
  if _pid_file.exists():
    raise RuntimeError(f"PID file {_pid_file} already exists.")
  _pid_file.write_text(str(os.getpid()))
  atexit.register(_remove_pid_file)
  logging.info(f"PID {os.getpid()} written to {_pid_file}")

   

# Global app instance for Uvicorn reload support
def get_app():
    """
    Factory function for Uvicorn to create the FastAPI app instance.

    This function relies on environment variables (SIDESTAGE_CAMPAIGN, SIDESTAGE_DIR)
    to configure the Orchestrator, as Uvicorn reload spawns new processes that
    cannot receive direct function arguments.

    Returns:
        FastAPI: The initialized FastAPI application.
    """
    
    sidestage_dir = os.getenv("SIDESTAGE_DIR")
    if not sidestage_dir:
       raise RuntimeError("SIDESTAGE_DIR not set")
    config.SIDESTAGE_DIR = Path(sidestage_dir)

    campaign = os.getenv("SIDESTAGE_CAMPAIGN")
    if not campaign:
        return None

    orchestrator = SidestageOrchestrator(campaign_name=campaign)
    return orchestrator.fastapi_app

def main():
    """
    Main entry point for the Sidestage CLI.
    
    Parses command-line arguments, sets up the environment for the factory pattern,
    and starts the Uvicorn server with hot-reloading enabled.
    """
    parser = argparse.ArgumentParser(
        description="Sidestage: AI Co-Author for Roleplaying Games",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("campaign", help="Name of the campaign to load or create")
    parser.add_argument("--sidestage_dir", default=str(Path.home() / ".sidestage"), help="Directory where campaign data is stored")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind the server to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind the server to")
    args = parser.parse_args()

    # Set environment variable so the reloaded process knows which campaign to use
    os.environ["SIDESTAGE_CAMPAIGN"] = args.campaign
    os.environ["SIDESTAGE_DIR"] = args.sidestage_dir
    config.SIDESTAGE_DIR = Path(args.sidestage_dir)

    config.SIDESTAGE_DIR.mkdir(parents=True, exist_ok=True)
    _create_pid_file()

    # Load config early to initialize logging for the main process
    config.get_config()

    logger = logging.getLogger(__name__)
    # Start the AgentOS server using the import string and factory mode to enable reload
    logger.info(f"Starting Sidestage Server on {args.host}:{args.port} with reload enabled...")
    logger.info(f"Campaign data: {os.path.abspath(os.path.join(args.sidestage_dir, args.campaign))}")
    
    try:
        uvicorn.run("sidestage.server:get_app",
                    host=args.host, port=args.port,
                    reload=True, reload_dirs=[str(Path(__file__).parent)],
                    factory=True,
                    log_config=None)
    finally:
        _remove_pid_file()

if __name__ == "__main__":
    main()
