diff --git a/frontend/tsconfig.app.json b/frontend/tsconfig.app.json
index a9b5a59..a822344 100644
--- a/frontend/tsconfig.app.json
+++ b/frontend/tsconfig.app.json
@@ -24,5 +24,6 @@
     "noFallthroughCasesInSwitch": true,
     "noUncheckedSideEffectImports": true
   },
-  "include": ["src"]
+  "include": ["src"],
+  "exclude": ["src/**/*.test.ts", "src/**/*.test.tsx", "src/test-setup.ts", "src/test-helpers.tsx"]
 }
diff --git a/frontend/vite.config.ts b/frontend/vite.config.ts
index af15e4f..a1b1712 100644
--- a/frontend/vite.config.ts
+++ b/frontend/vite.config.ts
@@ -1,3 +1,4 @@
+/// <reference types="vitest/config" />
 import { defineConfig } from 'vite'
 import react from '@vitejs/plugin-react'
 import tailwindcss from '@tailwindcss/vite'
diff --git a/pyproject.toml b/pyproject.toml
index 5632090..c5c164b 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -47,6 +47,7 @@ dev = [
     "pytest-anyio (>=0.0.0)",
     "uv (>=0.10.0,<0.11.0)",
     "pdoc (>=15.0.0,<16.0.0)",
+    "pytest-playwright",
 ]
 
 [tool.pytest.ini_options]
@@ -54,4 +55,5 @@ pythonpath = "src"
 testpaths = ["tests"]
 markers = [
     "llm: tests requiring a live LLM instance at localhost:8080",
+    "e2e: end-to-end browser tests requiring Playwright",
 ]
