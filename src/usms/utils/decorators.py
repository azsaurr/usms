"""USMS Decorators."""


def requires_init(method):
    """Guard method calls until class is ready."""

    def wrapper(self, *args, **kwargs):
        if not getattr(self, "_initialized", False):
            msg = f"{self.__class__.__name__} must be initialized first."
            raise RuntimeError(msg)
        return method(self, *args, **kwargs)

    return wrapper
