let currentSavedPath = ""; // Global tracker for the last saved file
let videoDuration = 0; // Total video length in seconds
let ffmpegReady = false;
let setupPollHandle = null;
let setupRetryPending = false;

// Add listeners to URL input
document.addEventListener("DOMContentLoaded", () => {
    const urlInput = document.getElementById('urlInput');
    const retrySetupBtn = document.getElementById('retrySetupBtn');
    retrySetupBtn.addEventListener('click', retrySetup);

    // Auto-fetch info when user clicks away
    urlInput.addEventListener('blur', async () => {
        let url = urlInput.value.trim();
        if (!url) return;

        const titleLabel = document.getElementById('videoTitleLabel');
        const durationLabel = document.getElementById('videoDurationLabel');
        const trimmingSection = document.getElementById('trimmingSection');
        const playlistToggle = document.getElementById('playlistToggle');

        if (!playlistToggle.checked) {
            trimmingSection.style.display = 'flex';
        } else {
            trimmingSection.style.display = 'none';
        }

        titleLabel.innerText = "Bilgi getiriliyor...";

        try {
            const res = await fetch('/api/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            });
            const data = await res.json();

            if (data.status === 'success') {
                videoDuration = data.duration;
                titleLabel.innerText = data.title || "Bilinmeyen Başlık";
                durationLabel.innerText = formatTimeLimit(videoDuration);
                setupSliders();
            } else {
                titleLabel.innerText = "Video bilgisi alınamadı.";
            }
        } catch (e) {
            titleLabel.innerText = "Hata oluştu.";
        }
    });

    // Hide trimming section if downloading playlist
    const playlistToggle = document.getElementById('playlistToggle');
    const trimmingSection = document.getElementById('trimmingSection');

    playlistToggle.addEventListener('change', () => {
        if (playlistToggle.checked) {
            trimmingSection.style.display = 'none';
        } else if (urlInput.value.trim() && videoDuration > 0) {
            trimmingSection.style.display = 'flex';
        }
    });

    setupSliderEvents();
});

function setDownloadAvailability(enabled) {
    ffmpegReady = enabled;
    document.getElementById('downloadBtn').disabled = !enabled;
}

function renderSetupState(data) {
    const overlay = document.getElementById('setupOverlay');
    const setupMessage = document.getElementById('setupMessage');
    const setupPercent = document.getElementById('setupPercent');
    const setupProgressBar = document.getElementById('setupProgressBar');
    const retrySetupBtn = document.getElementById('retrySetupBtn');

    const status = data.status || 'pending';
    const progress = Math.max(0, Math.min(100, Number(data.progress || 0)));
    const ffmpegAvailable = Boolean(data.ffmpeg_available);

    setupMessage.textContent = data.message || 'FFmpeg hazirlaniyor.';
    setupPercent.textContent = `${progress}%`;
    setupProgressBar.style.width = `${progress}%`;

    if (status === 'failed') {
        overlay.classList.remove('hidden');
        retrySetupBtn.classList.remove('hidden');
        retrySetupBtn.disabled = setupRetryPending;
        setDownloadAvailability(false);
        return;
    }

    retrySetupBtn.classList.add('hidden');

    if (ffmpegAvailable || status === 'complete') {
        overlay.classList.add('hidden');
        setDownloadAvailability(true);
        return;
    }

    overlay.classList.remove('hidden');
    setDownloadAvailability(false);
}

async function pollSetupStatus() {
    try {
        const response = await fetch('/api/setup_status');
        const data = await response.json();
        renderSetupState(data);

        if ((data.status === 'complete' || data.ffmpeg_available) && setupPollHandle) {
            clearInterval(setupPollHandle);
            setupPollHandle = null;
        }
    } catch (e) {
        console.error("Setup status poll failed", e);
    }
}

async function retrySetup() {
    const retrySetupBtn = document.getElementById('retrySetupBtn');
    setupRetryPending = true;
    retrySetupBtn.disabled = true;
    retrySetupBtn.textContent = 'Tekrar deneniyor...';

    try {
        await fetch('/api/retry_setup', { method: 'POST' });
        if (!setupPollHandle) {
            setupPollHandle = setInterval(pollSetupStatus, 1000);
        }
        await pollSetupStatus();
    } catch (e) {
        console.error("Retry setup failed", e);
    } finally {
        setupRetryPending = false;
        retrySetupBtn.disabled = false;
        retrySetupBtn.textContent = 'Tekrar Dene';
    }
}

// Time formatting helpers
function formatTimeLimit(seconds) {
    if (!seconds) return "00:00:00";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function parseTimeInput(timeStr) {
    if (!timeStr) return 0;
    const parts = timeStr.split(':');
    if (parts.length === 3) {
        return parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
    } else if (parts.length === 2) {
        return parseInt(parts[0]) * 60 + parseInt(parts[1]);
    } else {
        return parseInt(timeStr) || 0;
    }
}

// Slider logic
function setupSliders() {
    const minSlider = document.getElementById('rangeMin');
    const maxSlider = document.getElementById('rangeMax');
    const startInput = document.getElementById('startTimeInput');
    const endInput = document.getElementById('endTimeInput');

    minSlider.max = videoDuration;
    maxSlider.max = videoDuration;

    minSlider.value = 0;
    maxSlider.value = videoDuration;

    startInput.value = formatTimeLimit(0);
    endInput.value = formatTimeLimit(videoDuration);

    updateSliderTrack();
}

function setupSliderEvents() {
    const minSlider = document.getElementById('rangeMin');
    const maxSlider = document.getElementById('rangeMax');
    const startInput = document.getElementById('startTimeInput');
    const endInput = document.getElementById('endTimeInput');

    minSlider.addEventListener('input', () => {
        let minVal = parseInt(minSlider.value);
        let maxVal = parseInt(maxSlider.value);
        if (minVal > maxVal - 1) { // Min 1 sec gap
            minSlider.value = maxVal - 1;
            minVal = maxVal - 1;
        }
        startInput.value = formatTimeLimit(minVal);
        updateSliderTrack();
    });

    maxSlider.addEventListener('input', () => {
        let minVal = parseInt(minSlider.value);
        let maxVal = parseInt(maxSlider.value);
        if (maxVal < minVal + 1) { // Min 1 sec gap
            maxSlider.value = minVal + 1;
            maxVal = minVal + 1;
        }
        endInput.value = formatTimeLimit(maxVal);
        updateSliderTrack();
    });

    // Update sliders when text inputs are manually changed
    startInput.addEventListener('change', () => {
        let sec = parseTimeInput(startInput.value);
        if (sec > parseInt(maxSlider.value)) sec = parseInt(maxSlider.value) - 1;
        if (sec < 0) sec = 0;
        minSlider.value = sec;
        startInput.value = formatTimeLimit(sec);
        updateSliderTrack();
    });

    endInput.addEventListener('change', () => {
        let sec = parseTimeInput(endInput.value);
        if (sec < parseInt(minSlider.value)) sec = parseInt(minSlider.value) + 1;
        if (sec > videoDuration) sec = videoDuration;
        maxSlider.value = sec;
        endInput.value = formatTimeLimit(sec);
        updateSliderTrack();
    });
}

function updateSliderTrack() {
    const minSlider = document.getElementById('rangeMin');
    const maxSlider = document.getElementById('rangeMax');
    const track = document.getElementById('sliderTrack');

    if (videoDuration <= 0) return;

    let minPercent = (minSlider.value / videoDuration) * 100;
    let maxPercent = (maxSlider.value / videoDuration) * 100;

    track.style.background = `linear-gradient(to right, rgba(255,255,255,0.1) ${minPercent}%, #a855f7 ${minPercent}%, #6366f1 ${maxPercent}%, rgba(255,255,255,0.1) ${maxPercent}%)`;
}

async function startDownload() {
    if (!ffmpegReady) {
        const status = document.getElementById('statusMessage');
        status.textContent = "Ilk kurulum tamamlanmadan indirme baslatilamaz.";
        status.className = "status error";
        return;
    }

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
    const startTimeInput = document.getElementById('startTimeInput');
    const endTimeInput = document.getElementById('endTimeInput');

    const url = input.value.trim();
    const downloadDir = dirInput.value.trim();
    const quality = qualitySelect.value;
    const audio_only = audioToggle.checked;
    const download_playlist = playlistToggle.checked;
    const start_time = startTimeInput.value.trim();
    const end_time = endTimeInput.value.trim();

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
    startTimeInput.disabled = true;
    endTimeInput.disabled = true;
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
            } else if (data.status === 'trimming') {
                downloadSpeed.innerText = "Kesiliyor...";
                progressInfo.innerText = "Video kesiliyor...";
                progressBar.style.width = "100%";
            }
        } catch (e) {
            console.error("Progress poll failed", e);
        }
    }, 800);

    try {
        let final_start = null;
        let final_end = null;

        // Only send trim parameters if the user actually modified the sliders
        // to be something other than the full video length.
        if (document.getElementById('trimmingSection').style.display !== 'none' && videoDuration > 0) {
            const currentStart = parseTimeInput(start_time);
            const currentEnd = parseTimeInput(end_time);

            if (currentStart > 0 || currentEnd < videoDuration) {
                final_start = start_time;
                final_end = end_time;
            }
        }

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
                download_playlist: download_playlist,
                start_time: final_start,
                end_time: final_end
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
            // FastAPI validation errors return detail as an array of objects
            let errorMsg = "İndirme başarısız";
            if (data.detail) {
                if (typeof data.detail === 'string') {
                    errorMsg = data.detail;
                } else if (Array.isArray(data.detail)) {
                    errorMsg = data.detail.map(e => e.msg || JSON.stringify(e)).join(', ');
                }
            }
            throw new Error(errorMsg);
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
        startTimeInput.disabled = false;
        endTimeInput.disabled = false;
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
        await pollSetupStatus();
        if (!setupPollHandle && !ffmpegReady) {
            setupPollHandle = setInterval(pollSetupStatus, 1000);
        }

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

window.addEventListener('beforeunload', () => {
    try {
        navigator.sendBeacon('/api/shutdown');
    } catch (e) {
        console.error("Shutdown beacon failed", e);
    }
});

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