diff --git a/tests/e2e/__init__.py b/tests/e2e/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/tests/e2e/conftest.py b/tests/e2e/conftest.py
new file mode 100644
index 0000000..bbf10ea
--- /dev/null
+++ b/tests/e2e/conftest.py
@@ -0,0 +1,302 @@
+"""Fixtures for end-to-end Playwright tests.
+
+Session-scoped fixtures build the frontend, start a Sidestage server on port 8001,
+and provide an httpx client. Class-scoped fixtures reset campaign state.
+"""
+
+from __future__ import annotations
+
+import importlib.util
+import os
+import shutil
+import signal
+import socket
+import subprocess
+import sys
+import time
+from collections.abc import Generator
+from pathlib import Path
+from typing import Any
+
+import httpx
+import pytest
+
+# ---------------------------------------------------------------------------
+# Import helpers from devserver (LogObserver, server_is_running)
+# ---------------------------------------------------------------------------
+
+_helpers_path = Path(__file__).resolve().parent.parent / "devserver" / "helpers.py"
+_spec = importlib.util.spec_from_file_location("tests.devserver.helpers", _helpers_path)
+assert _spec and _spec.loader
+_helpers = importlib.util.module_from_spec(_spec)
+sys.modules.setdefault(_spec.name, _helpers)
+_spec.loader.exec_module(_helpers)
+
+LogObserver = _helpers.LogObserver
+server_is_running = _helpers.server_is_running
+
+# ---------------------------------------------------------------------------
+# Paths
+# ---------------------------------------------------------------------------
+
+REPO_ROOT = Path(__file__).resolve().parent.parent.parent
+DEVSERVER_DIR = REPO_ROOT / "sidestage.dev"
+FRONTEND_DIR = REPO_ROOT / "frontend"
+CAMPAIGN_NAME = "dev"
+
+DEV_CAMPAIGN_SOURCE = REPO_ROOT / "data" / "dev_campaign"
+CAMPAIGN_MARKDOWN_DIR = DEVSERVER_DIR / CAMPAIGN_NAME / "markdown"
+
+DEFAULT_E2E_PORT = 8001
+
+
+def _find_available_port(start: int = DEFAULT_E2E_PORT, max_attempts: int = 10) -> int:
+    """Find an available TCP port starting from *start*."""
+    for port in range(start, start + max_attempts):
+        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
+            try:
+                s.bind(("localhost", port))
+                return port
+            except OSError:
+                continue
+    raise RuntimeError(
+        f"No available port found in range {start}-{start + max_attempts - 1}"
+    )
+
+
+def _log_files(base_dir: Path, campaign: str = CAMPAIGN_NAME) -> dict[str, Path]:
+    """Return the standard log file paths for a given base directory."""
+    return {
+        "server": base_dir / "server.log",
+        "request": base_dir / "request.log",
+        "campaign": base_dir / campaign / "campaign.log",
+        "chat": base_dir / campaign / "chat.log",
+    }
+
+
+def _rotate_logs(log_files: dict[str, Path]) -> None:
+    """Rotate log files by truncating them (preserves the file for tailing)."""
+    for path in log_files.values():
+        if path.exists():
+            path.write_text("")
+
+
+def _restore_campaign_markdown() -> None:
+    """Copy source markdown from data/dev_campaign/ into the working dir."""
+    src = DEV_CAMPAIGN_SOURCE / "markdown"
+    if not src.exists():
+        return
+    if CAMPAIGN_MARKDOWN_DIR.exists():
+        shutil.rmtree(CAMPAIGN_MARKDOWN_DIR)
+    shutil.copytree(src, CAMPAIGN_MARKDOWN_DIR)
+
+
+# ---------------------------------------------------------------------------
+# Session-scoped: Frontend build
+# ---------------------------------------------------------------------------
+
+
+@pytest.fixture(scope="session")
+def frontend_dist() -> Path:
+    """Ensure frontend/dist/ exists and is up-to-date.
+
+    1. Check for node_modules/, run npm install if missing
+    2. Check for dist/index.html
+    3. If missing or stale (src newer than dist), run npm build
+    4. Return the dist path
+    """
+    node_modules = FRONTEND_DIR / "node_modules"
+    dist_dir = FRONTEND_DIR / "dist"
+    dist_index = dist_dir / "index.html"
+    src_dir = FRONTEND_DIR / "src"
+
+    # Verify npm is available
+    npm_path = shutil.which("npm")
+    if npm_path is None:
+        pytest.fail(
+            "npm is not installed or not on PATH. "
+            "Install Node.js to run E2E tests."
+        )
+
+    # Step 1: npm install if needed
+    if not node_modules.exists():
+        result = subprocess.run(
+            ["npm", "install"],
+            cwd=str(FRONTEND_DIR),
+            capture_output=True,
+            text=True,
+            timeout=120,
+        )
+        if result.returncode != 0:
+            pytest.fail(
+                f"npm install failed:\n{result.stdout}\n{result.stderr}"
+            )
+
+    # Step 2-3: Check dist freshness
+    needs_build = False
+    if not dist_index.exists():
+        needs_build = True
+    else:
+        # Compare newest src file mtime against dist mtime
+        dist_mtime = dist_dir.stat().st_mtime
+        for src_file in src_dir.rglob("*"):
+            if src_file.is_file() and src_file.stat().st_mtime > dist_mtime:
+                needs_build = True
+                break
+
+    if needs_build:
+        result = subprocess.run(
+            ["npm", "run", "build"],
+            cwd=str(FRONTEND_DIR),
+            capture_output=True,
+            text=True,
+            timeout=120,
+        )
+        if result.returncode != 0:
+            pytest.fail(
+                f"Frontend build failed:\n{result.stdout}\n{result.stderr}"
+            )
+
+    return dist_dir
+
+
+# ---------------------------------------------------------------------------
+# Session-scoped: E2E server
+# ---------------------------------------------------------------------------
+
+
+@pytest.fixture(scope="session")
+def e2e_server(frontend_dist: Path) -> Generator[str, None, None]:
+    """Start a Sidestage server on port 8001 for E2E tests.
+
+    - Always starts fresh (never reuses running instance)
+    - Restores campaign markdown before start
+    - Rotates log files
+    - Passes SIDESTAGE_MOCK_AGENT=1
+    - Waits for readiness via health check polling
+    - Tears down with SIGTERM on session end
+    """
+    port = _find_available_port(DEFAULT_E2E_PORT)
+    base_url = f"http://localhost:{port}"
+
+    # Restore campaign state and rotate logs
+    _restore_campaign_markdown()
+    logs = _log_files(DEVSERVER_DIR)
+    _rotate_logs(logs)
+
+    # Ensure the working directory exists
+    DEVSERVER_DIR.mkdir(parents=True, exist_ok=True)
+    campaign_dir = DEVSERVER_DIR / CAMPAIGN_NAME
+    if not campaign_dir.exists():
+        shutil.copytree(DEV_CAMPAIGN_SOURCE, campaign_dir)
+
+    # Remove stale PID file if present
+    pid_file = DEVSERVER_DIR / "sidestage.pid"
+    if pid_file.exists():
+        pid_file.unlink()
+
+    # Start the server directly (not via run-dev.sh, to control port)
+    env = {
+        **os.environ,
+        "SIDESTAGE_MOCK_AGENT": "1",
+        "SIDESTAGE_PORT": str(port),
+    }
+
+    process = subprocess.Popen(
+        [
+            sys.executable, "-m", "sidestage.server",
+            "--sidestage_dir", str(DEVSERVER_DIR),
+            "--port", str(port),
+            CAMPAIGN_NAME,
+        ],
+        cwd=str(REPO_ROOT),
+        env=env,
+        stdout=subprocess.PIPE,
+        stderr=subprocess.PIPE,
+    )
+
+    # Wait for readiness
+    deadline = time.time() + 30
+    while time.time() < deadline:
+        if server_is_running(base_url):
+            break
+        # Check if process died
+        if process.poll() is not None:
+            stdout, stderr = process.communicate(timeout=5)
+            pytest.fail(
+                f"E2E server exited unexpectedly (code {process.returncode}).\n"
+                f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
+            )
+        time.sleep(1.0)
+    else:
+        process.kill()
+        stdout, stderr = process.communicate(timeout=5)
+        pytest.fail(
+            f"E2E server failed to start within 30s on port {port}.\n"
+            f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
+        )
+
+    yield base_url
+
+    # Teardown: graceful shutdown
+    process.send_signal(signal.SIGTERM)
+    try:
+        process.wait(timeout=10)
+    except subprocess.TimeoutExpired:
+        process.kill()
+        process.wait(timeout=5)
+
+
+# ---------------------------------------------------------------------------
+# Session-scoped: HTTP client
+# ---------------------------------------------------------------------------
+
+
+@pytest.fixture(scope="session")
+def e2e_client(e2e_server: str) -> Generator[httpx.Client, None, None]:
+    """Session-scoped httpx client pointed at the E2E server."""
+    with httpx.Client(base_url=e2e_server, timeout=30.0) as client:
+        yield client
+
+
+# ---------------------------------------------------------------------------
+# Class-scoped: Campaign reset
+# ---------------------------------------------------------------------------
+
+
+@pytest.fixture(scope="class")
+def fresh_e2e_campaign(e2e_client: httpx.Client) -> None:
+    """Restore campaign state: re-import markdown and reload defaults.
+
+    Class-scoped so it runs once per test class.
+    """
+    _restore_campaign_markdown()
+
+    resp = e2e_client.post(
+        "/v1/campaign/import",
+        json={"action": "execute", "force": True},
+    )
+    assert resp.status_code == 200, f"Campaign re-import failed: {resp.text}"
+    data = resp.json()
+    result = data.get("result", {})
+    errors = result.get("errors", [])
+    assert result.get("phase") == "complete", (
+        f"Campaign import phase={result.get('phase')!r}, errors={errors}"
+    )
+
+    resp = e2e_client.post("/v1/campaign/reload-defaults")
+    assert resp.status_code == 200, f"reload-defaults failed: {resp.text}"
+
+
+# ---------------------------------------------------------------------------
+# Per-test: Log observer
+# ---------------------------------------------------------------------------
+
+
+@pytest.fixture()
+def log_observer() -> Any:
+    """Per-test log observer for asserting on backend log output."""
+    logs = _log_files(DEVSERVER_DIR)
+    observer = LogObserver(logs)
+    observer.mark()
+    return observer
diff --git a/tests/e2e/test_canary.py b/tests/e2e/test_canary.py
new file mode 100644
index 0000000..5f7507a
--- /dev/null
+++ b/tests/e2e/test_canary.py
@@ -0,0 +1,27 @@
+"""Canary test to verify E2E infrastructure works end-to-end."""
+
+import pytest
+
+
+@pytest.mark.e2e
+class TestCanary:
+    """Minimal test that verifies the E2E server starts and Playwright can connect."""
+
+    def test_server_is_reachable(self, e2e_client):
+        """The e2e_client fixture provides an httpx.Client on port 8001."""
+        resp = e2e_client.get("/v1/entities")
+        assert resp.status_code == 200
+
+    def test_frontend_loads(self, page, e2e_server):
+        """Playwright can navigate to the SPA and the page loads."""
+        page.goto(f"{e2e_server}/sidestage/")
+        # The app should render something -- wait for any content
+        page.wait_for_selector("body", timeout=10000)
+        assert "sidestage" in page.url.lower() or page.title() != ""
+
+    def test_frontend_has_content(self, page, e2e_server):
+        """The SPA renders actual application content (not a blank page)."""
+        page.goto(f"{e2e_server}/sidestage/")
+        # Wait for the React app to hydrate -- look for the entity list
+        # or any substantive DOM element
+        page.wait_for_selector("[data-testid], main, .app, #root *", timeout=15000)
diff --git a/uv.lock b/uv.lock
index abc8fa7..ec5d47d 100644
--- a/uv.lock
+++ b/uv.lock
@@ -717,6 +717,7 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/f9/c8/9d76a66421d1ae24340dfae7e79c313957f6e3195c144d2c73333b5bfe34/greenlet-3.3.1-cp312-cp312-macosx_11_0_universal2.whl", hash = "sha256:7e806ca53acf6d15a888405880766ec84721aa4181261cd11a457dfe9a7a4975", size = 276443, upload-time = "2026-01-23T15:30:10.066Z" },
     { url = "https://files.pythonhosted.org/packages/81/99/401ff34bb3c032d1f10477d199724f5e5f6fbfb59816ad1455c79c1eb8e7/greenlet-3.3.1-cp312-cp312-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:d842c94b9155f1c9b3058036c24ffb8ff78b428414a19792b2380be9cecf4f36", size = 597359, upload-time = "2026-01-23T16:00:57.394Z" },
     { url = "https://files.pythonhosted.org/packages/2b/bc/4dcc0871ed557792d304f50be0f7487a14e017952ec689effe2180a6ff35/greenlet-3.3.1-cp312-cp312-manylinux_2_24_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:20fedaadd422fa02695f82093f9a98bad3dab5fcda793c658b945fcde2ab27ba", size = 607805, upload-time = "2026-01-23T16:05:28.068Z" },
