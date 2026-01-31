# Specification: Time and Scenes

## Goal
Implement a robust system for managing temporal progression (Gametime) and logical containers for interactions (Scenes).

## Requirements

### 1. Gametime System
- **Distinction**: Clearly distinguish between `gametime` (in-world time) and `walltime` (real-world time).
- **Gametime Class**:
    - Internal storage: Seconds since epoch (integer).
    - Conversion: Convert to/from a user-defined calendar.
    - Initial format: `Day X, HH:MM:SS`.
- **Walltime**: Use standard Python `datetime` for real-world timestamps.

### 2. Scenes as Entities
- `Scene` is a first-class `Entity`.
- **Properties**:
    - `current_gametime`: Optional `Gametime`. If `None`, the scene is "inactive" (e.g., a historical record or memory).
    - `events`: A list of significant occurrences within the scene.
    - `messages`: A dedicated chat log for the scene.
- **Universal Container**: Everything that happens in Sidestage must occur within a Scene.

### 3. Scene Management
- **Multiple Concurrent Scenes**: Different scenes can exist at the same walltime but have different local gametimes.
- **Campaign Planning**: The "main" or default chat is just a special Scene named "Campaign Planning".
- **Co-Author Access**: For now, the Co-Author agent can join any active scene.

### 4. UI Integration
- Users must be able to switch between scenes.
- The chat widget must display messages for the currently active scene.
- Gametime should be visible in the scene view.
