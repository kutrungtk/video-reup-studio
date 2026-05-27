"""
Video Reup Studio Rebuild — Task Manager
Multi-task queue with QThread workers, cancel/pause/resume.
Learned from NAVTools task_manager.py pattern.
"""

import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal, QMutex, QWaitCondition


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A single task in the queue."""
    id: str
    name: str
    task_type: str  # pipeline, download, transcribe, tts, compose, export, watermark, upscale
    config: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    message: str = ""
    result: Any = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0


class TaskWorker(QThread):
    """Worker thread for executing a single task."""

    progress = Signal(str, int, str)    # (task_id, percent, message)
    completed = Signal(str, object)     # (task_id, result)
    error = Signal(str, str)            # (task_id, error_message)
    log = Signal(str, str)              # (task_id, log_line)

    def __init__(self, task: Task, executor: Callable):
        super().__init__()
        self._task = task
        self._executor = executor
        self._cancelled = False
        self._paused = False
        self._pause_mutex = QMutex()
        self._pause_condition = QWaitCondition()

    @property
    def task(self) -> Task:
        return self._task

    def run(self):
        """Execute the task."""
        self._task.status = TaskStatus.RUNNING
        self._task.started_at = time.time()

        try:
            # Pass cancel/pause check callback to executor
            result = self._executor(
                self._task,
                progress_cb=self._emit_progress,
                log_cb=self._emit_log,
                check_cancelled=self._check_cancelled,
            )
            if self._cancelled:
                self._task.status = TaskStatus.CANCELLED
                return

            self._task.status = TaskStatus.COMPLETED
            self._task.result = result
            self._task.completed_at = time.time()
            self.completed.emit(self._task.id, result)

        except InterruptedError:
            self._task.status = TaskStatus.CANCELLED
            self.error.emit(self._task.id, "Cancelled")
        except Exception as e:
            self._task.status = TaskStatus.ERROR
            self._task.error = str(e)
            self._task.completed_at = time.time()
            tb = traceback.format_exc()
            self.log.emit(self._task.id, f"ERROR: {e}\n{tb}")
            self.error.emit(self._task.id, str(e))

    def cancel(self):
        self._cancelled = True
        # Wake up if paused
        self._paused = False
        self._pause_condition.wakeAll()

    def pause(self):
        self._paused = True
        self._task.status = TaskStatus.PAUSED

    def resume(self):
        self._paused = False
        self._task.status = TaskStatus.RUNNING
        self._pause_condition.wakeAll()

    def _check_cancelled(self):
        """Check if cancelled or paused. Raises InterruptedError if cancelled."""
        if self._cancelled:
            raise InterruptedError("Task cancelled")
        # Handle pause
        if self._paused:
            self._pause_mutex.lock()
            self._pause_condition.wait(self._pause_mutex)
            self._pause_mutex.unlock()
            if self._cancelled:
                raise InterruptedError("Task cancelled while paused")

    def _emit_progress(self, percent: int, message: str):
        self._task.progress = percent
        self._task.message = message
        self.progress.emit(self._task.id, percent, message)

    def _emit_log(self, message: str):
        self.log.emit(self._task.id, message)


class TaskManager(QObject):
    """
    Manages a queue of tasks with concurrent execution.
    Learned from NAVTools: round-robin workers, cancel/pause per task.
    """

    # Signals for UI
    task_added = Signal(str)           # task_id
    task_started = Signal(str)         # task_id
    task_progress = Signal(str, int, str)  # task_id, percent, message
    task_completed = Signal(str, object)   # task_id, result
    task_error = Signal(str, str)      # task_id, error
    task_log = Signal(str, str)        # task_id, log_line
    queue_empty = Signal()

    def __init__(self, max_concurrent: int = 3):
        super().__init__()
        self._max_concurrent = max_concurrent
        self._queue: list[Task] = []
        self._workers: dict[str, TaskWorker] = {}  # task_id → worker
        self._executors: dict[str, Callable] = {}  # task_type → executor function

    def register_executor(self, task_type: str, executor: Callable):
        """Register an executor function for a task type."""
        self._executors[task_type] = executor

    def add_task(self, task: Task) -> str:
        """Add task to queue. Returns task ID."""
        self._queue.append(task)
        self.task_added.emit(task.id)
        self._try_start_next()
        return task.id

    def cancel_task(self, task_id: str):
        """Cancel a running or pending task."""
        # If running, cancel worker
        if task_id in self._workers:
            self._workers[task_id].cancel()
            return

        # If pending, remove from queue
        for task in self._queue:
            if task.id == task_id and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                self._queue.remove(task)
                return

    def pause_task(self, task_id: str):
        """Pause a running task."""
        if task_id in self._workers:
            self._workers[task_id].pause()

    def resume_task(self, task_id: str):
        """Resume a paused task."""
        if task_id in self._workers:
            self._workers[task_id].resume()

    def cancel_all(self):
        """Cancel all tasks."""
        for worker in list(self._workers.values()):
            worker.cancel()
        for task in self._queue:
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
        self._queue.clear()

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        for task in self._queue:
            if task.id == task_id:
                return task
        for worker in self._workers.values():
            if worker.task.id == task_id:
                return worker.task
        return None

    def get_all_tasks(self) -> list[Task]:
        """Get all tasks (queue + running)."""
        tasks = list(self._queue)
        for worker in self._workers.values():
            if worker.task not in tasks:
                tasks.append(worker.task)
        return tasks

    @property
    def running_count(self) -> int:
        return len(self._workers)

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self._queue if t.status == TaskStatus.PENDING)

    def _try_start_next(self):
        """Start next pending task if under concurrency limit."""
        if self.running_count >= self._max_concurrent:
            return

        # Find next pending task
        for task in self._queue:
            if task.status == TaskStatus.PENDING:
                self._start_task(task)
                break

    def _start_task(self, task: Task):
        """Start executing a task."""
        executor = self._executors.get(task.task_type)
        if not executor:
            task.status = TaskStatus.ERROR
            task.error = f"No executor for task type: {task.task_type}"
            self.task_error.emit(task.id, task.error)
            return

        worker = TaskWorker(task, executor)
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._on_completed)
        worker.error.connect(self._on_error)
        worker.log.connect(self._on_log)
        worker.finished.connect(lambda: self._on_worker_finished(task.id))

        self._workers[task.id] = worker
        self.task_started.emit(task.id)
        worker.start()

    def _on_progress(self, task_id: str, percent: int, message: str):
        self.task_progress.emit(task_id, percent, message)

    def _on_completed(self, task_id: str, result: object):
        self.task_completed.emit(task_id, result)

    def _on_error(self, task_id: str, error: str):
        self.task_error.emit(task_id, error)

    def _on_log(self, task_id: str, message: str):
        self.task_log.emit(task_id, message)

    def _on_worker_finished(self, task_id: str):
        """Worker thread finished — cleanup and start next."""
        if task_id in self._workers:
            del self._workers[task_id]

        # Remove completed/cancelled/error tasks from queue
        self._queue = [t for t in self._queue if t.status == TaskStatus.PENDING]

        # Try start next
        if self._queue:
            self._try_start_next()
        elif not self._workers:
            self.queue_empty.emit()
