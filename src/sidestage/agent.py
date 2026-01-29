from agno.agent import Agent
from sidestage.llm_factory import get_llm_model

def create_agent() -> Agent:
    return Agent(
        model=get_llm_model(),
        description="I am the Co-Author agent for Sidestage.",
        instructions=["You are a helpful assistant assisting with world-building."],
        markdown=True,
    )
