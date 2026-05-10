"""Resource service modules used by ``Bot`` (issue #32).

Each service owns one Discord resource family. ``Bot`` keeps its public
methods unchanged but delegates to these services so the facade stops
expanding every time a new REST endpoint lands.
"""

from .messages import MessageService

__all__ = ["MessageService"]
