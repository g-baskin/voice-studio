"""Run the pinned downloader with a hard per-file disk limit (no shell or user config)."""

import resource
import runpy

if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_FSIZE, (250 * 1024**2, 250 * 1024**2))
    runpy.run_module("yt_dlp", run_name="__main__")