+    { url = "https://files.pythonhosted.org/packages/3b/cd/7a7ca57588dac3389e97f7c9521cb6641fd8b6602faf1eaa4188384757df/greenlet-3.3.1-cp312-cp312-manylinux_2_24_s390x.manylinux_2_28_s390x.whl", hash = "sha256:c620051669fd04ac6b60ebc70478210119c56e2d5d5df848baec4312e260e4ca", size = 622363, upload-time = "2026-01-23T16:15:54.754Z" },
     { url = "https://files.pythonhosted.org/packages/cf/05/821587cf19e2ce1f2b24945d890b164401e5085f9d09cbd969b0c193cd20/greenlet-3.3.1-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:14194f5f4305800ff329cbf02c5fcc88f01886cadd29941b807668a45f0d2336", size = 609947, upload-time = "2026-01-23T15:32:51.004Z" },
     { url = "https://files.pythonhosted.org/packages/a4/52/ee8c46ed9f8babaa93a19e577f26e3d28a519feac6350ed6f25f1afee7e9/greenlet-3.3.1-cp312-cp312-musllinux_1_2_aarch64.whl", hash = "sha256:7b2fe4150a0cf59f847a67db8c155ac36aed89080a6a639e9f16df5d6c6096f1", size = 1567487, upload-time = "2026-01-23T16:04:22.125Z" },
     { url = "https://files.pythonhosted.org/packages/8f/7c/456a74f07029597626f3a6db71b273a3632aecb9afafeeca452cfa633197/greenlet-3.3.1-cp312-cp312-musllinux_1_2_x86_64.whl", hash = "sha256:49f4ad195d45f4a66a0eb9c1ba4832bb380570d361912fa3554746830d332149", size = 1636087, upload-time = "2026-01-23T15:33:47.486Z" },
