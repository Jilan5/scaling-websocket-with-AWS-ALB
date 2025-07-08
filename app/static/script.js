// Client state
let socket = null;
let clientId = null;
let instanceId = null;
let isConnected = false;
let messagesSent = 0;
let messagesReceived = 0;
let tasksCreated = 0;
let tasksCompleted = 0;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

// DOM elements
const statusIconElement = document.getElementById('status');
const statusTextElement = document.querySelector('.status-text');
const instanceIdElement = document.getElementById('instance-id');
const connectionCountElement = document.getElementById('connection-count');
const chatMessagesElement = document.getElementById('chat-messages');
const messageInputElement = document.getElementById('message-input');
const sendButtonElement = document.getElementById('send-button');
const loadHistoryButtonElement = document.getElementById('load-history-button');
const connectButtonElement = document.getElementById('connect-button');
const disconnectButtonElement = document.getElementById('disconnect-button');
const startTaskButtonElement = document.getElementById('start-task-button');
const tasksElement = document.getElementById('tasks');
const instanceDetailsElement = document.getElementById('instance-details');
const refreshInstanceInfoButton = document.getElementById('refresh-instance-info');



// Metrics elements
const messagesSentElement = document.getElementById('messages-sent');
const messagesReceivedElement = document.getElementById('messages-received');
const tasksCreatedElement = document.getElementById('tasks-created');
const tasksCompletedElement = document.getElementById('tasks-completed');

// Generate or retrieve client ID - always use persistent storage
function getClientId() {
    let storedClientId = localStorage.getItem('clientId');
    
    if (!storedClientId) {
        storedClientId = Math.random().toString(36).substring(2, 10);
        localStorage.setItem('clientId', storedClientId);
    }
    
    return storedClientId;
}

