import time
from typing import Optional, Callable, Any
from functools import wraps
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, auto
import logging
from core.config import logger

class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()

@dataclass
class CircuitBreakerStats:
    failures: int = 0
    successes: int = 0
    last_failure_time: Optional[float] = None
    state_changes: int = 0

class CircuitBreakerError(Exception):
    """Custom exception for circuit breaker failures"""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 30,
        expected_exceptions: tuple = (Exception,),
        name: str = "default",
        monitor_interval: int = 60
    ):
        """
        Initialize the Circuit Breaker.

        Args:
            failure_threshold: Number of failures before opening the circuit
            recovery_timeout: Time in seconds before attempting recovery
            expected_exceptions: Exceptions that count as failures
            name: Identifier for this circuit breaker
            monitor_interval: Time window for monitoring failures (in seconds)
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        self.name = name
        self.monitor_interval = monitor_interval

        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None

        logger.info(f"CircuitBreaker '{self.name}' initialized with threshold {failure_threshold}")

    async def __aenter__(self):
        await self._check_state()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None and isinstance(exc_val, self.expected_exceptions):
            await self._record_failure()
        elif exc_val is None:
            await self._record_success()

    def __call__(self, func: Callable):
        @wraps(func)
        async def async_wrapped(*args, **kwargs):
            async with self:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if isinstance(e, self.expected_exceptions):
                        raise CircuitBreakerError(
                            f"Circuit '{self.name}' blocked call to {func.__name__}",
                            original_exception=e
                        )
                    raise
        return async_wrapped

    async def _check_state(self):
        async with self._lock:
            if self.state == CircuitState.OPEN:
                current_time = time.time()
                if (current_time - (self.stats.last_failure_time or 0)) > self.recovery_timeout:
                    await self._half_open()
                else:
                    raise CircuitBreakerError(
                        f"Circuit '{self.name}' is OPEN (failures: {self.stats.failures})"
                    )
            elif self.state == CircuitState.HALF_OPEN:
                raise CircuitBreakerError(
                    f"Circuit '{self.name}' is HALF-OPEN (testing recovery)"
                )

    async def _record_failure(self):
        async with self._lock:
            self.stats.failures += 1
            self.stats.last_failure_time = time.time()

            if (self.state == CircuitState.CLOSED and
                self.stats.failures >= self.failure_threshold):
                await self._open()
            elif self.state == CircuitState.HALF_OPEN:
                await self._open()

    async def _record_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                await self._close()
            self.stats.successes += 1

    async def _open(self):
        self.state = CircuitState.OPEN
        self.stats.state_changes += 1
        logger.warning(
            f"Circuit '{self.name}' OPENED. "
            f"Failures: {self.stats.failures}, "
            f"Last error at: {self.stats.last_failure_time}"
        )

        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_circuit())

    async def _half_open(self):
        self.state = CircuitState.HALF_OPEN
        self.stats.state_changes += 1
        logger.info(f"Circuit '{self.name}' moved to HALF-OPEN state")

    async def _close(self):
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self.stats.state_changes += 1
        logger.info(f"Circuit '{self.name}' CLOSED. Recovery successful")

        if self._monitor_task:
            self._monitor_task.cancel()

    async def _monitor_circuit(self):
        """Background task to monitor circuit state and attempt recovery"""
        while self.state == CircuitState.OPEN:
            await asyncio.sleep(5)

            async with self._lock:
                current_time = time.time()
                if (current_time - (self.stats.last_failure_time or 0)) > self.recovery_timeout:
                    await self._half_open()

    def get_state(self) -> CircuitState:
        """Get current circuit state (thread-safe)"""
        return self.state

    def get_stats(self) -> CircuitBreakerStats:
        """Get current circuit statistics (thread-safe)"""
        return self.stats

    @contextmanager
    def context(self):
        """Synchronous context manager for non-async code"""
        try:
            yield
        except self.expected_exceptions as e:
            asyncio.run(self._record_failure())
            raise CircuitBreakerError(
                f"Circuit '{self.name}' blocked operation",
                original_exception=e
            )
        else:
            asyncio.run(self._record_success())

weather_circuit_breaker = CircuitBreaker(
    name="weather_api",
    failure_threshold=3,
    recovery_timeout=60,
    expected_exceptions=(
        ConnectionError,
        TimeoutError,
        ValueError,
        Exception  # Catch-all for API specific errors
    )
)
