const videoInput = document.getElementById("videoInput");

const fileName = document.getElementById("fileName");

const uploadButton =
    document.getElementById("uploadButton");

const status =
    document.getElementById("status");

const result =
    document.getElementById("result");

const resultContent =
    document.getElementById("resultContent");


videoInput.addEventListener("change", function () {

    if (videoInput.files.length > 0) {

        fileName.textContent =
            videoInput.files[0].name;

    } else {

        fileName.textContent =
            "No file selected";
    }
});


async function uploadVideo() {

    const file = videoInput.files[0];

    if (!file) {

        status.textContent =
            "Please select a CCTV video.";

        return;
    }


    const formData = new FormData();

    formData.append("file", file);


    uploadButton.disabled = true;

    uploadButton.textContent =
        "Uploading...";

    status.textContent =
        "Uploading CCTV footage...";


    try {

        const response = await fetch(
            "http://127.0.0.1:8000/upload-video",
            {
                method: "POST",
                body: formData
            }
        );


        if (!response.ok) {

            throw new Error(
                "Upload failed"
            );
        }


        const data =
            await response.json();


        status.textContent =
            "Upload successful!";


        result.classList.remove("hidden");


        resultContent.innerHTML = `

    <h3>Video Information</h3>

    <p>
        <strong>Filename:</strong>
        ${data.filename}
    </p>

    <p>
        <strong>Resolution:</strong>
        ${data.video_info.width} ×
        ${data.video_info.height}
    </p>

    <p>
        <strong>FPS:</strong>
        ${data.video_info.fps}
    </p>

    <p>
        <strong>Duration:</strong>
        ${data.video_info.duration_seconds} seconds
    </p>

    <p>
        <strong>Frames Extracted:</strong>
        ${data.frames_extracted}
    </p>

`;

    }

    catch (error) {

        console.error(error);

        status.textContent =
            "Something went wrong while uploading.";

    }

    finally {

        uploadButton.disabled = false;

        uploadButton.textContent =
            "Upload & Analyze";
    }
}