from pydantic import BaseModel


class DownloadRequest(BaseModel):
    url: str
    download_dir: str = None
    quality: str = "best"
    audio_only: bool = False
    download_playlist: bool = False
    start_time: str | None = None
    end_time: str | None = None


class InfoRequest(BaseModel):
    url: str


class QualityRequest(BaseModel):
    quality: str


class OpenFolderRequest(BaseModel):
    file_path: str
