import pytest
import logging
from sidestage.config import SidestageConfig
from sidestage.logging import LogConfig, _parse_log_level, _serialize_log_level

def test_log_level_serialization():
    config = LogConfig(level=logging.INFO)
    assert config.level == logging.INFO
    
    # Serialize
    data = config.model_dump()
    assert data["level"] == "INFO"

def test_log_level_deserialization():
    config = LogConfig(level="ERROR")  # type: ignore[arg-type]
    assert config.level == logging.ERROR
    
    config = LogConfig(level=logging.WARNING)
    assert config.level == logging.WARNING

def test_log_level_invalid():
    # Invalid level names raise a validation error
    with pytest.raises(Exception):
        LogConfig(level="INVALID_LEVEL")  # type: ignore[arg-type]

def test_sidestage_config_logging():
    config = SidestageConfig(logging={"level": "DEBUG"})  # type: ignore[arg-type]
    assert config.logging.level == logging.DEBUG
    
    dump = config.model_dump()
    assert dump["logging"]["level"] == "DEBUG"
