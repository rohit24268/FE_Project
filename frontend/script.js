const API_URL = "http://localhost:8000";

// --------------------------------------------------
// ELEMENTS
// --------------------------------------------------

const videoInput = document.getElementById("videoInput");
const fileName = document.getElementById("fileName");
const uploadButton = document.getElementById("uploadButton");
const buttonText = document.getElementById("buttonText");
const loading = document.getElementById("loading");
const result = document.getElementById("result");
const status = document.getElementById("status");


// --------------------------------------------------
// CHECK FRONTEND
// --------------------------------------------------

console.log("ForenSight AI frontend loaded");
console.log("Backend URL:", API_URL);


// --------------------------------------------------
// FILE SELECTION
// --------------------------------------------------

videoInput.addEventListener("change", function () {

    if (!this.files || this.files.length === 0) {

        fileName.textContent = "No file selected";

        return;
    }

    const file = this.files[0];

    const size =
        (file.size / (1024 * 1024)).toFixed(2);

    fileName.textContent =
        `${file.name} (${size} MB)`;

});


// --------------------------------------------------
// UPLOAD VIDEO
// --------------------------------------------------

async function uploadVideo() {

    const file = videoInput.files[0];

    if (!file) {

        showStatus(
            "Please select a CCTV video first.",
            "error"
        );

        return;
    }


    // Disable button
    uploadButton.disabled = true;

    buttonText.textContent =
        "Analyzing...";


    // Show loading
    loading.classList.remove("hidden");

    result.classList.add("hidden");


    showStatus(
        "Uploading CCTV footage...",
        ""
    );


    // Create form data
    const formData = new FormData();

    formData.append(
        "file",
        file
    );


    try {

        console.log(
            "Sending video to:",
            `${API_URL}/analyze-video`
        );


        showStatus(
            "YOLO is analyzing the CCTV footage. Please wait...",
            ""
        );


        // --------------------------------------------------
        // SEND REQUEST
        // --------------------------------------------------

        const response = await fetch(
            `${API_URL}/analyze-video`,
            {
                method: "POST",
                body: formData
            }
        );


        console.log(
            "Backend response status:",
            response.status
        );


        // --------------------------------------------------
        // READ RESPONSE
        // --------------------------------------------------

        const text =
            await response.text();


        console.log(
            "Raw backend response:",
            text
        );


        let data;

        try {

            data = JSON.parse(text);

        } catch (jsonError) {

            throw new Error(
                "Backend returned invalid JSON: " +
                text
            );
        }


        console.log(
            "Parsed backend data:",
            data
        );


        // --------------------------------------------------
        // CHECK HTTP ERROR
        // --------------------------------------------------

        if (!response.ok) {

            throw new Error(
                data.detail ||
                "Video analysis failed."
            );
        }


        // --------------------------------------------------
        // DISPLAY RESULTS
        // --------------------------------------------------

        displayResults(data);


        showStatus(
            "CCTV analysis completed successfully.",
            "success"
        );


    } catch (error) {

        console.error(
            "Analysis error:",
            error
        );


        showStatus(
            error.message ||
            "Unable to analyze video.",
            "error"
        );


    } finally {

        uploadButton.disabled = false;

        buttonText.textContent =
            "Analyze CCTV Evidence";

        loading.classList.add("hidden");

    }

}


// --------------------------------------------------
// DISPLAY RESULTS
// --------------------------------------------------

function displayResults(data) {

    console.log(
        "Displaying analysis results:",
        data
    );


    // Show result section
    result.classList.remove("hidden");


    // --------------------------------------------------
    // ANALYSIS ID
    // --------------------------------------------------

    const analysisId =
        data.analysis_id || "—";


    document.getElementById(
        "analysisId"
    ).textContent =
        `Analysis ID: ${analysisId}`;


    document.getElementById(
        "forensicAnalysisId"
    ).textContent =
        analysisId;


    // --------------------------------------------------
    // TOTAL DETECTIONS
    // --------------------------------------------------

    const totalDetections =
        data.total_detections || 0;


    document.getElementById(
        "totalDetections"
    ).textContent =
        totalDetections;


    document.getElementById(
        "forensicDetections"
    ).textContent =
        totalDetections;


    // --------------------------------------------------
    // OBJECT COUNTS
    // --------------------------------------------------

    const objectCounts =
        data.object_counts || {};


    const objectTypes =
        Object.keys(objectCounts);


    document.getElementById(
        "objectTypeCount"
    ).textContent =
        objectTypes.length;


    // --------------------------------------------------
    // PERSON COUNT
    // --------------------------------------------------

    document.getElementById(
        "personCount"
    ).textContent =
        objectCounts.person || 0;


    // --------------------------------------------------
    // VEHICLE COUNT
    // --------------------------------------------------

    const vehicleCount =
        (objectCounts.car || 0) +
        (objectCounts.truck || 0) +
        (objectCounts.bus || 0) +
        (objectCounts.motorcycle || 0) +
        (objectCounts.bicycle || 0);


    document.getElementById(
        "vehicleCount"
    ).textContent =
        vehicleCount;


    // --------------------------------------------------
    // OBJECT SUMMARY
    // --------------------------------------------------

    displayObjectSummary(
        objectCounts
    );


    // --------------------------------------------------
    // DOWNLOAD ANNOTATED VIDEO
    // --------------------------------------------------



    if (data.annotated_video) {

        const downloadVideo =
            document.getElementById("downloadVideo");

        // Backend returns:
        // /results/analysisid_annotated.mp4

        const filename =
            data.annotated_video
                .split("/")
                .pop();

        const downloadURL =
            `${API_URL}/download-video/${encodeURIComponent(filename)}`;

        console.log(
            "Annotated video download URL:",
            downloadURL
        );

        if (downloadVideo) {

            downloadVideo.href =
                downloadURL;

            downloadVideo.removeAttribute("target");

            downloadVideo.style.display =
                "inline-block";

            downloadVideo.textContent =
                "⬇ Download Annotated Video";
        }

    }


    // --------------------------------------------------
    // DOWNLOAD JSON
    // --------------------------------------------------

    if (data.detections_file) {

        const downloadButton =
            document.getElementById(
                "downloadJson"
            );


        const jsonURL =
            API_URL +
            data.detections_file;


        console.log(
            "JSON evidence URL:",
            jsonURL
        );


        if (downloadButton) {

            downloadButton.href =
                jsonURL;

        }

    }


    // --------------------------------------------------
    // DETECTION TABLE
    // --------------------------------------------------

    displayDetectionTable(
        data.detections || []
    );


    // --------------------------------------------------
    // SCROLL TO RESULTS
    // --------------------------------------------------

    setTimeout(function () {

        result.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });

    }, 300);

}


