import argparse
import os
import sys
import uvicorn
from sidestage.orchestrator import SidestageOrchestrator

# Global app instance for Uvicorn reload support
def get_app():
    campaign = os.getenv("SIDESTAGE_CAMPAIGN")
    if not campaign:
        return None
    orchestrator = SidestageOrchestrator(campaign_name=campaign)
    return orchestrator.app.get_app()

def main():
    parser = argparse.ArgumentParser(description="Sidestage: AI Co-Author for Roleplaying Games")
    parser.add_argument("campaign", help="Name of the campaign to load or create")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind the server to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind the server to")
    args = parser.parse_args()

    # Set environment variable so the reloaded process knows which campaign to use
    os.environ["SIDESTAGE_CAMPAIGN"] = args.campaign
    
    # Start the AgentOS server using the import string and factory mode to enable reload
    print(f"Starting Sidestage Server on {args.host}:{args.port} with reload enabled...")
    print(f"Observability: Built-in tracing enabled. View traces at http://{args.host}:{args.port}/traces")
    print(f"Campaign data: {os.path.abspath(os.path.join(os.path.expanduser('~'), '.sidestage', args.campaign))}")
    
    uvicorn.run("sidestage.main:get_app", 
                host=args.host, port=args.port, 
                reload=True, reload_dirs=["./src"],
                factory=True)

if __name__ == "__main__":
    main()


