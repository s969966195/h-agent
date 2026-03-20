// h_agent/web/static/app.js - Frontend logic

class HAgentUI {
    constructor() {
        this.currentSessionId = null;
        this.sessions = [];
        this.isStreaming = false;
        this.currentAgent = '__default__';
        this.agents = [];
        
        this.messagesEl = document.getElementById('messages');
        this.chatForm = document.getElementById('chatForm');
        this.messageInput = document.getElementById('messageInput');
        this.sessionListEl = document.getElementById('sessionList');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.chatTitle = document.getElementById('chatTitle');
        this.agentSelect = document.getElementById('agentSelect');
        
        this.init();
    }
    
    init() {
        this.chatForm.addEventListener('submit', (e) => this.handleSubmit(e));
        this.newChatBtn.addEventListener('click', () => this.newChat());
        this.clearBtn.addEventListener('click', () => this.clearChat());
        
        // Agent selector change
        this.agentSelect.addEventListener('change', (e) => {
            this.currentAgent = e.target.value;
            const agent = this.agents.find(a => a.id === this.currentAgent);
            if (agent && agent.id !== '__default__') {
                this.chatTitle.textContent = `🤖 ${agent.name}`;
            } else {
                this.chatTitle.textContent = 'New Chat';
            }
        });
        
        // Auto-resize textarea
        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 200) + 'px';
        });
        
        // Enter to send, Shift+Enter for newline
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.chatForm.dispatchEvent(new Event('submit'));
            }
        });
        
        // Load sessions and agents
        this.loadSessions();
        this.loadAgents();
    }
    
    async loadSessions() {
        try {
            const res = await fetch('/api/sessions');
            const data = await res.json();
            if (data.success) {
                this.sessions = data.sessions || [];
                this.renderSessions();
            }
        } catch (e) {
            console.error('Failed to load sessions:', e);
        }
    }
    
    async loadAgents() {
        try {
            const res = await fetch('/api/agents');
            const data = await res.json();
            if (data.success) {
                this.agents = data.agents || [];
                this.renderAgents();
            }
        } catch (e) {
            console.error('Failed to load agents:', e);
        }
    }
    
    renderAgents() {
        // Keep the default option, clear team agents
        this.agentSelect.innerHTML = '';
        
        this.agents.forEach(agent => {
            const opt = document.createElement('option');
            opt.value = agent.id;
            opt.textContent = agent.name + (agent.team ? ` (${agent.role})` : '');
            opt.title = agent.description || agent.role;
            this.agentSelect.appendChild(opt);
        });
        
        // Restore selected agent
        this.agentSelect.value = this.currentAgent;
    }
    
    renderSessions() {
        this.sessionListEl.innerHTML = '';
        
        if (this.sessions.length === 0) {
            this.sessionListEl.innerHTML = '<div style="padding: 12px; color: var(--text-muted); font-size: 12px;">No sessions yet</div>';
            return;
        }
        
        this.sessions.forEach(s => {
            const el = document.createElement('div');
            el.className = 'session-item' + (s.session_id === this.currentSessionId ? ' active' : '');
            el.textContent = s.name || s.session_id;
            el.title = s.name || s.session_id;
            el.addEventListener('click', () => this.selectSession(s.session_id));
            this.sessionListEl.appendChild(el);
        });
    }
    
    async newChat() {
        this.currentSessionId = null;
        this.messagesEl.innerHTML = '';
        this.addWelcomeMessage();
        // Update title based on selected agent
        if (this.currentAgent !== '__default__') {
            const agent = this.agents.find(a => a.id === this.currentAgent);
            if (agent) {
                this.chatTitle.textContent = `🤖 ${agent.name}`;
            }
        } else {
            this.chatTitle.textContent = 'New Chat';
        }
        this.renderSessions();
        this.messageInput.focus();
    }
    
    addWelcomeMessage() {
        const welcome = document.createElement('div');
        welcome.className = 'welcome-message';
        welcome.innerHTML = '<h2>Welcome to h-agent 🌐</h2><p>Your AI coding assistant. Ask me anything!</p>';
        this.messagesEl.appendChild(welcome);
    }
    
    async selectSession(sessionId) {
        this.currentSessionId = sessionId;
        
        // Load history
        try {
            const res = await fetch(`/api/sessions/${sessionId}/history`);
            const data = await res.json();
            
            this.messagesEl.innerHTML = '';
            
            if (data.success && data.history && data.history.length > 0) {
                data.history.forEach(msg => {
                    this.addMessage(msg.role, msg.content);
                });
            } else {
                this.addWelcomeMessage();
            }
            
            // Update title
            const session = this.sessions.find(s => s.session_id === sessionId);
            this.chatTitle.textContent = session?.name || 'Chat';
            
            this.renderSessions();
            this.scrollToBottom();
            
        } catch (e) {
            console.error('Failed to load session history:', e);
        }
    }
    
    clearChat() {
        this.messagesEl.innerHTML = '';
        this.addWelcomeMessage();
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        
        const message = this.messageInput.value.trim();
        if (!message || this.isStreaming) return;
        
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        
        // Add user message
        this.addMessage('user', message);
        
        // Show typing indicator
        const typingEl = this.addTypingIndicator();
        
        this.isStreaming = true;
        
        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    session_id: this.currentSessionId,
                    agent: this.currentAgent,
                })
            });
            
            this.removeTypingIndicator(typingEl);
            
            if (!res.ok) {
                const err = await res.json();
                this.addMessage('assistant', 'Error: ' + (err.error || 'Unknown error'));
                return;
            }
            
            // Track current assistant message
            let assistantEl = this.addMessage('assistant', '');
            
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                
                // Process complete SSE messages
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        const eventType = line.slice(7).trim();
                        continue;
                    }
                    
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6).trim();
                        try {
                            const parsed = JSON.parse(data);
                            this.handleStreamEvent(parsed, assistantEl);
                        } catch (e) {
                            // Ignore parse errors for partial data
                        }
                    }
                }
            }
            
            // Process remaining buffer
            if (buffer.startsWith('data: ')) {
                try {
                    const parsed = JSON.parse(buffer.slice(6));
                    this.handleStreamEvent(parsed, assistantEl);
                } catch (e) {}
            }
            
            // If we created a new session, reload sessions
            if (!this.currentSessionId) {
                await this.loadSessions();
            }
            
        } catch (e) {
            this.removeTypingIndicator(typingEl);
            this.addMessage('assistant', 'Error: ' + e.message);
        } finally {
            this.isStreaming = false;
        }
    }
    
    handleStreamEvent(data, assistantEl) {
        if (data.token) {
            // Append token to assistant message
            const contentEl = assistantEl.querySelector('.message-content');
            contentEl.textContent += data.token;
            this.scrollToBottom();
        }
        
        if (data.content) {
            // Complete content
            const contentEl = assistantEl.querySelector('.message-content');
            contentEl.textContent = data.content;
            this.scrollToBottom();
        }
        
        if (data.error) {
            const contentEl = assistantEl.querySelector('.message-content');
            if (contentEl.textContent) {
                contentEl.textContent += '\n[Error: ' + data.error + ']';
            } else {
                contentEl.textContent = 'Error: ' + data.error;
            }
        }
        
        if (data.done) {
            // Done
        }
    }
    
    addMessage(role, content) {
        const el = document.createElement('div');
        el.className = `message ${role}`;
        
        const avatar = role === 'user' ? '👤' : '🤖';
        
        let formattedContent = content;
        if (typeof content === 'string') {
            // Basic markdown-ish formatting
            formattedContent = this.formatMessage(content);
        }
        
        el.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">${formattedContent}</div>
        `;
        
        this.messagesEl.appendChild(el);
        this.scrollToBottom();
        return el;
    }
    
    formatMessage(text) {
        // Escape HTML first
        text = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        // Code blocks (```...```)
        text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre><code>${code.trim()}</code></pre>`;
        });
        
        // Inline code (`...`)
        text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        // Bold (**...**)
        text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        
        // Italic (*...*)
        text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        
        // Line breaks
        text = text.replace(/\n/g, '<br>');
        
        return text;
    }
    
    addTypingIndicator() {
        const el = document.createElement('div');
        el.className = 'message assistant';
        el.innerHTML = `
            <div class="message-avatar">🤖</div>
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        this.messagesEl.appendChild(el);
        this.scrollToBottom();
        return el;
    }
    
    removeTypingIndicator(el) {
        if (el && el.parentNode) {
            el.parentNode.removeChild(el);
        }
    }
    
    scrollToBottom() {
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.hAgentUI = new HAgentUI();
});
