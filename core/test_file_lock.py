import multiprocessing
import time

from core.file_lock import locked_file


def _hold_lock(path: str, ready, release) -> None:
    with locked_file(path):
        ready.set()
        release.wait(10)


def _acquire_lock(path: str, acquired) -> None:
    with locked_file(path):
        acquired.set()


def test_file_lock_serializes_independent_processes(tmp_path):
    path = str(tmp_path / "state.lock")
    context = multiprocessing.get_context("spawn")
    holder_ready = context.Event()
    release = context.Event()
    acquired = context.Event()

    holder = context.Process(target=_hold_lock, args=(path, holder_ready, release))
    waiter = context.Process(target=_acquire_lock, args=(path, acquired))
    holder.start()
    try:
        assert holder_ready.wait(5)

        waiter.start()
        time.sleep(0.2)
        assert not acquired.is_set()

        release.set()
        assert acquired.wait(5)
    finally:
        release.set()
        holder.join(5)
        waiter.join(5)
        if holder.is_alive():
            holder.terminate()
            holder.join(5)
        if waiter.is_alive():
            waiter.terminate()
            waiter.join(5)

    assert holder.exitcode == 0
    assert waiter.exitcode == 0