@@ -725,6 +726,7 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/ec/ab/d26750f2b7242c2b90ea2ad71de70cfcd73a948a49513188a0fc0d6fc15a/greenlet-3.3.1-cp313-cp313-macosx_11_0_universal2.whl", hash = "sha256:7ab327905cabb0622adca5971e488064e35115430cec2c35a50fd36e72a315b3", size = 275205, upload-time = "2026-01-23T15:30:24.556Z" },
     { url = "https://files.pythonhosted.org/packages/10/d3/be7d19e8fad7c5a78eeefb2d896a08cd4643e1e90c605c4be3b46264998f/greenlet-3.3.1-cp313-cp313-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:65be2f026ca6a176f88fb935ee23c18333ccea97048076aef4db1ef5bc0713ac", size = 599284, upload-time = "2026-01-23T16:00:58.584Z" },
     { url = "https://files.pythonhosted.org/packages/ae/21/fe703aaa056fdb0f17e5afd4b5c80195bbdab701208918938bd15b00d39b/greenlet-3.3.1-cp313-cp313-manylinux_2_24_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:7a3ae05b3d225b4155bda56b072ceb09d05e974bc74be6c3fc15463cf69f33fd", size = 610274, upload-time = "2026-01-23T16:05:29.312Z" },
+    { url = "https://files.pythonhosted.org/packages/06/00/95df0b6a935103c0452dad2203f5be8377e551b8466a29650c4c5a5af6cc/greenlet-3.3.1-cp313-cp313-manylinux_2_24_s390x.manylinux_2_28_s390x.whl", hash = "sha256:12184c61e5d64268a160226fb4818af4df02cfead8379d7f8b99a56c3a54ff3e", size = 624375, upload-time = "2026-01-23T16:15:55.915Z" },
     { url = "https://files.pythonhosted.org/packages/cb/86/5c6ab23bb3c28c21ed6bebad006515cfe08b04613eb105ca0041fecca852/greenlet-3.3.1-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:6423481193bbbe871313de5fd06a082f2649e7ce6e08015d2a76c1e9186ca5b3", size = 612904, upload-time = "2026-01-23T15:32:52.317Z" },
     { url = "https://files.pythonhosted.org/packages/c2/f3/7949994264e22639e40718c2daf6f6df5169bf48fb038c008a489ec53a50/greenlet-3.3.1-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:33a956fe78bbbda82bfc95e128d61129b32d66bcf0a20a1f0c08aa4839ffa951", size = 1567316, upload-time = "2026-01-23T16:04:23.316Z" },
     { url = "https://files.pythonhosted.org/packages/8d/6e/d73c94d13b6465e9f7cd6231c68abde838bb22408596c05d9059830b7872/greenlet-3.3.1-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:4b065d3284be43728dd280f6f9a13990b56470b81be20375a207cdc814a983f2", size = 1636549, upload-time = "2026-01-23T15:33:48.643Z" },
