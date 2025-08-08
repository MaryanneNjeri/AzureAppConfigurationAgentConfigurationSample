import asyncio
import threading
from typing import Optional, Any, Coroutine

class EventLoopManager:
    """Manages a dedicated event loop for async operations in a Flask app."""
    
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._start_loop()
    
    def _start_loop(self):
        """Start the event loop in a separate thread."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(
                target=self._loop.run_forever, 
                name="app-event-loop", 
                daemon=True
            )
            self._loop_thread.start()
    
    def run_async(self, coro: Coroutine, timeout: Optional[float] = None) -> Any:
        """Run an async coroutine on the app loop and wait for result."""
        if self._loop is None:
            raise RuntimeError("Event loop not started")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)
    
    def stop(self):
        """Stop the event loop and cleanup."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=2)
        self._loop = None
        self._loop_thread = None
    
    @property
    def is_running(self) -> bool:
        """Check if the event loop is running."""
        return self._loop is not None and self._loop.is_running()