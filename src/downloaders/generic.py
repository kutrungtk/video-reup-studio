"""
Generic downloader — YouTube, Facebook, Instagram, and other platforms.
Uses standard yt-dlp with cookie support.
"""
import os
import sys
import glob


def download_generic(url: str, output_dir: str, cookie_opts: dict,
                     ffmpeg_location: str, today: str, resolution: str = '1080',
                     mode: str = 'Video MP4', delay: int = 0) -> dict:
    """
    Download video from YouTube, Facebook, Instagram, etc.
    
    Args:
        url: Video/playlist URL
        output_dir: Output directory
        cookie_opts: Cookie options dict (e.g. {'cookiesfrombrowser': ('firefox',)})
        ffmpeg_location: Path to ffmpeg binary directory
        today: Date string for filename prefix
        resolution: Target resolution (360-2160)
        mode: Download mode (Video MP4, Video + Thumbnail, Audio MP3, Thumbnail Only)
        delay: Delay between requests (seconds)
    
    Returns:
        {'success': bool, 'file': str or None, 'message': str}
    """
    import yt_dlp

    has_ffmpeg = ffmpeg_location is not None

    opts = {
        'outtmpl': os.path.join(output_dir, f'{today}_%(title)s.%(ext)s'),
        'retries': 3,
        'fragment_retries': 3,
        'extractor_retries': 3,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
    }
    opts.update(cookie_opts)

    if delay > 0:
        opts['sleep_interval'] = delay
        opts['sleep_requests'] = max(1, delay - 2)

    if ffmpeg_location:
        opts['ffmpeg_location'] = ffmpeg_location

    # Format strategy based on mode
    if mode == "Video MP4":
        if has_ffmpeg:
            opts['format'] = (
                f'bestvideo[height<={resolution}]+bestaudio/'
                f'best[height<={resolution}][ext=mp4]/'
                f'best[height<={resolution}]/best'
            )
        else:
            opts['format'] = f'best[height<={resolution}][ext=mp4]/best[height<={resolution}]/best'
        opts['merge_output_format'] = 'mp4'

    elif mode == "Video + Thumbnail":
        if has_ffmpeg:
            opts['format'] = (
                f'bestvideo[height<={resolution}]+bestaudio/'
                f'best[height<={resolution}][ext=mp4]/'
                f'best[height<={resolution}]/best'
            )
        else:
            opts['format'] = f'best[height<={resolution}][ext=mp4]/best[height<={resolution}]/best'
        opts['merge_output_format'] = 'mp4'
        opts['writethumbnail'] = True
        opts['postprocessors'] = [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}]

    elif mode == "Audio MP3":
        opts['format'] = 'bestaudio/best'
        if has_ffmpeg:
            opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]

    elif mode == "Thumbnail Only":
        opts['skip_download'] = True
        opts['writethumbnail'] = True
        if has_ffmpeg:
            opts['postprocessors'] = [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}]

    # Fix Unicode filenames on Windows
    if sys.platform == 'win32':
        opts['windowsfilenames'] = True
        opts['encoding'] = 'utf-8'

    downloaded_file = None

    def progress_hook(d):
        nonlocal downloaded_file
        if d['status'] == 'finished':
            downloaded_file = d.get('filename', d.get('info_dict', {}).get('_filename', ''))

    opts['progress_hooks'] = [progress_hook]

    # Download
    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.download([url])

    # Verify
    if downloaded_file and os.path.isfile(downloaded_file):
        return {'success': True, 'file': downloaded_file, 'message': 'OK'}
    elif result == 0:
        # yt-dlp returned 0 but no file hook — check by pattern
        pattern = os.path.join(output_dir, f"{today}*")
        matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if matches:
            return {'success': True, 'file': matches[0], 'message': 'OK'}
        else:
            return {'success': False, 'file': None, 'message': 'Download OK but file not found'}
    else:
        return {'success': False, 'file': None, 'message': f'yt-dlp error code {result}'}
