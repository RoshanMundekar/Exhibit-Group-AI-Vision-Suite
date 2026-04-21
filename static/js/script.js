let progressInterval;

document.getElementById("progress-popup-btn").addEventListener("click", function () {
    fetchProgress();
    document.getElementById("progress-popup").style.display = "block";
    progressInterval = setInterval(fetchProgress, 10000);
});

function closePopup() {
    document.getElementById("progress-popup").style.display = "none";
    clearInterval(progressInterval);
}

async function fetchProgress() {
    try {
        const response = await fetch("/progress");
        const data = await response.json();

        document.getElementById("total-images").innerText = data.total || 0;
        document.getElementById("processed-images").innerText = data.processed || 0;
        document.getElementById("remaining-images").innerText = data.remaining || 0;

        let total = data.total || 1;
        let processed = data.processed || 0;
        let progressPercentage = Math.floor((processed / total) * 100);

        document.getElementById("progress-bar").style.width = `${progressPercentage}%`;
        document.getElementById("progress-text").innerText = `${progressPercentage}%`;

        document.getElementById("restart-btn").style.display = data.status === "failed" ? "block" : "none";

        if (progressPercentage >= 100) clearInterval(progressInterval);
    } catch (error) {
        console.error("Error fetching progress:", error);
    }
}

async function restartTraining() {
    try {
        const response = await fetch("/restart", { method: "POST" });
        if (response.ok) {
            alert("Training restarted!");
            document.getElementById("progress-bar").style.width = "0%";
            document.getElementById("progress-text").innerText = "0%";
            document.getElementById("restart-btn").style.display = "none";
            fetchProgress();
        } else {
            alert("Failed to restart training.");
        }
    } catch (error) {
        console.error("Error restarting training:", error);
    }
}

document.getElementById("uploadForm").addEventListener("submit", function (event) {
    event.preventDefault();

    let formData = new FormData(this);
    document.getElementById("results-container").style.display = "none";

    fetch("/search", {
        method: "POST",
        body: formData,
    })
        .then(response => response.json())
        .then(data => {
            console.log("Search successful:", data);
            displayResults(data.results);
        })
        .catch(error => {
            alert("Error: " + error);
            console.error("Error during search:", error);
        });
});

function displayResults(results) {
    const resultsContainer = document.getElementById("results-container");
    const similarImagesContainer = document.getElementById("similar-images");
    const queryImageContainer = document.querySelector('.query-image');

    // Clear previous results
    similarImagesContainer.innerHTML = "";
    resultsContainer.style.display = "none";

    // Handle missing results
    if (!Array.isArray(results) || results.length === 0 || results.length === 1) {
        alert(results.length === 1 ? "No similar images found." : "Invalid results");
        return;
    }

    // Update query image section
    queryImageContainer.innerHTML = `
        <h3 class="text-xl font-semibold mb-4">Query Image</h3> <!-- Add heading here -->
        <div class="result-card bg-white p-4 rounded-lg shadow-lg hover:shadow-xl transition-shadow relative border-2 border-blue-500 mx-auto" style="width: 256px;">
            <div class="flex items-center justify-between mb-3 header border-b border-gray-200 pb-2">
                <div class="image-name text-sm font-medium text-gray-700 truncate max-w-[85%]">
                    ${results[0].name || 'Query Image'}
                </div>
                <button onclick="viewImage('${results[0].image}','${results[0].name || 'Query Image'}')" 
                    class="p-1 hover:bg-gray-50 rounded-md border border-gray-300 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M3 3 L9 3 M3 3 L3 9 M3 3 L9 9 M21 3 L15 3 M21 3 L21 9 M21 3 L15 9 M3 21 L9 21 M3 21 L3 15 M3 21 L9 15 M21 21 L15 21 M21 21 L21 15 M21 21 L15 15" />
                    </svg>
                </button>
            </div>
            <img src="data:image/jpeg;base64,${results[0].image}" alt="Query Image" 
                 class="w-full h-48 object-contain rounded-lg">
        </div>
    `;

    // Update result images
    resultsContainer.style.display = "block";
    for (let i = 1; i < results.length; i++) {
        let imageHTML = `
            <div class="result-card bg-white p-4 rounded-lg shadow-lg hover:shadow-xl transition-shadow relative border border-blue-500">
                <div class="flex items-center justify-between mb-3 header border-b border-gray-200 pb-2">
                    <div class="image-name text-sm font-medium text-gray-700 truncate max-w-[85%]">
                        ${results[i].name}
                    </div>
                    <button onclick="viewImage('${results[i].image}','${results[i].name}')" 
                        class="p-1 hover:bg-gray-50 rounded-md border border-gray-300 transition-colors">
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M3 3 L9 3 M3 3 L3 9 M3 3 L9 9 M21 3 L15 3 M21 3 L21 9 M21 3 L15 9 M3 21 L9 21 M3 21 L3 15 M3 21 L9 15 M21 21 L15 21 M21 21 L21 15 M21 21 L15 15" />
                        </svg>
                    </button>
                </div>
                <img src="data:image/jpeg;base64,${results[i].image}" alt="Similar Image" 
                     class="w-full h-48 object-contain rounded-lg">
                <div class="similarity">Similarity: ${(results[i].similarity * 100).toFixed(2)}%</div>
            </div>
        `;
        similarImagesContainer.innerHTML += imageHTML;
    }
}


// Drag-and-Drop and File Upload Functionality
const uploadContainer = document.getElementById("upload-container");
const fileInput = document.getElementById("file");
const fileNameDisplay = document.getElementById("file-name");

// Drag Over Event
uploadContainer.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadContainer.classList.add("dragover");
});

// Drag Leave Event
uploadContainer.addEventListener("dragleave", () => {
    uploadContainer.classList.remove("dragover");
});

// Drop Event
uploadContainer.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadContainer.classList.remove("dragover");

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files; // Assign file to input
        displayFileName(files[0]); // Display file name
    }
});

// File Input Change Event
fileInput.addEventListener("change", (e) => {
    const files = e.target.files;
    if (files.length > 0) {
        displayFileName(files[0]); // Display file name
    }
});

// Function to Display Selected File Name
function displayFileName(file) {
    fileNameDisplay.innerText = `Selected File: ${file.name}`;
    fileNameDisplay.style.display = "block"; // Ensure visibility
}


function viewImage(imageBase64, imageName) {
    // Set the image source
    document.getElementById("view-popup-image").src = `data:image/jpeg;base64,${imageBase64}`;
    
    // Set the image name
    document.getElementById("view-popup-image-name").innerText = imageName;
    
    // Display the popup
    document.getElementById("view-popup").style.display = "flex";
}

function closeViewPopup() {
    document.getElementById("view-popup").style.display = "none";
}

function downloadImage(imageBase64, fileName) {
    let link = document.createElement("a");
    link.href = `data:image/jpeg;base64,${imageBase64}`;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

document.getElementById("uploadForm").addEventListener("submit", function (event) {
    event.preventDefault();

    let formData = new FormData(this);
    document.getElementById("results-container").style.display = "none";

    // Show loader
    document.getElementById("loader").style.display = "flex";

    fetch("/search", {
        method: "POST",
        body: formData,
    })
        .then(response => response.json())
        .then(data => {
            displayResults(data.results);
        })
        .catch(error => {
            alert("Error: " + error);
            console.error("Error during search:", error);
        })
        .finally(() => {
            // Hide loader in all cases
            document.getElementById("loader").style.display = "none";
        });
});
