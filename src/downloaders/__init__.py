"""
Platform-specific downloaders for Batch Download.
Each module exports a download_one(url, opts, context) function.
"""
from .tiktok import download_tiktok
from .douyin import download_douyin
from .generic import download_generic

__all__ = ['download_tiktok', 'download_douyin', 'download_generic']
