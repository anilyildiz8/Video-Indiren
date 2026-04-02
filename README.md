# Video Indiren

Video Indiren is a locally hosted desktop application for downloading videos seamlessly. Built with Python  it features a web-based user interface.

## How it Works

The application operates by running a lightweight local Python server (powered by FastAPI and Uvicorn). Upon startup, it automatically opens your default web browser to serve the user interface. 

The underlying downloading tasks are handled via `yt-dlp`.

## License

Distributed under the MIT License. See LICENSE for more information.