@@ -733,6 +735,7 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/ae/fb/011c7c717213182caf78084a9bea51c8590b0afda98001f69d9f853a495b/greenlet-3.3.1-cp314-cp314-macosx_11_0_universal2.whl", hash = "sha256:bd59acd8529b372775cd0fcbc5f420ae20681c5b045ce25bd453ed8455ab99b5", size = 275737, upload-time = "2026-01-23T15:32:16.889Z" },
     { url = "https://files.pythonhosted.org/packages/41/2e/a3a417d620363fdbb08a48b1dd582956a46a61bf8fd27ee8164f9dfe87c2/greenlet-3.3.1-cp314-cp314-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:b31c05dd84ef6871dd47120386aed35323c944d86c3d91a17c4b8d23df62f15b", size = 646422, upload-time = "2026-01-23T16:01:00.354Z" },
     { url = "https://files.pythonhosted.org/packages/b4/09/c6c4a0db47defafd2d6bab8ddfe47ad19963b4e30f5bed84d75328059f8c/greenlet-3.3.1-cp314-cp314-manylinux_2_24_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:02925a0bfffc41e542c70aa14c7eda3593e4d7e274bfcccca1827e6c0875902e", size = 658219, upload-time = "2026-01-23T16:05:30.956Z" },
+    { url = "https://files.pythonhosted.org/packages/e2/89/b95f2ddcc5f3c2bc09c8ee8d77be312df7f9e7175703ab780f2014a0e781/greenlet-3.3.1-cp314-cp314-manylinux_2_24_s390x.manylinux_2_28_s390x.whl", hash = "sha256:3e0f3878ca3a3ff63ab4ea478585942b53df66ddde327b59ecb191b19dbbd62d", size = 671455, upload-time = "2026-01-23T16:15:57.232Z" },
     { url = "https://files.pythonhosted.org/packages/80/38/9d42d60dffb04b45f03dbab9430898352dba277758640751dc5cc316c521/greenlet-3.3.1-cp314-cp314-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:34a729e2e4e4ffe9ae2408d5ecaf12f944853f40ad724929b7585bca808a9d6f", size = 660237, upload-time = "2026-01-23T15:32:53.967Z" },
     { url = "https://files.pythonhosted.org/packages/96/61/373c30b7197f9e756e4c81ae90a8d55dc3598c17673f91f4d31c3c689c3f/greenlet-3.3.1-cp314-cp314-musllinux_1_2_aarch64.whl", hash = "sha256:aec9ab04e82918e623415947921dea15851b152b822661cce3f8e4393c3df683", size = 1615261, upload-time = "2026-01-23T16:04:25.066Z" },
     { url = "https://files.pythonhosted.org/packages/fd/d3/ca534310343f5945316f9451e953dcd89b36fe7a19de652a1dc5a0eeef3f/greenlet-3.3.1-cp314-cp314-musllinux_1_2_x86_64.whl", hash = "sha256:71c767cf281a80d02b6c1bdc41c9468e1f5a494fb11bc8688c360524e273d7b1", size = 1683719, upload-time = "2026-01-23T15:33:50.61Z" },
