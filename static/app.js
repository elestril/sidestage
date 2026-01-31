document.addEventListener('DOMContentLoaded', () => {
    const agentId = 'sidestage-co-author';

    // Navigation
    const navChat = document.getElementById('nav-chat');
    const navEntities = document.getElementById('nav-entities');
    const chatContainer = document.getElementById('chat-container');
    const entitiesContainer = document.getElementById('entities-container');
    const entityList = document.getElementById('entity-list');

    // Scenes
    const sceneList = document.getElementById('scene-list');
    const createSceneBtn = document.getElementById('create-scene-btn');
    let currentSceneId = 'campaign_planning';
    let scenes = [];

    // WebSocket Sync
    let socket;
    let currentEntityId = null;

    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

        socket.onopen = () => {
            console.log('WebSocket connection established');
        };

        socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'entities_updated') {
                console.log('Entities updated via sync');
                loadEntities(document.querySelector('.filter-btn.active').dataset.filter);
                // Refresh modal if open
                if (currentEntityId && modal.style.display === 'flex') {
                    refreshEntityDetails();
                }
            } else if (data.type === 'chat_message') {
                console.log('Chat message received via sync:', data);
                if (data.scene_id === currentSceneId) {
                    addMessageToAll(data.text, data.sender, data.widget);
                }
            } else if (data.type === 'scene_updated') {
                loadScenes();
            }
        };

        socket.onclose = () => {
            console.log('WebSocket disconnected. Retrying in 2s...');
            setTimeout(connectWebSocket, 2000);
        };
    }

    connectWebSocket();

    // Scene Logic
    async function loadScenes() {
        try {
            const response = await fetch('/scenes');
            scenes = await response.json();
            renderSceneList();
            updateSceneUI();
        } catch (error) {
            console.error('Failed to load scenes:', error);
        }
    }

    function renderSceneList() {
        sceneList.innerHTML = '';
        scenes.forEach(scene => {
            const item = document.createElement('div');
            item.className = `scene-item ${scene.id === currentSceneId ? 'active' : ''}`;
            item.textContent = scene.name;
            item.onclick = () => switchScene(scene.id);
            sceneList.appendChild(item);
        });
    }

    async function switchScene(sceneId) {
        if (sceneId === currentSceneId) return;
        currentSceneId = sceneId;
        renderSceneList();
        updateSceneUI();
        await loadChatHistory();
    }

    function formatGametime(totalSeconds) {
        if (totalSeconds === null) return '';
        const days = Math.floor(totalSeconds / (24 * 3600));
        const remainder = totalSeconds % (24 * 3600);
        const h = Math.floor(remainder / 3600);
        const m = Math.floor((remainder % 3600) / 60);
        const s = remainder % 60;
        
        const pad = (n) => n.toString().padStart(2, '0');
        return `Day ${days}, ${pad(h)}:${pad(m)}:${pad(s)}`;
    }

    function updateSceneUI() {
        const activeScene = scenes.find(s => s.id === currentSceneId);
        if (!activeScene) return;

        document.querySelectorAll('.scene-name').forEach(el => {
            el.textContent = activeScene.name;
        });

        document.querySelectorAll('.scene-gametime').forEach(el => {
            if (activeScene.current_gametime !== null) {
                el.textContent = formatGametime(activeScene.current_gametime);
            } else {
                el.textContent = '';
            }
        });
    }

    async function loadChatHistory() {
        document.querySelectorAll('.messages-display').forEach(el => el.innerHTML = '');
        try {
            // Agno AgentOS history endpoint
            const response = await fetch(`/sessions/${currentSceneId}/runs`);
            if (!response.ok) return;
            const runs = await response.json();
            
            // Runs are newest first usually, or sorted by timestamp
            // Agno returns a list of Run objects.
            runs.reverse().forEach(run => {
                // User message
                if (run.message && run.message.content) {
                    addMessageToAll(run.message.content, 'user');
                }
                // Agent response
                if (run.response && run.response.content) {
                    addMessageToAll(run.response.content, 'agent');
                }
            });
        } catch (error) {
            console.error('Failed to load chat history:', error);
        }
    }

    // Initialize scenes
    loadScenes().then(() => loadChatHistory());

    createSceneBtn.addEventListener('click', async () => {
        const name = prompt('Enter scene name:');
        if (!name) return;
        
        try {
            const response = await fetch('/scenes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });
            if (response.ok) {
                const scene = await response.json();
                loadScenes();
                switchScene(scene.id);
            }
        } catch (error) {
            console.error('Failed to create scene:', error);
        }
    });

    // Markdown Parser (Discord-style)
    function parseMarkdown(text) {
        if (!text) return '';
        let html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/__(.*?)__/g, '<u>$1</u>')
            .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/^> (.*$)/gm, '<blockquote>$1</blockquote>')
            .replace(/\n/g, '<br>');
        return html;
    }

    // Splitter Logic
    const splitter = document.getElementById('splitter');
    const browser = document.getElementById('entities-browser');
    const miniChat = document.getElementById('entities-chat');
    let isResizing = false;

    if (splitter) {
        splitter.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'ns-resize';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const containerRect = entitiesContainer.getBoundingClientRect();
            const offset = e.clientY - containerRect.top;
            const browserHeight = (offset / containerRect.height) * 100;
            const chatHeight = 100 - browserHeight - 2; // -2 for splitter
            
            if (browserHeight > 10 && chatHeight > 10) {
                browser.style.flex = browserHeight;
                miniChat.style.flex = chatHeight;
            }
        });

        document.addEventListener('mouseup', () => {
            isResizing = false;
            document.body.style.cursor = 'default';
        });
    }

    function showSection(section) {
        if (section === 'chat') {
            chatContainer.style.display = 'flex';
            entitiesContainer.style.display = 'none';
            navChat.classList.add('active');
            navEntities.classList.remove('active');
        } else if (section === 'entities') {
            chatContainer.style.display = 'none';
            entitiesContainer.style.display = 'flex';
            navChat.classList.remove('active');
            navEntities.classList.add('active');
            loadEntities();
        }
    }

    navChat.addEventListener('click', (e) => {
        e.preventDefault();
        showSection('chat');
    });

    navEntities.addEventListener('click', (e) => {
        e.preventDefault();
        showSection('entities');
    });

    // Import/Export
    const importBtn = document.getElementById('import-btn');
    const exportBtn = document.getElementById('export-btn');

    if (importBtn) {
        importBtn.addEventListener('click', async () => {
            console.log('Import button clicked');
            importBtn.disabled = true;
            try {
                const response = await fetch('/entities/import', { method: 'POST' });
                console.log('Import response status:', response.status);
                const data = await response.json();
                console.log('Import response data:', data);
                loadEntities();
            } catch (error) {
                console.error('Import failed:', error);
            } finally {
                importBtn.disabled = false;
            }
        });
    }

    if (exportBtn) {
        exportBtn.addEventListener('click', async () => {
            console.log('Export button clicked');
            exportBtn.disabled = true;
            try {
                const response = await fetch('/entities/export', { method: 'POST' });
                console.log('Export response status:', response.status);
                const data = await response.json();
                console.log('Export response data:', data);
            } catch (error) {
                console.error('Export failed:', error);
            } finally {
                exportBtn.disabled = false;
            }
        });
    }

    // Filters
    const filterBtns = document.querySelectorAll('.filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadEntities(btn.dataset.filter);
        });
    });

    // Modal
    const modal = document.getElementById('entity-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalType = document.getElementById('modal-type');
    const modalMarkdown = document.getElementById('modal-markdown');
    const closeBtn = document.querySelector('.close-btn');

    closeBtn.onclick = () => {
        modal.style.display = 'none';
        currentEntityId = null;
    };
    window.onclick = (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
            currentEntityId = null;
        }
    };

    async function showEntityDetails(entity) {
        currentEntityId = entity.id;
        modalTitle.textContent = entity.name;
        modalType.textContent = entity.type || entity.entity_type;
        modalMarkdown.textContent = 'Loading markdown...';
        modal.style.display = 'flex';
        await refreshEntityDetails();
    }

    async function refreshEntityDetails() {
        if (!currentEntityId) return;
        try {
            const response = await fetch(`/entities/${currentEntityId}/markdown`);
            if (!response.ok) throw new Error('Failed to fetch markdown');
            const data = await response.json();
            modalMarkdown.textContent = data.markdown;
        } catch (error) {
            modalMarkdown.textContent = 'Error loading markdown: ' + error.message;
        }
    }

    async function loadEntities(filter = 'all') {
        entityList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem;">Loading entities...</div>';
        
        try {
            const response = await fetch('/entities');
            if (!response.ok) throw new Error('Failed to fetch entities');
            const allEntities = await response.json();

            entityList.innerHTML = '';
            const filtered = filter === 'all' ? allEntities : allEntities.filter(e => e.type === filter);
            
            if (filtered.length === 0) {
                entityList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem;">No entities found.</div>';
                return;
            }

            filtered.forEach(entity => {
                const card = document.createElement('div');
                card.className = 'entity-card';
                card.innerHTML = `
                    <div class="type">${entity.type}</div>
                    <div class="name">${entity.name}</div>
                    <div class="description">${entity.description}</div>
                `;
                card.addEventListener('click', () => showEntityDetails(entity));
                entityList.appendChild(card);
            });
        } catch (error) {
            console.error('Error:', error);
            entityList.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #ff5555;">Error: ${error.message}</div>`;
        }
    }

    function addMessageToAll(text, sender, widget = null) {
        const containers = document.querySelectorAll('.messages-display');

        containers.forEach(container => {
            if (!container) return;
            const msgDiv = document.createElement('div');
            msgDiv.className = `message ${sender}`;
            
            if (widget) {
                msgDiv.appendChild(renderWidget(widget));
            } else {
                msgDiv.innerHTML = parseMarkdown(text);
            }
            
            container.appendChild(msgDiv);
            container.scrollTop = container.scrollHeight;
        });
    }

    function renderWidget(widget) {
        const div = document.createElement('div');
        div.className = 'widget entity-widget';
        if (widget.type === 'entity') {
            div.innerHTML = `
                <div class="widget-header">${widget.entity_type}: ${widget.name}</div>
                <div class="widget-body">${widget.description}</div>
            `;
            div.addEventListener('click', () => showEntityDetails(widget));
        }
        return div;
    }

    async function handleChatSubmit(e) {
        e.preventDefault();
        const form = e.target;
        const input = form.querySelector('input');
        const text = input.value.trim();
        if (!text) return;

        input.value = '';
        input.disabled = true;

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    message: text,
                    scene_id: currentSceneId
                })
            });

            if (!response.ok) throw new Error('Failed to send message');
        } catch (error) {
            console.error('Error:', error);
            addMessageToAll('Error: ' + error.message, 'agent');
        } finally {
            input.disabled = false;
            input.focus();
        }
    }

    document.querySelectorAll('.chat-form').forEach(form => {
        form.addEventListener('submit', handleChatSubmit);
    });

    // Initial state
    showSection('chat');
});