// --------------------------------------------------
// OBJECT SUMMARY
// --------------------------------------------------

function displayObjectSummary(
    objectCounts
) {

    const container =
        document.getElementById(
            "objectSummary"
        );


    container.innerHTML = "";


    const objects =
        Object.entries(
            objectCounts
        );


    if (objects.length === 0) {

        container.innerHTML = `
            <p>
                No objects were detected.
            </p>
        `;

        return;
    }


    objects.forEach(
        ([objectName, count]) => {

            const card =
                document.createElement(
                    "div"
                );


            card.className =
                "object-card";


            card.innerHTML = `
                <div class="object-name">
                    ${escapeHTML(objectName)}
                </div>

                <div class="object-count">
                    ${count}
                </div>

                <div class="object-label">
                    detections
                </div>
            `;


            container.appendChild(
                card
            );

        }
    );

}


// --------------------------------------------------
// DETECTION TABLE
// --------------------------------------------------

function displayDetectionTable(
    detections
) {

    const table =
        document.getElementById(
            "detectionsTable"
        );


    table.innerHTML = "";


    if (
        !detections ||
        detections.length === 0
    ) {

        table.innerHTML = `
            <tr>
                <td colspan="6">
                    No detections available.
                </td>
            </tr>
        `;


        document.getElementById(
            "tableNote"
        ).textContent =
            "No detection events were returned by the backend.";


        return;
    }


    console.log(
        "Number of detections:",
        detections.length
    );


    const displayed =
        detections.slice(0, 100);


    displayed.forEach(
        function (detection) {

            const row =
                document.createElement(
                    "tr"
                );


            const objectName =
                detection.object ||
                "Unknown";


            const trackId =
                detection.track_id !== null &&
                    detection.track_id !== undefined
                    ? detection.track_id
                    : "—";


            const timestamp =
                formatTime(
                    detection.timestamp
                );


            const confidence =
                detection.confidence !== null &&
                    detection.confidence !== undefined
                    ? (
                        detection.confidence * 100
                    ).toFixed(1) + "%"
                    : "—";


            const frame =
                detection.frame !== null &&
                    detection.frame !== undefined
                    ? detection.frame
                    : "—";


            const bbox =
                detection.bounding_box;


            let boundingBox =
                "—";


            if (bbox) {

                boundingBox =
                    `${bbox.x1}, ${bbox.y1}, ` +
                    `${bbox.x2}, ${bbox.y2}`;

            }


            row.innerHTML = `
                <td>
                    <strong>
                        ${escapeHTML(objectName)}
                    </strong>
                </td>

                <td>
                    ${trackId}
                </td>

                <td>
                    ${timestamp}
                </td>

                <td>
                    ${confidence}
                </td>

                <td>
                    ${frame}
                </td>

                <td>
                    ${escapeHTML(
                boundingBox
            )}
                </td>
            `;


            table.appendChild(
                row
            );

        }
    );


    const note =
        document.getElementById(
            "tableNote"
        );


    if (detections.length > 100) {

        note.textContent =
            `Showing first 100 of ` +
            `${detections.length} detections. ` +
            `Download the JSON file for ` +
            `complete evidence data.`;

    } else {

        note.textContent =
            `${detections.length} detection events recorded.`;

    }

}


// --------------------------------------------------
// FORMAT TIME
// --------------------------------------------------

function formatTime(
    seconds
) {

    if (
        seconds === undefined ||
        seconds === null
    ) {

        return "—";

    }


    const mins =
        Math.floor(
            seconds / 60
        );


    const secs =
        Math.floor(
            seconds % 60
        );


    return (
        String(mins).padStart(2, "0") +
        ":" +
        String(secs).padStart(2, "0")
    );

}


// --------------------------------------------------
// STATUS
// --------------------------------------------------

function showStatus(
    message,
    type
) {

    status.textContent =
        message;


    status.className =
        "status";


    if (type) {

        status.classList.add(
            type
        );

    }

}


// --------------------------------------------------
// HTML ESCAPING
// --------------------------------------------------

function escapeHTML(
    value
) {

    const div =
        document.createElement(
            "div"
        );


    div.textContent =
        String(value);


    return div.innerHTML;

}