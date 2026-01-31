document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const messagesContainer = document.getElementById('messages');
    const agentId = 'sidestage-co-author';

    // Navigation
    const navChat = document.getElementById('nav-chat');
    const navEntities = document.getElementById('nav-entities');
    const chatContainer = document.getElementById('chat-container');
    const entitiesContainer = document.getElementById('entities-container');
    const entityList = document.getElementById('entity-list');

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

    // Initial state
    showSection('chat');

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

    closeBtn.onclick = () => modal.style.display = 'none';
    window.onclick = (e) => {
        if (e.target === modal) modal.style.display = 'none';
    };

    async function showEntityDetails(entity) {
        modalTitle.textContent = entity.name;
        modalType.textContent = entity.type;
        modalMarkdown.textContent = 'Loading markdown...';
        modal.style.display = 'flex';

        try {
            const response = await fetch(`/entities/${entity.id}/markdown`);
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

    function addMessage(text, sender) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender}`;
        msgDiv.textContent = text;
        messagesContainer.appendChild(msgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = userInput.value.trim();
        if (!text) return;

        addMessage(text, 'user');
        userInput.value = '';
        userInput.disabled = true;

        try {
            const formData = new FormData();
            formData.append('message', text);
            formData.append('stream', 'false');

            const response = await fetch(`/agents/${agentId}/runs`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Failed to get response from agent');
            }

            const data = await response.json();
            console.log('Agent response:', data);
            
            let reply = "I'm sorry, I couldn't process that.";
            if (data && data.content) {
                reply = data.content;
            }

            addMessage(reply, 'agent');
        } catch (error) {
            console.error('Error:', error);
            addMessage('Error: ' + error.message, 'agent');
        } finally {
            userInput.disabled = false;
            userInput.focus();
        }
    });
});
