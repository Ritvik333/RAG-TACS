async function sendMessage() {
    const input = document.getElementById('user-input').value.trim();
    const messages = document.getElementById('messages');
    const loading = document.getElementById('loading');

    if (!input) {
        messages.innerHTML += `<p class="error"><strong>Error:</strong> Please enter a question.</p>`;
        scrollToBottom();
        return;
    }

    const escapedInput = escapeHtml(input);
    messages.innerHTML += `<p class="user"><strong>You:</strong> ${escapedInput}</p>`;
    document.getElementById('user-input').value = '';
    scrollToBottom();

    loading.style.display = 'block';

    try {
        const response = await fetch('https://f15vjt8in1.execute-api.us-east-1.amazonaws.com/prod/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: input })
        });

        const data = await response.json();

        let context = '';
        let botResponse = '';

        if (data.context !== undefined && data.response !== undefined) {
            context = data.context;
            botResponse = data.response;
        } else if (data.body) {
            let parsedBody = data.body;
            if (typeof parsedBody === 'string') {
                try {
                    parsedBody = JSON.parse(parsedBody);
                } catch (e) {
                    parsedBody = { response: parsedBody };
                }
            }
            context = parsedBody.context || '';
            botResponse = parsedBody.response || '';
        } else {
            botResponse = data.response || 'No response from bot.';
        }

        const formattedContext = context ? formatContext(context) : '';
        const formattedResponse = botResponse
            ? `<div class="response-box"><h4>Response</h4>${escapeHtml(botResponse)}</div>`
            : '<div class="response-box"><h4>Response</h4>No response from bot.</div>';

        messages.innerHTML += `
            <div class="bot-message-box">
                <strong>Bot:</strong>
                ${formattedContext}
                ${formattedResponse}
            </div>`;

    } catch (error) {
        messages.innerHTML += `<p class="error"><strong>Error:</strong> Unable to connect to the server.</p>`;
    } finally {
        loading.style.display = 'none';
        scrollToBottom();
    }
}

function scrollToBottom() {
    const messages = document.getElementById('messages');
    messages.scrollTop = messages.scrollHeight;
}

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatContext(rawContext) {
    const contextParts = rawContext.split(/Context \d+:/g).filter(Boolean);

    let formatted = '';
    contextParts.forEach((part, index) => {
        const cleaned = part
            .replace(/Problem:\s*/i, '')
            .replace(/Solution:\s*/i, '')
            .trim();

        const lines = cleaned.split('\n').map(line => line.trim()).filter(Boolean);
        const title = `Context ${index + 1}: ${lines[0]}`;
        const steps = lines.slice(1).map(line => escapeHtml(line)).join('<br>');

        formatted += `<div style="margin-bottom: 1em;"><strong>${escapeHtml(title)}</strong><br>${steps}</div>`;
    });

    return `<div class="context-box"><h4>Context</h4>${formatted}</div>`;
}
