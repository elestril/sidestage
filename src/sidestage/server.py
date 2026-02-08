import argparse
import os
import sys
import logging
import uvicorn
from pathlib import Path
from sidestage.orchestrator import SidestageOrchestrator
from sidestage import config

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
    campaign = os.getenv("SIDESTAGE_CAMPAIGN")
    sidestage_dir = os.getenv("SIDESTAGE_DIR")
    if not campaign:
        return None

    base_dir = Path(sidestage_dir) if sidestage_dir else Path.home() / ".sidestage"

    cfg = config.init(base_dir)
    logging.basicConfig(
        level=getattr(logging, cfg.loglevel.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    orchestrator = SidestageOrchestrator(campaign_name=campaign, base_dir=base_dir)
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

    # Load config early so we can read the log level for the main process
    cfg = config.init(Path(args.sidestage_dir))
    logging.basicConfig(
        level=getattr(logging, cfg.loglevel.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Start the AgentOS server using the import string and factory mode to enable reload
    logger.info(f"Starting Sidestage Server on {args.host}:{args.port} with reload enabled...")
    logger.info(f"Campaign data: {os.path.abspath(os.path.join(args.sidestage_dir, args.campaign))}")
    
    uvicorn.run("sidestage.server:get_app",
                host=args.host, port=args.port, 
                reload=True, reload_dirs=[str(Path(__file__).parent)],
                factory=True)

if __name__ == "__main__":
    main()
