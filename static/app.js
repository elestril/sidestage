document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const messagesContainer = document.getElementById('messages');
    const agentId = 'sidestage-co-author';

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
