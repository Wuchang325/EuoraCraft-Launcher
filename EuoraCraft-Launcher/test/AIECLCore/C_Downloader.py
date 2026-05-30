from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Tuple, Optional, Union, Any, Dict
from pathlib import Path
import threading
import requests
import time
import sys
import shutil
import random
from ..logger import get_logger

logger = get_logger("downloader")

class DownloadTask:
    """下载任务数据类，用于精细控制下载过程"""
    def __init__(self, urls: Union[str, List[str]], save_path: str, 
                 task_type: str = "resource", size: int = 0, 
                 priority: int = 0, retries: int = 3):
        """
        初始化下载任务
        
        Args:
            urls: 下载链接（支持多个备用链接）
            save_path: 保存路径
            task_type: 任务类型 ('client', 'library', 'asset', 'resource')
            size: 文件大小（字节），0 表示未知
            priority: 优先级，数字越小优先级越高（0=最高）
            retries: 最大重试次数
        """
        self.urls = [urls] if isinstance(urls, str) else urls
        self.save_path = Path(save_path)
        self.task_type = task_type
        self.size = size
        self.priority = priority
        self.max_retries = retries
        self.status = "pending"  # pending, downloading, completed, failed
        self.progress = 0  # 0-100
        self.current_url_index = 0
        self.error_msg = ""
        self.downloaded_size = 0
        
    def __repr__(self):
        return f"<DownloadTask {self.task_type}: {self.save_path.name}>"


