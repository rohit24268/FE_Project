import { analyzeVideoAPI } from "./api.js";
import { showStatus } from "./utils.js";
import { displayResults } from "./components/stats.js";
import { sendChatMessage } from "./components/chat.js";

document.addEventListener("DOMContentLoaded", () => {
    const videoInput = document.getElementById("videoInput");
    const fileName = document.getElementById("fileName");
    const uploadButton = document.getElementById("uploadButton");
    const buttonText = document.getElementById("buttonText");
    const loading = document.getElementById("loading");
    const result = document.getElementById("result");
    const chatInput = document.getElementById("chatInput");
    const chatSendButton = document.getElementById("chatSendButton");

    console.log("ForenSight AI modular frontend initialized");

    if (videoInput && fileName) {
        videoInput.addEventListener("change", function () {
            if (!this.files || this.files.length === 0) {
                fileName.textContent = "No file selected";
                return;
            }
            const file = this.files[0];
            const size = (file.size / (1024 * 1024)).toFixed(2);
            fileName.textContent = `${file.name} (${size} MB)`;
        });
    }

    if (uploadButton) {
        uploadButton.addEventListener("click", uploadVideo);
    }

    if (chatSendButton) {
        chatSendButton.addEventListener("click", sendChatMessage);
    }

    if (chatInput) {
        chatInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                sendChatMessage();
            }
        });
    }

    async function uploadVideo() {
        const file = videoInput ? videoInput.files[0] : null;

        if (!file) {
            showStatus("Please select a CCTV video first.", "error");
            return;
        }

        if (uploadButton) uploadButton.disabled = true;
        if (buttonText) buttonText.textContent = "Analyzing...";
        if (loading) loading.classList.remove("hidden");
        if (result) result.classList.add("hidden");

        showStatus("Uploading CCTV footage...", "");

        try {
            showStatus("YOLO is analyzing the CCTV footage. Please wait...", "");
            const data = await analyzeVideoAPI(file);
            displayResults(data);
            showStatus("CCTV analysis completed successfully.", "success");
        } catch (error) {
            console.error("Analysis error:", error);
            showStatus(error.message || "Unable to analyze video.", "error");
        } finally {
            if (uploadButton) uploadButton.disabled = false;
            if (buttonText) buttonText.textContent = "Analyze CCTV Evidence";
            if (loading) loading.classList.add("hidden");
        }
    }
});
