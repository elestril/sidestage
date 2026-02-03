import argparse
import os
import sys
import logging
import uvicorn
from pathlib import Path
from sidestage.orchestrator import SidestageOrchestrator

# Global app instance for Uvicorn reload support
def get_app():
    campaign = os.getenv("SIDESTAGE_CAMPAIGN")
    sidestage_dir = os.getenv("SIDESTAGE_DIR")
    if not campaign:
        return None
    
    base_dir = None
    if sidestage_dir:
        base_dir = Path(sidestage_dir)
        
    orchestrator = SidestageOrchestrator(campaign_name=campaign, base_dir=base_dir)
    return orchestrator.fastapi_app

def main():
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
    
    # We don't configure logging here anymore, Orchestrator will do it.
    # However, we can log the startup to stdout at least.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    # Start the AgentOS server using the import string and factory mode to enable reload
    logger.info(f"Starting Sidestage Server on {args.host}:{args.port} with reload enabled...")
    logger.info(f"Campaign data: {os.path.abspath(os.path.join(args.sidestage_dir, args.campaign))}")
    
    uvicorn.run("sidestage.main:get_app", 
                host=args.host, port=args.port, 
                reload=True, reload_dirs=["./src"],
                factory=True)

if __name__ == "__main__":
    main()