@@ -741,6 +744,7 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/28/24/cbbec49bacdcc9ec652a81d3efef7b59f326697e7edf6ed775a5e08e54c2/greenlet-3.3.1-cp314-cp314t-macosx_11_0_universal2.whl", hash = "sha256:3e63252943c921b90abb035ebe9de832c436401d9c45f262d80e2d06cc659242", size = 282706, upload-time = "2026-01-23T15:33:05.525Z" },
     { url = "https://files.pythonhosted.org/packages/86/2e/4f2b9323c144c4fe8842a4e0d92121465485c3c2c5b9e9b30a52e80f523f/greenlet-3.3.1-cp314-cp314t-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:76e39058e68eb125de10c92524573924e827927df5d3891fbc97bd55764a8774", size = 651209, upload-time = "2026-01-23T16:01:01.517Z" },
     { url = "https://files.pythonhosted.org/packages/d9/87/50ca60e515f5bb55a2fbc5f0c9b5b156de7d2fc51a0a69abc9d23914a237/greenlet-3.3.1-cp314-cp314t-manylinux_2_24_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:c9f9d5e7a9310b7a2f416dd13d2e3fd8b42d803968ea580b7c0f322ccb389b97", size = 654300, upload-time = "2026-01-23T16:05:32.199Z" },
+    { url = "https://files.pythonhosted.org/packages/7c/25/c51a63f3f463171e09cb586eb64db0861eb06667ab01a7968371a24c4f3b/greenlet-3.3.1-cp314-cp314t-manylinux_2_24_s390x.manylinux_2_28_s390x.whl", hash = "sha256:4b9721549a95db96689458a1e0ae32412ca18776ed004463df3a9299c1b257ab", size = 662574, upload-time = "2026-01-23T16:15:58.364Z" },
     { url = "https://files.pythonhosted.org/packages/1d/94/74310866dfa2b73dd08659a3d18762f83985ad3281901ba0ee9a815194fb/greenlet-3.3.1-cp314-cp314t-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:92497c78adf3ac703b57f1e3813c2d874f27f71a178f9ea5887855da413cd6d2", size = 653842, upload-time = "2026-01-23T15:32:55.671Z" },
     { url = "https://files.pythonhosted.org/packages/97/43/8bf0ffa3d498eeee4c58c212a3905dd6146c01c8dc0b0a046481ca29b18c/greenlet-3.3.1-cp314-cp314t-musllinux_1_2_aarch64.whl", hash = "sha256:ed6b402bc74d6557a705e197d47f9063733091ed6357b3de33619d8a8d93ac53", size = 1614917, upload-time = "2026-01-23T16:04:26.276Z" },
     { url = "https://files.pythonhosted.org/packages/89/90/a3be7a5f378fc6e84abe4dcfb2ba32b07786861172e502388b4c90000d1b/greenlet-3.3.1-cp314-cp314t-musllinux_1_2_x86_64.whl", hash = "sha256:59913f1e5ada20fde795ba906916aea25d442abcc0593fba7e26c92b7ad76249", size = 1676092, upload-time = "2026-01-23T15:33:52.176Z" },
@@ -1467,6 +1471,25 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/fd/2c/87250ac73ca8730b2c4e0185b573585f0b42e09562132e6c29d00b3a9bb9/pdoc-15.0.4-py3-none-any.whl", hash = "sha256:f9028e85e7bb8475b054e69bde1f6d26fc4693d25d9fa1b1ce9009bec7f7a5c4", size = 145978, upload-time = "2025-06-04T17:05:48.473Z" },
 ]
 
