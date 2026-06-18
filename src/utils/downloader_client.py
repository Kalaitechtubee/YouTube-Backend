import time
import requests
from typing import Callable, Optional

class DownloaderClient:
    @staticmethod
    def download_file(
        url: str,
        destination_path: str,
        progress_callback: Optional[Callable[[int, int, float, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        chunk_size: int = 1024 * 1024, # 1MB chunks
        max_retries: int = 3,
        timeout: int = 20
    ) -> None:
        """
        Downloads a file from url to destination_path.
        Calculates instantaneous speeds and handles cancellation/retries.
        """
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Referer': 'https://www.youtube.com/',
            'Origin': 'https://www.youtube.com'
        })

        for attempt in range(max_retries):
            if is_cancelled and is_cancelled():
                raise InterruptedError("Download cancelled by user.")

            try:
                with session.get(url, stream=True, timeout=timeout) as response:
                    response.raise_for_status()
                    total_bytes = int(response.headers.get('content-length', 0))
                    downloaded_bytes = 0
                    
                    # Track window metrics for speed calculation
                    start_time = time.time()
                    last_time = start_time
                    last_downloaded = 0
                    speeds = []

                    with open(destination_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if is_cancelled and is_cancelled():
                                raise InterruptedError("Download cancelled by user.")
                            
                            if chunk:
                                f.write(chunk)
                                downloaded_bytes += len(chunk)
                                
                                # Speed calculation logic every 0.5s or so
                                current_time = time.time()
                                time_diff = current_time - last_time
                                if time_diff >= 0.5:
                                    bytes_diff = downloaded_bytes - last_downloaded
                                    # MB/s calculation
                                    current_speed = (bytes_diff / (1024 * 1024)) / time_diff
                                    speeds.append(current_speed)
                                    # Keep last 5 speed readings
                                    if len(speeds) > 5:
                                        speeds.pop(0)
                                    
                                    avg_speed = sum(speeds) / len(speeds)
                                    
                                    # ETA calculation
                                    if avg_speed > 0 and total_bytes > 0:
                                        remaining_bytes = total_bytes - downloaded_bytes
                                        eta_seconds = int(remaining_bytes / (avg_speed * 1024 * 1024))
                                        
                                        # Format ETA
                                        hours = eta_seconds // 3600
                                        minutes = (eta_seconds % 3600) // 60
                                        seconds = eta_seconds % 60
                                        eta_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                                    else:
                                        eta_str = "00:00:00"

                                    speed_str = f"{avg_speed:.2f} MB/s"
                                    
                                    if progress_callback:
                                        progress_callback(downloaded_bytes, total_bytes, avg_speed, eta_str)
                                    
                                    last_time = current_time
                                    last_downloaded = downloaded_bytes

                    # Final progress callback invocation
                    if progress_callback:
                        progress_callback(downloaded_bytes, total_bytes, 0.0, "00:00:00")
                return # Success, escape retry loop
            except (requests.RequestException, IOError) as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(2)