class ResourceDownloader:
    """
    多线程资源下载器 - 专为 Minecraft 资源优化
    
    特性：
    - 并发下载：支持最多 64 线程并发下载小文件
    - 分块下载：对 >5MB 的大文件自动使用多线程分块下载
    - 断点续传：支持自动断点续传
    - 优先级队列：可设置任务优先级（Client > Library > Asset）
    - 实时进度：支持总体进度和单文件进度回调
    - 速度统计：实时计算下载速度
    - 优雅停止：支持随时停止所有下载任务
    """
    
    def __init__(self, max_workers: int = 16, chunk_size: int = 8192,
                 enable_progress_bar: bool = True, use_multi_part: bool = True):
        """
        初始化资源下载器
        
        Args:
            max_workers: 最大并发线程数（建议 8-32）
            chunk_size: 下载块大小（默认 8KB）
            enable_progress_bar: 是否启用命令行进度条
            use_multi_part: 是否对大文件启用多线程分块下载
        """
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self.enable_progress_bar = enable_progress_bar
        self.use_multi_part = use_multi_part
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Euora Craft Launcher/1.0",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        })
        
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        
        # 回调函数（可由外部设置）
        self.on_task_progress: Optional[Callable[[DownloadTask, int, int], None]] = None
        self.on_overall_progress: Optional[Callable[[int, int, int, int], None]] = None
        self.on_task_complete: Optional[Callable[[DownloadTask, bool], None]] = None
        self.on_log: Optional[Callable[[str, str], None]] = None
        
        # 统计信息
        self.stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_bytes": 0,
            "downloaded_bytes": 0,
            "start_time": 0,
            "speed": 0.0
        }

    def _log(self, message: str, level: str = "info"):
        """内部日志输出"""
        if self.on_log:
            self.on_log(message, level)
        else:
            getattr(logger, level, logger.info)(message)

    def _get_file_size(self, url: str) -> Optional[int]:
        """获取远程文件大小"""
        try:
            resp = self.session.head(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                return int(resp.headers.get("Content-Length", 0))
        except Exception as e:
            logger.debug(f"获取文件大小失败 {url}: {e}")
        return None

    def _download_single_thread(self, task: DownloadTask) -> bool:
        """单线程流式下载（适合小文件 < 5MB）"""
        save_path = task.save_path
        temp_suffix = f".tmp_{threading.current_thread().ident}_{random.randint(1000, 9999)}"
        temp_path = save_path.with_suffix(save_path.suffix + temp_suffix)
        
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            for url in task.urls[task.current_url_index:]:
                try:
                    headers = {}
                    if task.downloaded_size > 0 and temp_path.exists():
                        headers["Range"] = f"bytes={task.downloaded_size}-"
                    
                    with self.session.get(url, headers=headers, stream=True, timeout=30) as resp:
                        if resp.status_code not in [200, 206]:
                            raise Exception(f"HTTP {resp.status_code}")
                        
                        mode = "ab" if task.downloaded_size > 0 else "wb"
                        with open(temp_path, mode) as f:
                            for chunk in resp.iter_content(chunk_size=self.chunk_size):
                                if self._stop_event.is_set():
                                    return False
                                if chunk:
                                    f.write(chunk)
                                    f.flush()
                                    task.downloaded_size += len(chunk)
                                    if task.size > 0:
                                        task.progress = int(task.downloaded_size / task.size * 100)
                                    
                                    if self.on_task_progress and task.size > 0:
                                        self.on_task_progress(task, task.downloaded_size, task.size)
                        
                        # 验证文件大小
                        if task.size > 0 and temp_path.stat().st_size != task.size:
                            raise Exception(f"大小不匹配")
                        
                        # 移动到最终位置（带重试机制）
                        for _ in range(5):
                            try:
                                if save_path.exists():
                                    save_path.unlink(missing_ok=True)
                                temp_path.rename(save_path)
                                break
                            except PermissionError:
                                time.sleep(0.5)
                        else:
                            raise Exception("无法重命名临时文件（被占用）")
                        
                        task.status = "completed"
                        return True
                        
                except Exception as e:
                    task.current_url_index += 1
                    task.error_msg = str(e)
                    logger.debug(f"链接失败，尝试备用: {url} - {e}")
                    continue
                    
            task.status = "failed"
            return False
            
        except Exception as e:
            task.status = "failed"
            task.error_msg = str(e)
            logger.error(f"下载异常 {save_path.name}: {e}")
            return False
        finally:
            if temp_path.exists() and task.status != "completed":
                temp_path.unlink(missing_ok=True)

    def _download_multi_part(self, task: DownloadTask, num_parts: int = 4) -> bool:
        """
        多线程分块下载（适合大文件 > 5MB）
        将文件分成多个块，使用多个线程同时下载
        """
        if not task.size or task.size < 5 * 1024 * 1024:  # 小于 5MB 不用分块
            return self._download_single_thread(task)
        
        save_path = task.save_path
        temp_dir = save_path.parent / f".tmp_parts_{save_path.stem}_{random.randint(1000, 9999)}"
        
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            temp_dir.mkdir(exist_ok=True)
            
            part_size = task.size // num_parts
            parts_info = []  # (part_idx, start, end, completed)
            
            def download_part(part_idx: int, start: int, end: int) -> bool:
                """下载单个分块"""
                part_file = temp_dir / f"part_{part_idx}"
                
                # 检查是否已存在完整分块
                if part_file.exists():
                    existing_size = part_file.stat().st_size
                    if existing_size == (end - start + 1):
                        return True
                    elif existing_size < (end - start + 1):
                        start += existing_size  # 续传
                
                for url in task.urls:
                    try:
                        headers = {"Range": f"bytes={start}-{end}"}
                        with self.session.get(url, headers=headers, stream=True, timeout=60) as resp:
                            if resp.status_code == 206:
                                mode = "ab" if part_file.exists() else "wb"
                                with open(part_file, mode) as f:
                                    for chunk in resp.iter_content(chunk_size=self.chunk_size):
                                        if self._stop_event.is_set():
                                            return False
                                        if chunk:
                                            f.write(chunk)
                                            with self.lock:
                                                self.stats["downloaded_bytes"] += len(chunk)
                                return True
                    except Exception as e:
                        continue
                return False
            
            # 使用线程池下载各分块
            with ThreadPoolExecutor(max_workers=num_parts) as executor:
                futures = []
                for i in range(num_parts):
                    start = i * part_size
                    end = start + part_size - 1 if i < num_parts - 1 else task.size - 1
                    future = executor.submit(download_part, i, start, end)
                    futures.append((i, future))
                
                completed_parts = 0
                for idx, future in futures:
                    success = future.result()
                    if not success:
                        task.status = "failed"
                        return False
                    completed_parts += 1
                    task.progress = int(completed_parts / num_parts * 100)
                    if self.on_task_progress:
                        self.on_task_progress(task, completed_parts, num_parts)
            
            # 合并分块
            with open(save_path, "wb") as outfile:
                for i in range(num_parts):
                    part_file = temp_dir / f"part_{i}"
                    if part_file.exists():
                        with open(part_file, "rb") as infile:
                            shutil.copyfileobj(infile, outfile)
                        part_file.unlink()
            
            temp_dir.rmdir()
            task.status = "completed"
            return True
            
        except Exception as e:
            task.status = "failed"
            task.error_msg = str(e)
            logger.error(f"分块下载失败 {save_path.name}: {e}")
            return False
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _download_worker(self, task: DownloadTask) -> bool:
        """下载工作线程"""
        if self._stop_event.is_set():
            return False
        
        task.status = "downloading"
        
        # 根据文件大小和类型选择下载策略
        is_large_file = task.size and task.size > 5 * 1024 * 1024
        if is_large_file and self.use_multi_part and task.task_type in ["client", "library"]:
            result = self._download_multi_part(task, num_parts=4)
        else:
            result = self._download_single_thread(task)
        
        with self.lock:
            if result:
                self.stats["completed_tasks"] += 1
            else:
                self.stats["failed_tasks"] += 1
        
        if self.on_task_complete:
            self.on_task_complete(task, result)
        
        return result

    def download_resources(self, tasks: List[DownloadTask], 
                          max_workers: Optional[int] = None,
                          priority_sort: bool = True) -> Tuple[int, int]:
        """
        批量下载资源（主要入口）
        
        Args:
            tasks: 下载任务列表
            max_workers: 并发线程数，None 则使用初始化值
            priority_sort: 是否按优先级排序（数字小的优先）
        
        Returns:
            (成功数, 失败数)
        """
        if not tasks:
            return 0, 0
        
        self._stop_event.clear()
        self.stats = {
            "total_tasks": len(tasks),
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_bytes": sum(t.size for t in tasks if t.size > 0),
            "downloaded_bytes": 0,
            "start_time": time.time(),
            "speed": 0.0
        }
        
        workers = max_workers or self.max_workers
        workers = min(workers, len(tasks), 64)  # 最多 64 线程
        
        if priority_sort:
            tasks.sort(key=lambda x: x.priority)
        
        self._log(f"开始下载 {len(tasks)} 个文件，使用 {workers} 线程，"
                 f"总大小 {self.stats['total_bytes']/1024/1024:.1f} MB")
        
        completed = 0
        failed = 0
        last_progress_update = 0
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_task = {executor.submit(self._download_worker, task): task for task in tasks}
            
            for future in as_completed(future_to_task):
                if self._stop_event.is_set():
                    break
                    
                task = future_to_task[future]
                try:
                    success = future.result()
                    if success:
                        completed += 1
                    else:
                        failed += 1
                        self._log(f"下载失败: {task.save_path.name} - {task.error_msg}", "warning")
                    
                    # 更新总体进度（每秒最多更新 10 次，避免频繁回调）
                    current_time = time.time()
                    if self.on_overall_progress and (current_time - last_progress_update > 0.1 or 
                                                     completed + failed == len(tasks)):
                        elapsed = current_time - self.stats["start_time"]
                        if elapsed > 0:
                            self.stats["speed"] = self.stats["downloaded_bytes"] / elapsed
                        self.on_overall_progress(
                            self.stats["completed_tasks"],
                            self.stats["total_tasks"],
                            self.stats["downloaded_bytes"],
                            self.stats["total_bytes"]
                        )
                        last_progress_update = current_time
                        
                except Exception as e:
                    failed += 1
                    self._log(f"任务异常: {task.save_path.name} - {e}", "error")
        
        elapsed = time.time() - self.stats["start_time"]
        speed_mb = (self.stats["downloaded_bytes"] / 1024 / 1024) / elapsed if elapsed > 0 else 0
        self._log(f"下载完成: 成功 {completed}/{len(tasks)}, 失败 {failed}, "
                 f"用时 {elapsed:.1f}s, 平均速度 {speed_mb:.2f} MB/s")
        
        return completed, failed

    def stop_all(self):
        """停止所有下载任务"""
        self._stop_event.set()
        self._log("正在停止所有下载任务...", "warning")

    def create_tasks_from_checker(self, download_list: List[Tuple[Union[str, List[str]], str]], 
                                  task_type: str = "resource") -> List[DownloadTask]:
        """
        从 FilesChecker 返回的列表创建任务（便捷方法）
        
        Args:
            download_list: [(urls, save_path), ...]
            task_type: 任务类型
        
        Returns:
            DownloadTask 列表
        """
        tasks = []
        for urls, save_path in download_list:
            # 自动判断任务类型和优先级
            path_lower = str(save_path).lower()
            if "client" in path_lower and path_lower.endswith(".jar"):
                detected_type = "client"
                priority = 0
            elif "libraries" in path_lower:
                detected_type = "library"
                priority = 1
            else:
                detected_type = task_type
                priority = 2
            
            task = DownloadTask(
                urls=urls,
                save_path=save_path,
                task_type=detected_type,
                priority=priority
            )
            
            # 尝试获取文件大小（从第一个可用 URL）
            for url in task.urls:
                size = self._get_file_size(url)
                if size:
                    task.size = size
                    break
            
            tasks.append(task)
        
        return tasks


# ==================== 原有 Downloader 类（保持向后兼容） ====================

class Downloader:
    """下载器类，支持多线程下载、断点续传和防文件锁冲突"""
    
    def __init__(self, max_retries: int = 3, chunk_size: int = 8192, enable_progress_bar: bool = True):
        self.download_status = True
        self.__download_total: List[Tuple[Any, str]] = []
        self.__download_done: List[str] = []
        self.output_progress = self.__default_output_progress
        self.output_log = self.__default_output_log
        self.lock = threading.Lock()
        self.max_retries = max_retries
        self.chunk_size = chunk_size
        self.enable_progress_bar = enable_progress_bar
        self._terminal_width = self._get_terminal_width()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Euora Craft Launcher"
        })

    def _get_terminal_width(self) -> int:
        try:
            return shutil.get_terminal_size().columns
        except:
            return 80

    def _draw_progress_bar(self, current: int, total: int, width: int = 40) -> str:
        if total == 0:
            return "[等待中...]"
        
        percent = current / total
        filled = int(width * percent)
        empty = width - filled
        
        bar_color = "\033[32m" if percent < 0.9 else "\033[33m"
        reset_color = "\033[0m"
        bold = "\033[1m"
        
        bar = "█" * filled + "░" * empty
        percent_str = f"{percent * 100:.1f}%"
        
        return f"{bold}[{bar_color}{bar}{reset_color}{bold}] {percent_str} ({current}/{total}){reset_color}"

    def __default_output_progress(self, total_files: list, downloaded_files: list):
        with self.lock:
            total = len(total_files)
            done = len(downloaded_files)
            
            if not self.enable_progress_bar:
                if total > 0 and (done == total or done % max(1, total // 10) == 0):
                    logger.info(f"下载进度: {done}/{total} ({done/total*100:.1f}%)")
                return
            
            if total > 0:
                bar = self._draw_progress_bar(done, total)
                sys.stdout.write(f"\r\033[K{bar}")
                sys.stdout.flush()
                
                if done >= total:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    logger.info(f"下载完成: {done}/{total} 文件")

    @staticmethod
    def __default_output_log(log: str):
        logger.info(log)

    def set_output_progress(self, output_function: Callable[[list, list], None]) -> None:
        def safe_output(total: list, done: list):
            with self.lock:
                output_function(total, done)
        self.output_progress = safe_output

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def set_download_status(self, set_status: bool) -> None:
        with self.lock:
            self.download_status = set_status

    def __get_file_size(self, url: str) -> Optional[int]:
        for attempt in range(self.max_retries):
            try:
                response = self.session.head(url, timeout=10, allow_redirects=True)
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                if content_length:
                    return int(content_length)

                response = self.session.get(url, stream=True, timeout=10)
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                if content_length:
                    return int(content_length)
                return 0
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    logger.debug(f"获取文件大小失败 {url}: {str(e)}")
                    return None
                time.sleep(1)
        return None

    def __download_stream(self, url: str, file_path: Path, start_byte: int = 0) -> bool:
        """流式下载文件，确保正确关闭句柄"""
        for attempt in range(self.max_retries):
            try:
                headers = {}
                if start_byte > 0:
                    headers["Range"] = f"bytes={start_byte}-"

                file_path.parent.mkdir(parents=True, exist_ok=True)

                with self.session.get(url, headers=headers, stream=True, timeout=30) as response:
                    response.raise_for_status()
                    if start_byte > 0 and response.status_code != 206:
                        return False

                    mode = "ab" if start_byte > 0 else "wb"
                    with open(file_path, mode) as f:
                        for chunk in response.iter_content(chunk_size=self.chunk_size):
                            with self.lock:
                                if not self.download_status:
                                    return False
                            if chunk:
                                f.write(chunk)
                                f.flush()
                
                time.sleep(0.1)
                return True

            except requests.exceptions.RequestException:
                if attempt == self.max_retries - 1:
                    return False
                time.sleep(1)
            except IOError as e:
                logger.error(f"文件写入失败 {file_path}: {str(e)}")
                return False
        return False

    def __safe_rename(self, temp_path: Path, target_path: Path, max_attempts: int = 10) -> bool:
        """安全重命名文件，处理 Windows 文件锁冲突"""
        for attempt in range(max_attempts):
            try:
                if target_path.exists():
                    target_path.unlink(missing_ok=True)
                
                temp_path.rename(target_path)
                return True
            except PermissionError as e:
                if attempt < max_attempts - 1:
                    wait_time = 0.5 + (attempt * 0.2) + (random.random() * 0.5)
                    logger.debug(f"文件被锁定，等待 {wait_time:.1f}s 后重试: {temp_path.name}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"无法重命名文件（被锁定）: {temp_path} -> {target_path}")
                    return False
            except Exception as e:
                logger.error(f"重命名失败: {temp_path} -> {target_path}: {e}")
                return False
        return False

    def __download_single_file(self, urls: Union[str, List[str]], save_path: str) -> bool:
        """下载单个文件，支持备用链接和文件锁保护"""
        if isinstance(urls, str):
            urls = [urls]
            
        save_file_path = Path(save_path)
        temp_suffix = f".tmp_{threading.current_thread().ident}_{random.randint(1000, 9999)}"
        temp_path = save_file_path.with_name(save_file_path.name + temp_suffix)

        try:
            save_file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"创建目录失败 {save_file_path.parent}: {str(e)}")
            return False

        for download_url in urls:
            if not download_url: 
                continue
            
            file_size = self.__get_file_size(download_url)
            if file_size is None:
                continue

            downloaded_size = 0
            if temp_path.exists():
                try:
                    downloaded_size = temp_path.stat().st_size
                    if downloaded_size >= file_size > 0:
                        temp_path.unlink(missing_ok=True)
                        downloaded_size = 0
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    downloaded_size = 0

            if self.__download_stream(download_url, temp_path, downloaded_size):
                try:
                    final_size = temp_path.stat().st_size
                    if 0 < file_size != final_size:
                        logger.warning(f"文件大小不匹配: 期望 {file_size}, 实际 {final_size}")
                        continue
                    
                    if self.__safe_rename(temp_path, save_file_path):
                        return True
                    else:
                        temp_path.unlink(missing_ok=True)
                        continue
                        
                except Exception as e:
                    logger.debug(f"验证/重命名失败: {e}")
                    continue
        
        temp_path.unlink(missing_ok=True)
        return False

    def download_manager(self, download_list: List[Tuple[Union[str, List[str]], str]], max_threads: int) -> bool:
        """下载管理器（带文件锁保护）"""
        if not download_list or max_threads <= 0:
            logger.warning("下载列表为空或线程数无效")
            return False

        if self.enable_progress_bar:
            sys.stdout.write("\n")

        logger.info(f"开始下载 {len(download_list)} 个文件，使用 {max_threads} 个线程")

        with self.lock:
            self.__download_total = download_list
            self.__download_done.clear()

        successful_downloads = 0
        failed_files = []
        
        actual_threads = min(max_threads, 16)
        
        try:
            with ThreadPoolExecutor(max_workers=actual_threads) as executor:
                future_to_url = {
                    executor.submit(self.__download_single_file, urls, save_path): (urls, save_path)
                    for urls, save_path in self.__download_total
                }

                for future in as_completed(future_to_url):
                    urls, save_path = future_to_url[future]
                    try:
                        success = future.result()
                        if success:
                            with self.lock:
                                self.__download_done.append(save_path)
                                successful_downloads += 1
                            self.output_progress(self.__download_total, self.__download_done)
                        else:
                            failed_files.append(save_path)
                            logger.error(f"下载失败: {save_path}")
                    except Exception as e:
                        logger.error(f"任务执行异常: {str(e)}")
                        failed_files.append(save_path)
                        
        except Exception as e:
            logger.error(f"下载管理器异常: {str(e)}")

        total_files = len(self.__download_total)
        
        if self.enable_progress_bar:
            sys.stdout.write("\n")
            sys.stdout.flush()
        
        if successful_downloads == total_files:
            logger.info(f"✓ 全部下载成功: {successful_downloads}/{total_files}")
        else:
            logger.warning(f"下载统计: 成功 {successful_downloads}/{total_files}, 失败 {len(failed_files)}")
            if failed_files:
                logger.debug(f"失败的文件（前5个）: {failed_files[:5]}")

        return successful_downloads == total_files