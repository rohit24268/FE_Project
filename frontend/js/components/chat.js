import { investigateAPI } from "../api.js";

let currentAnalysisId = null;
let chatHistory = [];

export function resetChatState(analysisId) {
    currentAnalysisId = analysisId;
    chatHistory = [];

    const chatWindow = document.getElementById("chatWindow");
    if (chatWindow) {
        chatWindow.innerHTML = `
            <div class="chat-message chat-assistant">
                <div class="chat-bubble">
                    Ask me anything about this footage —
                    for example, "When did a person first
                    appear?" or "How many unique vehicles
                    were tracked?"
                </div>
            </div>
        `;
    }

    const chatNote = document.getElementById("chatNote");
    if (chatNote) {
        chatNote.textContent = "";
    }
}

export function appendChatMessage(role, text, isLoading = false) {
    const chatWindow = document.getElementById("chatWindow");
    if (!chatWindow) return null;

    const message = document.createElement("div");
    message.className =
        `chat-message chat-${role}` + (isLoading ? " chat-loading" : "");

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = text;

    message.appendChild(bubble);
    chatWindow.appendChild(message);
    chatWindow.scrollTop = chatWindow.scrollHeight;

    return message;
}

export async function sendChatMessage() {
    const chatInput = document.getElementById("chatInput");
    const chatSendButton = document.getElementById("chatSendButton");
    const chatNote = document.getElementById("chatNote");

    if (!chatInput) return;
    const question = chatInput.value.trim();

    if (!question) return;

    if (!currentAnalysisId) {
        if (chatNote) {
            chatNote.textContent = "Run an analysis first before asking questions.";
        }
        return;
    }

    appendChatMessage("user", question);
    chatInput.value = "";
    chatInput.disabled = true;
    if (chatSendButton) chatSendButton.disabled = true;
    if (chatNote) chatNote.textContent = "";

    const loadingMessage = appendChatMessage(
        "assistant",
        "Reviewing the evidence...",
        true
    );

    try {
        const data = await investigateAPI(currentAnalysisId, question, chatHistory);

        if (loadingMessage) loadingMessage.remove();
        appendChatMessage("assistant", data.answer);

        chatHistory.push({ role: "user", content: question });
        chatHistory.push({ role: "assistant", content: data.answer });

        if (chatHistory.length > 12) {
            chatHistory = chatHistory.slice(-12);
        }
    } catch (error) {
        if (loadingMessage) loadingMessage.remove();
        appendChatMessage(
            "assistant",
            error.message || "Something went wrong. Please try again."
        );
    } finally {
        chatInput.disabled = false;
        if (chatSendButton) chatSendButton.disabled = false;
        chatInput.focus();
    }
}