+[[package]]
+name = "playwright"
+version = "1.58.0"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "greenlet" },
+    { name = "pyee" },
+]
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/f8/c9/9c6061d5703267f1baae6a4647bfd1862e386fbfdb97d889f6f6ae9e3f64/playwright-1.58.0-py3-none-macosx_10_13_x86_64.whl", hash = "sha256:96e3204aac292ee639edbfdef6298b4be2ea0a55a16b7068df91adac077cc606", size = 42251098, upload-time = "2026-01-30T15:09:24.028Z" },
+    { url = "https://files.pythonhosted.org/packages/e0/40/59d34a756e02f8c670f0fee987d46f7ee53d05447d43cd114ca015cb168c/playwright-1.58.0-py3-none-macosx_11_0_arm64.whl", hash = "sha256:70c763694739d28df71ed578b9c8202bb83e8fe8fb9268c04dd13afe36301f71", size = 41039625, upload-time = "2026-01-30T15:09:27.558Z" },
+    { url = "https://files.pythonhosted.org/packages/e1/ee/3ce6209c9c74a650aac9028c621f357a34ea5cd4d950700f8e2c4b7fe2c4/playwright-1.58.0-py3-none-macosx_11_0_universal2.whl", hash = "sha256:185e0132578733d02802dfddfbbc35f42be23a45ff49ccae5081f25952238117", size = 42251098, upload-time = "2026-01-30T15:09:30.461Z" },
+    { url = "https://files.pythonhosted.org/packages/f1/af/009958cbf23fac551a940d34e3206e6c7eed2b8c940d0c3afd1feb0b0589/playwright-1.58.0-py3-none-manylinux1_x86_64.whl", hash = "sha256:c95568ba1eda83812598c1dc9be60b4406dffd60b149bc1536180ad108723d6b", size = 46235268, upload-time = "2026-01-30T15:09:33.787Z" },
+    { url = "https://files.pythonhosted.org/packages/d9/a6/0e66ad04b6d3440dae73efb39540c5685c5fc95b17c8b29340b62abbd952/playwright-1.58.0-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:8f9999948f1ab541d98812de25e3a8c410776aa516d948807140aff797b4bffa", size = 45964214, upload-time = "2026-01-30T15:09:36.751Z" },
+    { url = "https://files.pythonhosted.org/packages/0e/4b/236e60ab9f6d62ed0fd32150d61f1f494cefbf02304c0061e78ed80c1c32/playwright-1.58.0-py3-none-win32.whl", hash = "sha256:1e03be090e75a0fabbdaeab65ce17c308c425d879fa48bb1d7986f96bfad0b99", size = 36815998, upload-time = "2026-01-30T15:09:39.627Z" },
+    { url = "https://files.pythonhosted.org/packages/41/f8/5ec599c5e59d2f2f336a05b4f318e733077cd5044f24adb6f86900c3e6a7/playwright-1.58.0-py3-none-win_amd64.whl", hash = "sha256:a2bf639d0ce33b3ba38de777e08697b0d8f3dc07ab6802e4ac53fb65e3907af8", size = 36816005, upload-time = "2026-01-30T15:09:42.449Z" },
+    { url = "https://files.pythonhosted.org/packages/c8/c4/cc0229fea55c87d6c9c67fe44a21e2cd28d1d558a5478ed4d617e9fb0c93/playwright-1.58.0-py3-none-win_arm64.whl", hash = "sha256:32ffe5c303901a13a0ecab91d1c3f74baf73b84f4bedbb6b935f5bc11cc98e1b", size = 33085919, upload-time = "2026-01-30T15:09:45.71Z" },
+]
+
 [[package]]
 name = "pluggy"
 version = "1.6.0"
@@ -1716,6 +1739,18 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/c1/60/5d4751ba3f4a40a6891f24eec885f51afd78d208498268c734e256fb13c4/pydantic_settings-2.12.0-py3-none-any.whl", hash = "sha256:fddb9fd99a5b18da837b29710391e945b1e30c135477f484084ee513adb93809", size = 51880, upload-time = "2025-11-10T14:25:45.546Z" },
 ]
 
+[[package]]
+name = "pyee"
+version = "13.0.1"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "typing-extensions" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/8b/04/e7c1fe4dc78a6fdbfd6c337b1c3732ff543b8a397683ab38378447baa331/pyee-13.0.1.tar.gz", hash = "sha256:0b931f7c14535667ed4c7e0d531716368715e860b988770fc7eb8578d1f67fc8", size = 31655, upload-time = "2026-02-14T21:12:28.044Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/a0/c4/b4d4827c93ef43c01f599ef31453ccc1c132b353284fc6c87d535c233129/pyee-13.0.1-py3-none-any.whl", hash = "sha256:af2f8fede4171ef667dfded53f96e2ed0d6e6bd7ee3bb46437f77e3b57689228", size = 15659, upload-time = "2026-02-14T21:12:26.263Z" },
+]
+
 [[package]]
 name = "pygments"
 version = "2.19.2"
@@ -1790,6 +1825,34 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/c6/25/bd6493ae85d0a281b6a0f248d0fdb1d9aa2b31f18bcd4a8800cf397d8209/pytest_anyio-0.0.0-py2.py3-none-any.whl", hash = "sha256:dc8b5c4741cb16ff90be37fddd585ca943ed12bbeb563de7ace6cd94441d8746", size = 1999, upload-time = "2021-06-29T22:57:29.158Z" },
 ]
 
