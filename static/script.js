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
    const qualitySelect = document.getElementById('qualitySelect');
    const audioToggle = document.getElementById('audioOnlyToggle');
    const playlistToggle = document.getElementById('playlistToggle');

    const url = input.value.trim();
    const downloadDir = dirInput.value.trim();
    const quality = qualitySelect.value;
    const audio_only = audioToggle.checked;
    const download_playlist = playlistToggle.checked;

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
    audioToggle.disabled = true;
    playlistToggle.disabled = true;
    btn.disabled = true;
    btnText.style.display = 'none';
    btnLoader.style.display = 'block';

    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressPercent = document.getElementById('progressPercent');
    const playlistCounter = document.getElementById('playlistCounter');
    const downloadSpeed = document.getElementById('downloadSpeed');
    const progressInfo = document.getElementById('progressInfo');

    progressContainer.classList.remove('hidden');
    progressPercent.innerText = "0%";
    playlistCounter.innerText = "";
    playlistCounter.style.display = download_playlist ? 'inline-block' : 'none';
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

                // Show counter only if info is available to avoid "hollow circle"
                if (data.playlist_info) {
                    playlistCounter.innerText = data.playlist_info;
                    playlistCounter.style.display = 'inline-block';
                } else {
                    playlistCounter.style.display = 'none';
                }

                downloadSpeed.innerText = data.speed;
                progressInfo.innerText = data.size_info || "";
                progressBar.style.width = data.percent;
            } else if (data.status === 'merging') {
                downloadSpeed.innerText = "Birleştiriliyor...";
                progressInfo.innerText = "Dosya birleştiriliyor (FFmpeg)...";
                progressBar.style.width = "100%";
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
                download_dir: downloadDir,
                quality: quality,
                audio_only: audio_only,
                download_playlist: download_playlist
            }),
        });

        const data = await response.json();

        if (response.ok) {
            if (data.status === "cancelled") {
                status.textContent = "İndirme iptal edildi";
                status.className = "status error";
                return;
            }
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
        const cancelBtn = document.getElementById('cancelBtn');
        cancelBtn.disabled = false;
        cancelBtn.innerText = "İptal Et";

        clearInterval(pollInterval);
        progressContainer.classList.add('hidden');
        input.disabled = false;
        dirInput.disabled = false;
        audioToggle.disabled = false;
        playlistToggle.disabled = false;
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

async function cancelDownload() {
    try {
        const btn = document.getElementById('cancelBtn');
        btn.disabled = true;
        btn.innerText = "İptal ediliyor...";
        await fetch('/api/cancel', { method: 'POST' });
    } catch (e) {
        console.error("Cancel failed", e);
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
        if (data.quality) {
            document.getElementById('qualitySelect').value = data.quality;
        }
    } catch (e) {
        console.error("Failed to fetch config", e);
    }
});

// Quality change listener
document.getElementById('qualitySelect').addEventListener('change', async (e) => {
    try {
        await fetch('/api/set_quality', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quality: e.target.value })
        });
    } catch (e) {
        console.error("Failed to save quality", e);
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
