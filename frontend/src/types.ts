/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * llm-profile-schema: a complete named topology — every role this
 * profile defines, mapped to a `ModelEntry`.
 */
export interface LlmProfile {
  models: {
    [k: string]: ModelEntry;
  };
}
/**
 * llm-profile-schema: one role within a profile's `models` map.
 *
 * `endpoint` is the base URL of an OpenAI-compatible (or
 * litellm-supported) HTTP endpoint. `model` is the litellm model
 * string, provider prefix included (`openai/local`,
 * `anthropic/claude-sonnet-4-5`). `api_key_env` names the env var
 * holding the API key for hosted providers; loopback endpoints
 * typically omit it and a stub is sent.
 */
export interface ModelEntry {
  endpoint: string;
  model: string;
  api_key_env?: string | null;
}
/**
 * server-message-accepted: Wire shape returned by
 * `POST /api/campaigns/{cid}/scenes/{scene_id}/messages` on success (201 Created).
 *
 * Carries the composite identity assigned by `Scene.append` so the
 * client can correlate its optimistic local message with the canonical
 * entry in scene history.
 *
 * .implements: rest-api-post-message
 */
export interface MessageAccepted {
  scene_id: string;
  index: number;
}
/**
 * server-message-request: Wire shape of `POST /api/campaigns/{cid}/scenes/{scene_id}/messages`.
 *
 * The minimal payload a client sends to inject a player message into a scene.
 * The server constructs the actual `Message` from this plus the resolved
 * sender Character.
 *
 * .implements: rest-api-post-message
 */
export interface MessageRequest {
  sender_id: string;
  body: string;
}
