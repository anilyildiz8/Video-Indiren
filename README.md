# Video Indiren

A modern, fast, and user-friendly desktop video downloader localized in Turkish. Built with a focus on simplicity and a premium app experience.

## Download

[Download the latest VideoIndiren.exe here](https://github.com/yourusername/video-indiren/releases)

Note: This is a portable standalone executable. No installation required. Just download and run.

## Features

-   Multi-Platform Support: Download videos from Reddit, YouTube, TikTok, Twitter (X), and thousands more.
-   Smart Media Merging: Automatically combines high-quality video and audio into a single MP4 file using FFmpeg.
-   Modern Desktop UI: Runs in Microsoft Edge "App Mode" for a native, windowed experience.
-   Turkish Localization: Fully translated interface ("İndir", "indirme klasörü", etc.).
-   Persistent Settings: Remembers your last used download directory.
-   Real-time Progress: Displays download percentage and current internet speed.
-   One-Click Explorer: Directly open the download folder and highlight your file upon completion.
-   Auto-Cleanup: Automatically removes temporary files if the app is closed during a download.
-   Portable: Can be compiled into a single EXE that handles its own dependencies.

## Technology Stack

-   Backend: FastAPI (Python)
-   Engine: yt-dlp
-   UI: HTML5, Vanilla CSS3 (Glassmorphism design), JavaScript (ES6+)
-   Server: Uvicorn
-   Packaging: PyInstaller
-   Dependencies: FFmpeg (Auto-downloaded if missing)

## Getting Started

### Prerequisites

-   Python 3.9+
-   (Optional) FFmpeg installed in PATH (The app will handle this automatically if missing)

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/yourusername/video-indiren.git
    cd video-indiren
    ```

2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3.  Run the application:
    ```bash
    python main.py
    ```

## Building the EXE

To create a single, portable executable:

1.  Run the provided PowerShell script:
    ```powershell
    ./build_exe.ps1
    ```
2.  Find your app in the dist/ folder.

## License

Distributed under the MIT License. See LICENSE for more information.

---
Built for a better downloading experience.
