let currentSavedPath = ""; // Global tracker for the last saved file

async function startDownload() {
    const input = document.getElementById('urlInput');
    const btn = document.getElementById('downloadBtn');
    const btnText = document.getElementById('btnText');
    const btnLoader = document.getElementById('btnLoader');
    const status = document.getElementById('statusMessage');
    const resultCard = document.getElementById('resultCard');
    const filePath = document.getElementById('filePath');

    const dirInput = document.getElementById('dirInput');
    const url = input.value.trim();
    const downloadDir = dirInput.value.trim();

    if (!url) {
        status.textContent = "Lütfen geçerli bir URL girin";
        status.className = "status error";
        return;
    }

    // Reset state
    status.textContent = "";
    resultCard.classList.add('hidden');
    input.disabled = true;
    dirInput.disabled = true;
    btn.disabled = true;
    btnText.style.display = 'none';
    btnLoader.style.display = 'block';

    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressPercent = document.getElementById('progressPercent');
    const downloadSpeed = document.getElementById('downloadSpeed');
    const progressInfo = document.getElementById('progressInfo');

    progressContainer.classList.remove('hidden');
    progressPercent.innerText = "0%";
    downloadSpeed.innerText = "Bağlanılıyor...";
    progressInfo.innerText = "0.0MB / 0.0MB";
    progressBar.style.width = "0%";

    // Polling function
    const pollInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/progress');
            const data = await res.json();
            if (data.status === 'downloading') {
                progressPercent.innerText = data.percent;
                downloadSpeed.innerText = data.speed;
                progressInfo.innerText = data.size_info || "";
                progressBar.style.width = data.percent;
            }
        } catch (e) {
            console.error("Progress poll failed", e);
        }
    }, 800);

    try {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                url: url,
                download_dir: downloadDir
            }),
        });

        const data = await response.json();

        if (response.ok) {
            status.textContent = "İndirme başarılı!";
            status.className = "status success";
            filePath.textContent = "Kaydedildi: " + data.filename;
            currentSavedPath = data.full_path; // Store the full absolute path
            resultCard.classList.remove('hidden');
            input.value = ""; // Clear input on success
        } else {
            throw new Error(data.detail || "İndirme başarısız");
        }
    } catch (error) {
        status.textContent = error.message;
        status.className = "status error";
    } finally {
        clearInterval(pollInterval);
        progressContainer.classList.add('hidden');
        input.disabled = false;
        btn.disabled = false;
        btnText.style.display = 'block';
        btnLoader.style.display = 'none';

        // Re-enable dir field if needed, but it's readonly anyway
    }
}

async function browseFolder() {
    try {
        const response = await fetch('/api/select_folder');
        const data = await response.json();
        if (data.path) {
            document.getElementById('dirInput').value = data.path;
        }
    } catch (e) {
        console.error("Failed to open folder picker", e);
    }
}

// Fetch default config on load
window.addEventListener('load', async () => {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        if (data.default_dir) {
            document.getElementById('dirInput').value = data.default_dir;
        }
    } catch (e) {
        console.error("Failed to fetch config", e);
    }
});

// Heartbeat system to keep server alive
setInterval(async () => {
    try {
        await fetch('/api/heartbeat');
    } catch (e) {
        console.error("Heartbeat failed", e);
    }
}, 3000); // 3s pulse for 10s shutdown

async function openResultFolder() {
    if (!currentSavedPath) return;

    try {
        await fetch('/api/open_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: currentSavedPath })
        });
    } catch (e) {
        console.error("Failed to open folder", e);
    }
}
