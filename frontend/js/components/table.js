import { formatTime, escapeHTML } from "../utils.js";

export function displayDetectionTable(detections) {
    const table = document.getElementById("detectionsTable");
    if (!table) return;

    table.innerHTML = "";

    if (!detections || detections.length === 0) {
        table.innerHTML = `
            <tr>
                <td colspan="6">No detections available.</td>
            </tr>
        `;
        document.getElementById("tableNote").textContent =
            "No detection events were returned by the backend.";
        return;
    }

    const displayed = detections.slice(0, 100);

    displayed.forEach(detection => {
        const row = document.createElement("tr");

        const objectName = detection.object || "Unknown";
        const trackId =
            detection.track_id !== null && detection.track_id !== undefined
                ? detection.track_id
                : "—";

        const timestamp = formatTime(detection.timestamp);
        const confidence =
            detection.confidence !== null && detection.confidence !== undefined
                ? (detection.confidence * 100).toFixed(1) + "%"
                : "—";

        const frame =
            detection.frame !== null && detection.frame !== undefined
                ? detection.frame
                : "—";

        const bbox = detection.bounding_box;
        let boundingBox = "—";
        if (bbox) {
            boundingBox = `${bbox.x1}, ${bbox.y1}, ${bbox.x2}, ${bbox.y2}`;
        }

        row.innerHTML = `
            <td><strong>${escapeHTML(objectName)}</strong></td>
            <td>${trackId}</td>
            <td>${timestamp}</td>
            <td>${confidence}</td>
            <td>${frame}</td>
            <td>${escapeHTML(boundingBox)}</td>
        `;

        table.appendChild(row);
    });

    const note = document.getElementById("tableNote");
    if (detections.length > 100) {
        note.textContent =
            `Showing first 100 of ${detections.length} detections. ` +
            `Download the JSON file for complete evidence data.`;
    } else {
        note.textContent = `${detections.length} detection events recorded.`;
    }
}
