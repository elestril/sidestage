# Product Guidelines

## 1. Brand & Personality
- **Voice of the Agent:** The initial "Co-Author" agent should be functional, precise, and objective. It acts as a reliable repository of world knowledge, prioritizing accuracy over narrative flair.
- **Future-Proofing:** The system must support diverse agent personalities later, but the core utility remains high-quality factual retrieval and updates.

## 2. Visual Identity & UX
- **Theme:** High-contrast aesthetic (inspired by the user's `swaync` style). This ensures legibility in both brightly lit preparation environments and darker "DM screen" scenarios.
- **Interface Modes:**
    - **CLI:** Monospace-heavy, prioritizing clear data structures and rapid input.
    - **Web UI:** Modern, functional layout utilizing the high-contrast palette for maximum clarity.

## 3. Interaction Design
- **Human-in-the-Loop:** To maintain the integrity of the campaign world, the DM is the ultimate authority. Every proposed change to the world state or campaign facts must be explicitly confirmed (Veto Power).
- **Transparency:** The interface must provide immediate access to the "why" behind an agent's response (e.g., source links to campaign documents or previous session logs).

## 4. Development Priorities
- **Experimentation Over Rigor:** At this stage, prioritizing flexible experimentation, simple prompts, and proof-of-concept workflows is paramount.
- **Fail-Fast Prototyping:** "Factual Integrity" and other advanced features are secondary to establishing a working, modifiable multi-agent framework.
- **Observability:** Focus on exposing the inner workings (prompts, context) rather than perfecting the final output.
