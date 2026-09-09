// ==================================================
// APPEND CHAT MESSAGE
// ==================================================

function appendChatMessage(
    role,
    text,
    isLoading = false
) {

    const message =
        document.createElement(
            "div"
        );


    message.className =
        `chat-message chat-${role}` +
        (
            isLoading
                ? " chat-loading"
                : ""
        );


    const bubble =
        document.createElement(
            "div"
        );


    bubble.className =
        "chat-bubble";


    bubble.textContent =
        text;


    message.appendChild(
        bubble
    );


    chatWindow.appendChild(
        message
    );


    chatWindow.scrollTop =
        chatWindow.scrollHeight;


    return message;
}


// ==================================================
// SEND CHAT MESSAGE
// ==================================================

async function sendChatMessage() {

    const question =
        chatInput.value.trim();


    if (!question) {
        return;
    }


    // ==================================================
    // CHECK ANALYSIS
    // ==================================================

    if (!currentAnalysisId) {

        chatNote.textContent =
            "Run an analysis first before asking questions.";

        return;
    }


    // ==================================================
    // SHOW USER QUESTION
    // ==================================================

    appendChatMessage(
        "user",
        question
    );


    chatInput.value =
        "";


    chatInput.disabled =
        true;


    chatSendButton.disabled =
        true;


    chatNote.textContent =
        "";


    // ==================================================
    // LOADING MESSAGE
    // ==================================================

    const loadingMessage =
        appendChatMessage(
            "assistant",
            "Reviewing the evidence...",
            true
        );


    try {

        // ==================================================
        // SEND INVESTIGATION REQUEST
        // ==================================================

        const response =
            await fetch(
                `${API_URL}/investigate`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        analysis_id:
                            currentAnalysisId,

                        question:
                            question,

                        history:
                            chatHistory
                    })
                }
            );


        const data =
            await response.json();


        // ==================================================
        // CHECK ERROR
        // ==================================================

        if (!response.ok) {

            throw new Error(
                data.detail ||
                "The investigation assistant could not answer that."
            );
        }


        // ==================================================
        // SHOW ANSWER
        // ==================================================

        loadingMessage.remove();


        appendChatMessage(
            "assistant",
            data.answer
        );


        // ==================================================
        // SAVE CHAT HISTORY
        // ==================================================

        chatHistory.push({
            role: "user",
            content: question
        });


        chatHistory.push({
            role: "assistant",
            content: data.answer
        });


        // Keep last 12 messages
        if (chatHistory.length > 12) {

            chatHistory =
                chatHistory.slice(-12);
        }


    } catch (error) {

        loadingMessage.remove();


        appendChatMessage(
            "assistant",
            error.message ||
            "Something went wrong. Please try again."
        );


    } finally {

        chatInput.disabled =
            false;


        chatSendButton.disabled =
            false;


        chatInput.focus();
    }
}