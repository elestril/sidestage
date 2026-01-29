from sidestage.agent import create_agent
from sidestage.config import settings

def main():
    print(f"Initializing Sidestage Agent with provider: {settings.LLM_PROVIDER}")
    agent = create_agent()
    
    print("\nSending test message to agent...\n")
    try:
        agent.print_response("Hello! Please introduce yourself.", stream=True)
    except Exception as e:
        print(f"\nError communicating with agent: {e}")
        print("Ensure the LLM backend is reachable.")

if __name__ == "__main__":
    main()

