from dataclasses import dataclass


@dataclass(frozen=True)
class CampaignId:
    value: str


@dataclass(frozen=True)
class SceneId:
    value: str


@dataclass(frozen=True)
class CharacterId:
    value: str


@dataclass(frozen=True)
class MessageId:
    value: str
