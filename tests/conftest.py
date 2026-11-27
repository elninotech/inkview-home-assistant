import pytest


@pytest.fixture(autouse=True, scope="session")
def _start_pycares_shutdown_thread():
    # pycares starts a process-wide thread on first use; start it up front so the
    # plugin's lingering-thread check doesn't fail whichever test hits it first.
    try:
        import pycares

        pycares._shutdown_manager.start()  # noqa: SLF001
    except (ImportError, AttributeError):
        pass
    yield
