"""Internal collaborators that the public ``Bot`` / ``Router`` / ``HTTPClient``
facades delegate to.

The package is *internal* — code outside vaidcord should not import from
``vaidcord._internal``. The public API still lives on the facades; this
package only exists to keep the facades small and the responsibilities
focused (issue #32).
"""

from .event_parser import EventParser
from .services import MessageService

__all__ = ["EventParser", "MessageService"]