+[[package]]
+name = "pytest-base-url"
+version = "2.1.0"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "pytest" },
+    { name = "requests" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/ae/1a/b64ac368de6b993135cb70ca4e5d958a5c268094a3a2a4cac6f0021b6c4f/pytest_base_url-2.1.0.tar.gz", hash = "sha256:02748589a54f9e63fcbe62301d6b0496da0d10231b753e950c63e03aee745d45", size = 6702, upload-time = "2024-01-31T22:43:00.81Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/98/1c/b00940ab9eb8ede7897443b771987f2f4a76f06be02f1b3f01eb7567e24a/pytest_base_url-2.1.0-py3-none-any.whl", hash = "sha256:3ad15611778764d451927b2a53240c1a7a591b521ea44cebfe45849d2d2812e6", size = 5302, upload-time = "2024-01-31T22:42:58.897Z" },
+]
+
+[[package]]
+name = "pytest-playwright"
+version = "0.7.2"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "playwright" },
+    { name = "pytest" },
+    { name = "pytest-base-url" },
+    { name = "python-slugify" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/e8/6b/913e36aa421b35689ec95ed953ff7e8df3f2ee1c7b8ab2a3f1fd39d95faf/pytest_playwright-0.7.2.tar.gz", hash = "sha256:247b61123b28c7e8febb993a187a07e54f14a9aa04edc166f7a976d88f04c770", size = 16928, upload-time = "2025-11-24T03:43:22.53Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/76/61/4d333d8354ea2bea2c2f01bad0a4aa3c1262de20e1241f78e73360e9b620/pytest_playwright-0.7.2-py3-none-any.whl", hash = "sha256:8084e015b2b3ecff483c2160f1c8219b38b66c0d4578b23c0f700d1b0240ea38", size = 16881, upload-time = "2025-11-24T03:43:24.423Z" },
+]
+
 [[package]]
 name = "pytest-timeout"
 version = "2.4.0"
@@ -1832,6 +1895,18 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/1b/d0/397f9626e711ff749a95d96b7af99b9c566a9bb5129b8e4c10fc4d100304/python_multipart-0.0.22-py3-none-any.whl", hash = "sha256:2b2cd894c83d21bf49d702499531c7bafd057d730c201782048f7945d82de155", size = 24579, upload-time = "2026-01-25T10:15:54.811Z" },
 ]
 
+[[package]]
+name = "python-slugify"
+version = "8.0.4"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "text-unidecode" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/87/c7/5e1547c44e31da50a460df93af11a535ace568ef89d7a811069ead340c4a/python-slugify-8.0.4.tar.gz", hash = "sha256:59202371d1d05b54a9e7720c5e038f928f45daaffe41dd10822f3907b937c856", size = 10921, upload-time = "2024-02-08T18:32:45.488Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/a4/62/02da182e544a51a5c3ccf4b03ab79df279f9c60c5e82d5e8bec7ca26ac11/python_slugify-8.0.4-py2.py3-none-any.whl", hash = "sha256:276540b79961052b66b7d116620b36518847f52d5fd9e3a70164fc8c50faa6b8", size = 10051, upload-time = "2024-02-08T18:32:43.911Z" },
+]
+
 [[package]]
 name = "pywin32"
 version = "311"
@@ -2167,6 +2242,7 @@ dev = [
     { name = "pyright" },
     { name = "pytest" },
     { name = "pytest-anyio" },
+    { name = "pytest-playwright" },
     { name = "pytest-timeout" },
     { name = "types-pyyaml" },
     { name = "uv" },
@@ -2201,6 +2277,7 @@ dev = [
     { name = "pyright", specifier = ">=1.1.408,<2.0.0" },
     { name = "pytest", specifier = ">=9.0.2,<10.0.0" },
     { name = "pytest-anyio", specifier = ">=0.0.0" },
+    { name = "pytest-playwright" },
     { name = "pytest-timeout", specifier = ">=2.4.0,<3.0.0" },
     { name = "types-pyyaml", specifier = ">=6.0.12.20250915,<7.0.0.0" },
     { name = "uv", specifier = ">=0.10.0,<0.11.0" },
@@ -2310,6 +2387,15 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/81/0d/13d1d239a25cbfb19e740db83143e95c772a1fe10202dda4b76792b114dd/starlette-0.52.1-py3-none-any.whl", hash = "sha256:0029d43eb3d273bc4f83a08720b4912ea4b071087a3b48db01b7c839f7954d74", size = 74272, upload-time = "2026-01-18T13:34:09.188Z" },
 ]
 
+[[package]]
+name = "text-unidecode"
+version = "1.3"
+source = { registry = "https://pypi.org/simple" }
+sdist = { url = "https://files.pythonhosted.org/packages/ab/e2/e9a00f0ccb71718418230718b3d900e71a5d16e701a3dae079a21e9cd8f8/text-unidecode-1.3.tar.gz", hash = "sha256:bad6603bb14d279193107714b288be206cac565dfa49aa5b105294dd5c4aab93", size = 76885, upload-time = "2019-08-30T21:36:45.405Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/a6/a5/c0b6468d3824fe3fde30dbb5e1f687b291608f9473681bbf7dabbf5a87d7/text_unidecode-1.3-py2.py3-none-any.whl", hash = "sha256:1311f10e8b895935241623731c2ba64f4c455287888b18189350b67134a822e8", size = 78154, upload-time = "2019-08-30T21:37:03.543Z" },
+]
+
 [[package]]
 name = "tiktoken"
 version = "0.12.0"
