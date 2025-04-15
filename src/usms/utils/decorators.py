"""USMS Decorators."""

from usms.exceptions.errors import USMSNotInitializedError


def requires_init(method):
    """Guard method calls until class is ready."""

    def wrapper(self, *args, **kwargs):
        if not getattr(self, "_initialized", False):
            raise USMSNotInitializedError(self.__class__.__name__)
        return method(self, *args, **kwargs)

    return wrapper
