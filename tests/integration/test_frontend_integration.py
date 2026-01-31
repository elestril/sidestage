import pytest
import os
from fastapi.testclient import TestClient
from sidestage.orchestrator import SidestageOrchestrator
from pathlib import Path

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
        
        self.orchestrator = SidestageOrchestrator(
            campaign_name=self.campaign_name,
            base_dir=tmp_path
        )
        self.client = TestClient(self.orchestrator.fastapi_app)

    def test_serve_frontend(self):
        """
        Test that the root URL serves the frontend index.html
        """
        response = self.client.get("/")
        assert response.status_code == 200
        # Check for some content we expect in the built index.html
        # Since it's a minified React app, we might just look for <html or <div or "Sidestage"
        # The title or some text from page.tsx should be there.
        assert "<!DOCTYPE html>" in response.text or "<html" in response.text
        # We can also check for a specific JS file reference or "Greeting, Archivist" if it's rendered (it's client side so maybe not in static HTML)
        # But Next.js static export usually pre-renders initial state.
        # "Greeting, Archivist" is in the initial state of useState, so it might be in the HTML if Next.js pre-rendered it.
        # But "use client" component might not be fully pre-rendered if it depends on browser APIs.
        # However, we definitely expect HTML.

    def test_api_access(self):
        """
        Test that the API endpoints are still accessible and not shadowed by the frontend mount.
        """
        response = self.client.get("/agents")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        agents = response.json()
        assert isinstance(agents, list)
        assert len(agents) > 0

    def test_static_asset(self):
        """
        Test that a sub-resource like /favicon.ico or a known static file is served.
        """
        # We don't know the exact hash of next files, but /favicon.ico is standard
        response = self.client.get("/favicon.ico")
        # Next.js usually puts favicon in the root of out/
        if response.status_code == 200:
            pass # Good
        else:
            # Maybe it's not there, check for something else known?
            # style.css is in the static directory
            response = self.client.get("/style.css")
            assert response.status_code == 200
