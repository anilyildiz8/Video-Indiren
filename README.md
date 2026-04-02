# Video Indiren

Video Indiren is a locally hosted desktop application for downloading videos seamlessly. Built with Python and modern web technologies, it features a web-based user interface that opens automatically upon launching the application. 

## How it Works

The application operates by running a lightweight local Python server (powered by FastAPI and Uvicorn). Upon startup, it automatically opens your default web browser to serve the user interface. 

Behind the scenes, the underlying downloading tasks are handled via `yt-dlp`. To ensure downloads and media processing (such as merging high-quality audio and video streams) work properly, the application will automatically manage the download and setup of FFmpeg into its internal application data folders.

## Features

- Local server backend communicating with a responsive web interface.
- Automatic backend setup of FFmpeg for media stream processing.
- Configurable settings via a locally stored configuration file (controlling the default download directory and quality preferences).
- Clean handling of downloads including resumability, cancellation, and automatic cleanup of interrupted processes.
- Bundled smoothly as a single executable for ease of use.

## Development

The project structure separates concerns into:
- **Backend**: API endpoints, settings manager, and download scripts live in the `app/` package. 
- **Frontend**: The user interface is located in the `static/` directory, built with standard HTML, Javascript, and CSS.
- **Packaging**: Build scripts like `build_exe.ps1` are included to compile the backend server, frontend UI, and python dependencies into a standalone executable using PyInstaller.

### Running from source

To run this application in a development environment, you must install the dependencies outlined in `requirements.txt`.

```bash
pip install -r requirements.txt
python main.py
```

## License

Distributed under the MIT License. See LICENSE for more information.
