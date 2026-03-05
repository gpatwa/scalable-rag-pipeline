# libs/utils/timing.py
import time
import functools
import logging

logger = logging.getLogger("performance")

def measure_time(func):
    """
    Decorator to log execution time of synchronous functions.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000 # ms
        logger.info(f"Function '{func.__name__}' took {execution_time:.2f} ms")
        return result
    return wrapper

def measure_time_async(func):
    """
    Decorator to log execution time of async functions.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000 # ms
        logger.info(f"Async Function '{func.__name__}' took {execution_time:.2f} ms")
        return result
    return wrapper