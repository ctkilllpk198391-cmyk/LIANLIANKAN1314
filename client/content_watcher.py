"""T1 客户端 · 监听本地"魔法文件夹" · 新文件 → 上传到云端。

依赖：watchdog>=4.0
fallback：watchdog 缺失时 → 走 polling 兜底（每 30s 扫一次）

使用：
    watcher = ContentWatcher(
        watch_dir="~/wechat_agent_input",
        api_client=ApiClient(...),
        tenant_id="tenant_0001",
    )
    watcher.start()
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 文件写入完成的等待（防止半写状态被读到）
SETTLE_WAIT_SEC = 2.0


class ContentWatcher:
    def __init__(
        self,
        watch_dir: str = "~/wechat_agent_input",
        api_client=None,
        tenant_id: str = "tenant_0001",
        backend: str = "auto",   # auto / watchdog / polling
        poll_interval: int = 30,
    ):
        self.watch_dir = Path(watch_dir).expanduser()
        self.api_client = api_client
        self.tenant_id = tenant_id
        self.backend = backend
        self.poll_interval = poll_interval
        self._observer = None
        self._seen: dict[str, float] = {}   # path → mtime
        self._task: Optional[asyncio.Task] = None
        self._stop = False

    def ensure_dir(self) -> None:
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        readme = self.watch_dir / "README.md"
        if not readme.exists():
            readme.write_text(
                "# 魔法文件夹\n\n"
                "把新产品资料、活动方案、反馈截图、培训文档丢进来。\n"
                "AI 会自动消化 · 立即影响私聊回复 + 触发营销方案生成。\n\n"
                "支持格式：.md .txt .csv .docx .jpg .png .mp3 .mp4 .m4a\n",
                encoding="utf-8",
            )

    def start(self) -> None:
        self.ensure_dir()
        backend = self._resolve_backend()
        if backend == "watchdog":
            self._start_watchdog()
        else:
            self._start_polling()

    def stop(self) -> None:
        self._stop = True
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception as e:
                logger.warning("observer stop error: %s", e)
            self._observer = None
        if self._task and not self._task.done():
            self._task.cancel()

    # ─── backend 选择 ─────────────────────────────────────────────────────

    def _resolve_backend(self) -> str:
        if self.backend == "polling":
            return "polling"
        if self.backend == "watchdog":
            return "watchdog"
        # auto
        try:
            import watchdog  # noqa: F401
            return "watchdog"
        except ImportError:
            logger.info("watchdog not installed · using polling backend")
            return "polling"

    # ─── watchdog backend ────────────────────────────────────────────────

    def _start_watchdog(self) -> None:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                watcher._enqueue(event.src_path)

            def on_modified(self, event):
                if event.is_directory:
                    return
                watcher._enqueue(event.src_path)

        self._observer = Observer()
        self._observer.schedule(Handler(), str(self.watch_dir), recursive=True)
        self._observer.start()
        logger.info("content_watcher (watchdog) started · dir=%s", self.watch_dir)

    # ─── polling backend ─────────────────────────────────────────────────

    def _start_polling(self) -> None:
        async def _loop():
            while not self._stop:
                try:
                    self._scan_once()
                except Exception as e:
                    logger.error("poll scan error: %s", e)
                await asyncio.sleep(self.poll_interval)

        try:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(_loop())
        except RuntimeError:
            logger.warning("no running event loop · polling not started")

    def _scan_once(self) -> None:
        for path in self.watch_dir.rglob("*"):
            if not path.is_file() or path.name == "README.md":
                continue
            mtime = path.stat().st_mtime
            if self._seen.get(str(path)) == mtime:
                continue
            self._seen[str(path)] = mtime
            self._enqueue(str(path))

    # ─── 上传 ────────────────────────────────────────────────────────────

    def _enqueue(self, path_str: str) -> None:
        path = Path(path_str)
        if path.name == "README.md":
            return
        # 等待 settle（避免半写状态）
        try:
            init_size = path.stat().st_size
        except OSError:
            return
        time.sleep(SETTLE_WAIT_SEC)
        try:
            now_size = path.stat().st_size
        except OSError:
            return
        if init_size != now_size:
            logger.debug("file still writing · skip this round: %s", path)
            return

        try:
            data = path.read_bytes()
        except OSError as e:
            logger.warning("read failed %s: %s", path, e)
            return

        if self.api_client is None:
            logger.info("[content_watcher MOCK] would upload %s (%d bytes)", path.name, len(data))
            return

        try:
            self.api_client.upload_content(
                tenant_id=self.tenant_id,
                file_name=path.name,
                file_bytes=data,
            )
            logger.info("uploaded %s (%d bytes)", path.name, len(data))
        except Exception as e:
            logger.error("upload failed %s: %s", path, e)
