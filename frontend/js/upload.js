// ==================================================
// FILE SELECTION
// ==================================================

videoInput.addEventListener("change", function () {

    if (
        !this.files ||
        this.files.length === 0
    ) {

        fileName.textContent =
            "No file selected";

        return;
    }


    const file =
        this.files[0];


    const size =
        (
            file.size /
            (1024 * 1024)
        ).toFixed(2);


    fileName.textContent =
        `${file.name} (${size} MB)`;
});


// ==================================================
// UPLOAD VIDEO
// ==================================================

async function uploadVideo() {

    const file =
        videoInput.files[0];


    if (!file) {

        showStatus(
            "Please select a CCTV video first.",
            "error"
        );

        return;
    }


    // ==================================================
    // DISABLE BUTTON
    // ==================================================

    uploadButton.disabled = true;

    buttonText.textContent =
        "Analyzing...";


    // ==================================================
    // SHOW LOADING
    // ==================================================

    loading.classList.remove(
        "hidden"
    );

    result.classList.add(
        "hidden"
    );


    showStatus(
        "Uploading CCTV footage...",
        ""
    );


    // ==================================================
    // CREATE FORM DATA
    // ==================================================

    const formData =
        new FormData();


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


        // ==================================================
        // SEND REQUEST
        // ==================================================

        const response =
            await fetch(
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


        // ==================================================
        // READ RESPONSE
        // ==================================================

        const text =
            await response.text();


        console.log(
            "Raw backend response:",
            text
        );


        let data;


        try {

            data =
                JSON.parse(text);

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


        // ==================================================
        // CHECK HTTP ERROR
        // ==================================================

        if (!response.ok) {

            throw new Error(
                data.detail ||
                "Video analysis failed."
            );
        }


        // ==================================================
        // DISPLAY RESULTS
        // ==================================================

        displayResults(
            data
        );


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

        uploadButton.disabled =
            false;


        buttonText.textContent =
            "Analyze CCTV Evidence";


        loading.classList.add(
            "hidden"
        );
    }
}