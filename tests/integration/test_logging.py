import logging
from pathlib import Path

from sidestage.logging import LogConfig, initLogging, initCampaignLogging


def test_init_logging_creates_server_and_request_logs(tmp_path: Path):
    """initLogging creates server.log and request.log in sidestage_dir."""
    initLogging(tmp_path, LogConfig())

    assert (tmp_path / "server.log").exists()
    assert (tmp_path / "request.log").exists()


def test_root_logger_writes_to_server_log(tmp_path: Path):
    """Messages from the root logger land in server.log."""
    initLogging(tmp_path, LogConfig())

    test_logger = logging.getLogger("test_root_logger_writes")
    test_logger.info("hello from test")
    for handler in logging.root.handlers + logging.getLogger().handlers:
        handler.flush()

    content = (tmp_path / "server.log").read_text()
    assert "hello from test" in content


def test_root_logger_does_not_write_to_request_log(tmp_path: Path):
    """Non-access messages should not appear in request.log."""
    initLogging(tmp_path, LogConfig())

    test_logger = logging.getLogger("test_root_not_in_request")
    test_logger.info("should not appear in request log")
    for handler in logging.root.handlers + logging.getLogger().handlers:
        handler.flush()

    content = (tmp_path / "request.log").read_text()
    assert "should not appear" not in content


def test_campaign_logging_creates_log_files(tmp_path: Path):
    """initCampaignLogging creates campaign.log and chat.log."""
    initLogging(tmp_path, LogConfig())

    campaign_dir = tmp_path / "test_campaign"
    campaign_dir.mkdir()

    campaign_log, chat_log = initCampaignLogging("test", campaign_dir)

    campaign_log.info("campaign message")
    chat_log.debug("chat debug message")
    for h in campaign_log.handlers + chat_log.handlers:
        h.flush()

    assert (campaign_dir / "campaign.log").exists()
    assert (campaign_dir / "chat.log").exists()

    campaign_content = (campaign_dir / "campaign.log").read_text()
    assert "campaign message" in campaign_content

    chat_content = (campaign_dir / "chat.log").read_text()
    assert "chat debug message" in chat_content


def test_campaign_log_does_not_propagate_to_server(tmp_path: Path):
    """Campaign logger messages stay out of server.log."""
    initLogging(tmp_path, LogConfig())

    campaign_dir = tmp_path / "test_campaign"
    campaign_dir.mkdir()

    campaign_log, _ = initCampaignLogging("test_no_prop", campaign_dir)
    campaign_log.info("campaign only message")
    for h in campaign_log.handlers:
        h.flush()
    for h in logging.root.handlers:
        h.flush()

    server_content = (tmp_path / "server.log").read_text()
    assert "campaign only message" not in server_content
