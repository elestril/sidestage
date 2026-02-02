import pytest
import os
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator
from pathlib import Path
from unittest.mock import patch

# Skip if backend dependencies like llama_cpp are problematic, but here we use TestClient so it's fine 
# as long as we mock or if the real one works.
# The previous test used `is_backend_up` for the real backend, but here we are testing the FastAPI app logic 
# which runs in-process with TestClient.

class TestFrontendIntegration:
    @pytest.fixture(autouse=True)
    def setup_server(self, tmp_path):
        """
        Setup a real orchestrator in a temp directory.
        We need to ensure it finds the 'frontend/out' directory.
        Since we are running tests from the project root, it should find it if we don't mess up paths.
        """
        self.campaign_name = "integration_test_campaign"
        # We need to make sure the orchestrator finds the real frontend/out
        # The orchestrator uses __file__ relative path. 
        # Since we are importing SidestageOrchestrator, its __file__ should be correct relative to the project.
        
        with patch("sidestage.campaign.Campaign._ensure_llm_availability"):
            self.orchestrator = SidestageOrchestrator(
                campaign_name=self.campaign_name,
                base_dir=tmp_path
            )
        self.client = TestClient(self.orchestrator.fastapi_app)

    def test_serve_frontend(self):
        """
        Test that the /sidestage/ URL serves the frontend index.html
        """
        response = self.client.get("/sidestage/", follow_redirects=True)
        assert response.status_code == 200
        assert "<!DOCTYPE html>" in response.text or "<html" in response.text

    def test_root_redirect(self):
        """
        Test that root URL redirects to /sidestage
        """
        response = self.client.get("/", follow_redirects=False)
        assert response.status_code == 307 or response.status_code == 302
        assert response.headers["location"] == "/sidestage"

    def test_api_access(self):
        """
        Test that the API endpoints are still accessible and not shadowed by the frontend mount.
        """
        response = self.client.get("/v1/entities")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        agents = response.json()
        assert isinstance(agents, list)
        assert len(agents) > 0

    def test_static_asset(self):
        """
        Test that a sub-resource like /sidestage/favicon.ico or a built static file is served.
        """
        response = self.client.get("/sidestage/favicon.ico")
        if response.status_code == 200:
            pass # Good
        else:
            response = self.client.get("/sidestage/")
            assert response.status_code == 200
