import { API_URL } from "../config.js";
import { escapeHTML } from "../utils.js";
import { displayDetectionTable } from "./table.js";
import { resetChatState } from "./chat.js";

export function displayObjectSummary(objectCounts) {
    const container = document.getElementById("objectSummary");
    if (!container) return;

    container.innerHTML = "";
    const objects = Object.entries(objectCounts);

    if (objects.length === 0) {
        container.innerHTML = `<p>No objects were detected.</p>`;
        return;
    }

    objects.forEach(([objectName, count]) => {
        const card = document.createElement("div");
        card.className = "object-card";
        card.innerHTML = `
            <div class="object-name">${escapeHTML(objectName)}</div>
            <div class="object-count">${count}</div>
            <div class="object-label">detections</div>
        `;
        container.appendChild(card);
    });
}

export function displayResults(data) {
    const resultElement = document.getElementById("result");
    if (!resultElement) return;

    resultElement.classList.remove("hidden");

    const analysisId = data.analysis_id || "—";
    resetChatState(data.analysis_id || null);

    document.getElementById("analysisId").textContent = `Analysis ID: ${analysisId}`;
    document.getElementById("forensicAnalysisId").textContent = analysisId;

    const totalDetections = data.total_detections || 0;
    document.getElementById("totalDetections").textContent = totalDetections;
    document.getElementById("forensicDetections").textContent = totalDetections;

    const objectCounts = data.object_counts || {};
    const objectTypes = Object.keys(objectCounts);

    document.getElementById("objectTypeCount").textContent = objectTypes.length;
    document.getElementById("personCount").textContent = objectCounts.person || 0;

    const vehicleCount =
        (objectCounts.car || 0) +
        (objectCounts.truck || 0) +
        (objectCounts.bus || 0) +
        (objectCounts.motorcycle || 0) +
        (objectCounts.bicycle || 0);

    document.getElementById("vehicleCount").textContent = vehicleCount;

    displayObjectSummary(objectCounts);

    if (data.annotated_video) {
        const downloadVideo = document.getElementById("downloadVideo");
        const filename = data.annotated_video.split("/").pop();
        const downloadURL = `${API_URL}/download-video/${encodeURIComponent(filename)}`;

        if (downloadVideo) {
            downloadVideo.href = downloadURL;
            downloadVideo.removeAttribute("target");
            downloadVideo.style.display = "inline-block";
            downloadVideo.textContent = "⬇ Download Annotated Video";
        }
    }

    if (data.detections_file) {
        const downloadButton = document.getElementById("downloadJson");
        const jsonURL = API_URL + data.detections_file;
        if (downloadButton) {
            downloadButton.href = jsonURL;
        }
    }

    displayDetectionTable(data.detections || []);

    setTimeout(() => {
        resultElement.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 300);
}
