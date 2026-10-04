"""Inert process-only wrong routing: permit unsupported start to dispatch."""


def pytest_configure():
    from cairntir import managed

    original = managed.stream_command

    def wrong_route(runtime, value):
        if isinstance(value, dict) and value.get("operation") == "start":
            return runtime.dispatch(value["request"])
        return original(runtime, value)

    managed.stream_command = wrong_route
