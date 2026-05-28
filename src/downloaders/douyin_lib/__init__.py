"""
Douyin signature utilities (from jiji262/douyin-downloader).
- XBogus: URL signing
- ABogus: Advanced anti-bot signature (requires gmssl)
"""
from .xbogus import XBogus

try:
    from .abogus import ABogus, BrowserFingerprintGenerator
except ImportError:
    ABogus = None
    BrowserFingerprintGenerator = None

__all__ = ['XBogus', 'ABogus', 'BrowserFingerprintGenerator']
