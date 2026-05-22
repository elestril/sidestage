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