// Connect to WebSocket
function connectWebSocket() {
    if (socket) {
        socket.close();
    }
    
    setConnectionStatus('connecting');
    
    clientId = getClientId();
    console.log('Connecting with client ID:', clientId); // Debug log
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${clientId}`;
    console.log('WebSocket URL:', wsUrl); // Debug log
    
    socket = new WebSocket(wsUrl);
    
    socket.onopen = () => {
        console.log('WebSocket connection established');
        setConnectionStatus('connected');
        enableInterface();
        reconnectAttempts = 0;
    };
    
    socket.onmessage = (event) => {
        console.log('Received message:', event.data); // Debug log
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
    
    socket.onclose = (event) => {
        console.log('WebSocket connection closed', event);
        setConnectionStatus('disconnected');
        disableInterface();
        
        // Auto-reconnect logic (if not manually disconnected)
        if (isConnected && reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            const delay = Math.min(1000 * reconnectAttempts, 5000);
            
            addSystemMessage(`Connection lost. Attempting to reconnect in ${delay/1000} seconds...`);
            
            setTimeout(() => {
                addSystemMessage(`Reconnecting... (Attempt ${reconnectAttempts}/${maxReconnectAttempts})`);
                connectWebSocket();
            }, delay);
        }
    };
    
    socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        addSystemMessage('WebSocket error occurred. Check console for details.');
    };
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    messagesReceived++;
    updateMetrics();
    
    switch (data.type) {
        case 'connection_info':
            instanceId = data.instance_id;
            instanceIdElement.textContent = instanceId;
            connectionCountElement.textContent = `Connections: ${data.connection_count}`;
            addSystemMessage(`Connected to server instance: ${instanceId}`);
            if (data.client_ip) {
                addSystemMessage(`Your IP address: ${data.client_ip}`);
            }
            highlightInstanceChange(instanceId);
            break;
            
        case 'chat':
            addChatMessage(data);
            highlightInstanceChange(data.instance_id);
            break;
            
        case 'system':
            addSystemMessage(data.content);
            highlightInstanceChange(data.instance_id);
            break;
            
        case 'message_history':
            // Display chat history
            const historySource = data.source || 'unknown';
            addSystemMessage(`Loaded ${data.messages.length} messages from ${historySource}`);
            
            // Clear chat if there are messages
            if (data.messages && data.messages.length > 0) {
                // Only display chat type messages from history
                const chatMessages = data.messages.filter(msg => msg.type === 'chat');
                
                // Add each message to the UI (in chronological order)
                chatMessages.forEach(msg => {
                    addChatMessage(msg);
                });
                
                addSystemMessage(`Loaded ${chatMessages.length} previous messages`);
            }
            break;
            
        case 'task_created':
            tasksCreated++;
            updateMetrics();
            addTaskToUI(data.task_id, data.details);
            break;
            
        case 'task_completed':
            tasksCompleted++;
            updateMetrics();
            updateTaskInUI(data.task_id, data.details);
            break;
            

        default:
            console.log('Unknown message type:', data);
    }
}

// UI Helper functions
function setConnectionStatus(status) {
    statusIconElement.className = `status-icon ${status}`;
    isConnected = status === 'connected';
    
    switch (status) {
        case 'connected':
            statusTextElement.textContent = 'Connected';
            break;
        case 'disconnected':
            statusTextElement.textContent = 'Disconnected';
            instanceIdElement.textContent = 'Not connected';
            break;
        case 'connecting':
            statusTextElement.textContent = 'Connecting...';
            break;
    }
}

function enableInterface() {
    messageInputElement.disabled = false;
    sendButtonElement.disabled = false;
    loadHistoryButtonElement.disabled = false;
    disconnectButtonElement.disabled = false;
    startTaskButtonElement.disabled = false;
    connectButtonElement.disabled = true;
}

function disableInterface() {
    messageInputElement.disabled = true;
    sendButtonElement.disabled = true;
    loadHistoryButtonElement.disabled = true;
    disconnectButtonElement.disabled = true;
    startTaskButtonElement.disabled = true;
    connectButtonElement.disabled = false;
}

function addChatMessage(data) {
    const messageElement = document.createElement('div');
    messageElement.className = 'message';
    
    const isSelf = data.client_id === clientId;
    messageElement.classList.add(isSelf ? 'self' : 'other');
    
    const formattedTime = new Date(data.timestamp).toLocaleTimeString();
    
    messageElement.innerHTML = `
        <div class="message-header">
            <span class="sender">${isSelf ? 'You' : data.client_id}</span>
            <span class="time">${formattedTime}</span>
            <span class="instance" title="Server Instance">[${data.instance_id}]</span>
        </div>
        <div class="message-content">${escapeHtml(data.content)}</div>
    `;
    
    chatMessagesElement.appendChild(messageElement);
    chatMessagesElement.scrollTop = chatMessagesElement.scrollHeight;
}

function addSystemMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.className = 'message system';
    messageElement.innerHTML = `<div class="message-content">${message}</div>`;
    
    chatMessagesElement.appendChild(messageElement);
    chatMessagesElement.scrollTop = chatMessagesElement.scrollHeight;
}

function highlightInstanceChange(newInstanceId) {
    if (instanceId && newInstanceId && instanceId !== newInstanceId) {
        addSystemMessage(`⚠️ Message routed through different instance! (${newInstanceId})`);
        
        // Visual flash effect
        document.body.classList.add('instance-changed');
        setTimeout(() => {
            document.body.classList.remove('instance-changed');
        }, 1000);
    }
}

function addTaskToUI(taskId, details) {
    const taskElement = document.createElement('div');
    taskElement.className = 'task running';
    taskElement.id = `task-${taskId}`;
    taskElement.innerHTML = `
        <div class="task-header">
            <span class="task-id">${taskId}</span>
            <span class="task-status">Running</span>
        </div>
        <div class="task-details">
            <div>Duration: ${details.duration}s</div>
            <div>Instance: ${details.instance_id}</div>
            <div class="task-progress">
                <div class="progress-bar"></div>
            </div>
        </div>
    `;
    
    tasksElement.appendChild(taskElement);
    
    // Animate progress bar
    const progressBar = taskElement.querySelector('.progress-bar');
    progressBar.style.transition = `width ${details.duration}s linear`;
    
    // Small delay to ensure transition works
    setTimeout(() => {
        progressBar.style.width = '100%';
    }, 50);
}

function updateTaskInUI(taskId, details) {
    const taskElement = document.getElementById(`task-${taskId}`);
    if (!taskElement) return;
    
    taskElement.className = `task ${details.status}`;
    
    const statusElement = taskElement.querySelector('.task-status');
    statusElement.textContent = details.status === 'completed' ? 'Completed' : 'Failed';
    
    const detailsElement = taskElement.querySelector('.task-details');
    const duration = details.duration || 'unknown';
    const completedTime = details.completed_at 
        ? new Date(details.completed_at).toLocaleTimeString()
        : 'unknown';
    
    detailsElement.innerHTML = `
        <div>Duration: ${duration}s</div>
        <div>Instance: ${details.instance_id}</div>
        <div>Completed: ${completedTime}</div>
    `;
    
    // Highlight different instance for task completion
    if (details.instance_id !== instanceId) {
        taskElement.classList.add('instance-mismatch');
        addSystemMessage(`⚠️ Task ${taskId} completed on different instance (${details.instance_id})!`);
    }
}

function updateMetrics() {
    messagesSentElement.textContent = messagesSent;
    messagesReceivedElement.textContent = messagesReceived;
    tasksCreatedElement.textContent = tasksCreated;
    tasksCompletedElement.textContent = tasksCompleted;
}

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

async function fetchInstanceInfo() {
    try {
        const response = await fetch('/instance');
        const data = await response.json();
        
        instanceDetailsElement.innerHTML = `
            <div>Instance ID: ${data.instance_id}</div>
            <div>Uptime: ${Math.floor(data.uptime / 60)} mins ${Math.floor(data.uptime % 60)} secs</div>
            <div>Active Connections: ${data.connection_count}</div>
            <div>Active Tasks: ${data.active_tasks}</div>
        `;
    } catch (error) {
        console.error('Error fetching instance info:', error);
        instanceDetailsElement.innerHTML = '<div class="error">Failed to fetch instance info</div>';
    }
}

// Message and action functions
function sendMessage() {
    const messageContent = messageInputElement.value.trim();
    console.log('Sending message:', messageContent); // Debug log
    if (messageContent && socket && socket.readyState === WebSocket.OPEN) {
        const message = {
            type: 'chat',
            content: messageContent,
            timestamp: Date.now()
        };
        
        console.log('Sending JSON:', JSON.stringify(message)); // Debug log
        socket.send(JSON.stringify(message));
        messageInputElement.value = '';
        messagesSent++;
        updateMetrics();
    } else {
        console.log('Cannot send message - socket state:', socket?.readyState, 'content:', messageContent); // Debug log
    }
}

function disconnectWebSocket() {
    if (socket) {
        isConnected = false; // Prevent auto-reconnect
        socket.close();
        socket = null;
    }
}

function loadHistory() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        const message = {
            type: 'get_history',
            limit: 50,
            history_type: 'user'
        };
        socket.send(JSON.stringify(message));
    }
}

function startBackgroundTask() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        const message = {
            type: 'task_request'
        };
        socket.send(JSON.stringify(message));
    }
}



function refreshInstanceInfo() {
    fetchInstanceInfo();
}

// Event listeners
connectButtonElement.addEventListener('click', connectWebSocket);
disconnectButtonElement.addEventListener('click', disconnectWebSocket);
sendButtonElement.addEventListener('click', sendMessage);
messageInputElement.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});
loadHistoryButtonElement.addEventListener('click', loadHistory);
startTaskButtonElement.addEventListener('click', startBackgroundTask);
refreshInstanceInfoButton.addEventListener('click', refreshInstanceInfo);





// Add additional CSS styles for instance changes and task statuses
const style = document.createElement('style');
style.textContent = `
    .message {
        padding: 8px;
        margin-bottom: 8px;
        border-radius: 8px;
        background-color: #f1f1f1;
    }
    
    .message.self {
        background-color: #d4edda;
    }
    
    .message.system {
        background-color: #cce5ff;
        font-style: italic;
    }
    
    .message-header {
        font-size: 0.8em;
        display: flex;
        justify-content: space-between;
        margin-bottom: 4px;
    }
    
    .instance {
        color: #666;
    }
    
    @keyframes highlight-change {
        0% { background-color: rgba(255, 193, 7, 0.2); }
        50% { background-color: rgba(255, 193, 7, 0.5); }
        100% { background-color: rgba(255, 193, 7, 0); }
    }
    
    body.instance-changed {
        animation: highlight-change 1s;
    }
    
    .task {
        padding: 10px;
        margin-bottom: 10px;
        border-radius: 4px;
        border: 1px solid #ddd;
    }
    
    .task.running {
        background-color: #fff3cd;
    }
    
    .task.completed {
        background-color: #d4edda;
    }
    
    .task.failed {
        background-color: #f8d7da;
    }
    
    .task-header {
        display: flex;
        justify-content: space-between;
        margin-bottom: 6px;
    }
    
    .task-progress {
        height: 5px;
        background-color: #e9ecef;
        border-radius: 2px;
        margin-top: 6px;
        overflow: hidden;
    }
    
    .progress-bar {
        height: 100%;
        width: 0%;
        background-color: var(--primary-color);
    }
    
    .task.instance-mismatch {
        border: 2px solid var(--warning-color);
    }
`;
document.head.appendChild(style);

// Initialize page
fetchInstanceInfo();

// Add tooltip for startup
addSystemMessage('Click "Connect WebSocket" to begin the demonstration');