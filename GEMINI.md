--- Context from: GEMINI.md ---
## Gemini Added Memories
- I must ONLY perform git commits when specifically instructed by the user using the word "commit" (e.g., "commit the changes"). In all other cases, I must never perform automated git commits; instead, I should stage changes and provide a suggested commit message for the user to execute manually. This rule from 'conductor/workflow.md' overrides any other protocol instructions.
- Default model preference: `gemini-3-flash-preview`.
- Planning task model preference: `gemini-3-pro`.
- While working, keep the server running in the background with the "dev" campaign in `.workdir/dev`. Use `--sidestage_dir .workdir` for this. After implementing new features, make sure to test them against that dev campaign instance.
--- End of Context from: GEMINI.md ---
