/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * campaign-response: Wire shape for GET /api/campaigns/{cid}.
 *
 * .implements: rest-api-get-campaign
 */
export interface CampaignResponse {
  name: string;
  default_scene_id: string | null;
}
/**
 * character-response: Wire shape for `GET /api/campaigns/{cid}/entities/{id}`
 * when the entity is a Character.
 *
 * Constructed exclusively by `Character.to_response()`. The `type`
 * discriminator distinguishes this variant within `EntityResponse`.
 */
export interface CharacterResponse {
  type?: "character";
  id: string;
  name: string;
  body: string;
  owner: "user" | "stub";
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
/**
 * scene-response: Wire shape for `GET /api/campaigns/{cid}/entities/{id}`
 * when the entity is a Scene, and for `GET /api/campaigns/{cid}/scenes`.
 *
 * Constructed exclusively by `Scene.to_response()`. The `type` discriminator
 * distinguishes this variant within `EntityResponse`.
 */
export interface SceneResponse {
  type?: "scene";
  id: string;
  name: string;
  body: string;
  character_ids: string[];
  player_character_ids: string[];
}
