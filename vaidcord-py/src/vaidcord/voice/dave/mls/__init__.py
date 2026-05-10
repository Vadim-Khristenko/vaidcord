"""MLS group-state abstraction for the DAVE protocol.

DAVE is layered on top of `MLS (RFC 9420) <https://datatracker.ietf.org/doc/html/rfc9420>`_
for key agreement. The voice gateway forwards MLS proposals, welcomes, and
commits; the local backend converts those into a stream of group epoch
secrets that the rest of the DAVE stack uses to derive frame keys.

This package exposes:

* :class:`MLSProvider` -- the small protocol that any MLS implementation
  (in-process reference, a wrapper around ``mls-rs``, ``openmls``, etc.)
  must implement to plug into the DAVE controller.
* :class:`InProcessMLSProvider` -- a single-participant reference provider
  that produces real, deterministic epoch secrets. It is suitable for tests,
  loopback ("bot talking to itself") sessions, and any deployment where
  multi-party group agreement isn't required (yet).
* Serializable types -- :class:`KeyPackage`, :class:`Welcome`,
  :class:`Commit`, :class:`GroupEpoch` -- shared between providers.
"""

from .inproc import InProcessMLSProvider
from .provider import MLSProvider
from .types import Commit, GroupEpoch, KeyPackage, Welcome

__all__ = [
    "MLSProvider",
    "Commit",
    "GroupEpoch",
    "KeyPackage",
    "Welcome",
    "InProcessMLSProvider",
]
