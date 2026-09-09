import { API_URL } from "./config.js";

export async function analyzeVideoAPI(file) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_URL}/analyze-video`, {
        method: "POST",
        body: formData
    });

    const text = await response.text();
    let data;
    try {
        data = JSON.parse(text);
    } catch (jsonError) {
        throw new Error("Backend returned invalid JSON: " + text);
    }

    if (!response.ok) {
        throw new Error(data.detail || "Video analysis failed.");
    }

    return data;
}

export async function investigateAPI(analysisId, question, history) {
    const response = await fetch(`${API_URL}/investigate`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            analysis_id: analysisId,
            question: question,
            history: history
        })
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(
            data.detail || "The investigation assistant could not answer that."
        );
    }

    return data;
}
