"""Single-process reference :class:`MLSProvider` implementation.

This provider is *not* a full MLS implementation. It plays the role of a
"single participant" group state: every call to :meth:`InProcessMLSProvider.propose_add`
or :meth:`InProcessMLSProvider.apply_commit` advances the local epoch and
deterministically derives a fresh epoch secret from the previous one. It
gives the rest of the DAVE stack a real, working source of epoch secrets so
tests, loopback ("self-encryption") sessions, and CI can exercise the
crypto/ratchet/AEAD code paths without pulling in a heavyweight MLS library.

The provider is intentionally compatible with the :class:`MLSProvider`
protocol so a production-grade implementation can drop in transparently.
"""

from __future__ import annotations

import os

from ..crypto import hkdf_expand_label
from ..errors import DaveMLSError
from .provider import MLSProvider
from .types import Commit, GroupEpoch, KeyPackage, Welcome

EPOCH_SECRET_BYTES = 32


class InProcessMLSProvider(MLSProvider):
    """Reference :class:`MLSProvider` that keeps state in-process.

    Parameters
    ----------
    member_id
        Identifier for the local participant.
    group_id
        Identifier for the MLS group; for Discord this is the voice channel id.
    initial_epoch_secret
        Optional fixed initial secret. Pass a deterministic value in tests;
        omit to draw 32 random bytes from :func:`os.urandom`.
    identity_public_key
        Optional fixed long-term key used in :class:`KeyPackage`. A random key
        is generated when omitted.
    """

    def __init__(
        self,
        *,
        member_id: str,
        group_id: str = "vaidcord-dave-group",
        initial_epoch_secret: bytes | None = None,
        identity_public_key: bytes | None = None,
    ) -> None:
        self._member_id = str(member_id)
        self._group_id = str(group_id)
        self._identity_public_key = identity_public_key or os.urandom(32)
        self._initial_epoch_secret = initial_epoch_secret or os.urandom(EPOCH_SECRET_BYTES)
        self._epoch: GroupEpoch | None = None
        self._joined = False

    # ------------------------------------------------------------------ #
    # Properties                                                         #
    # ------------------------------------------------------------------ #

    @property
    def member_id(self) -> str:
        return self._member_id

    @property
    def current_epoch(self) -> int | None:
        return self._epoch.epoch if self._epoch is not None else None

    @property
    def current_epoch_secret(self) -> bytes | None:
        return self._epoch.epoch_secret if self._epoch is not None else None

    # ------------------------------------------------------------------ #
    # MLSProvider protocol                                               #
    # ------------------------------------------------------------------ #

    def generate_key_package(self) -> KeyPackage:
        """Produce a key package for the local participant."""
        return KeyPackage(
            member_id=self._member_id,
            public_key=self._identity_public_key,
            signature=b"",
        )

    def apply_welcome(self, welcome: Welcome) -> None:
        """Adopt ``welcome`` as the current epoch."""
        if welcome.group_id != self._group_id:
            raise DaveMLSError(
                f"Welcome group_id={welcome.group_id} does not match "
                f"provider group_id={self._group_id}"
            )
        self._epoch = GroupEpoch(
            epoch=int(welcome.epoch),
            group_id=welcome.group_id,
            epoch_secret=bytes(welcome.epoch_secret),
            members=list(welcome.members) or [self._member_id],
        )
        self._joined = True

    def apply_commit(self, commit: Commit) -> None:
        """Apply ``commit`` and derive the next epoch secret deterministically."""
        if not self._joined or self._epoch is None:
            self._epoch = GroupEpoch(
                epoch=int(commit.epoch),
                group_id=commit.group_id,
                epoch_secret=self._initial_epoch_secret,
                members=[self._member_id],
            )
            self._joined = True
        else:
            new_secret = hkdf_expand_label(
                secret=self._epoch.epoch_secret,
                label=b"DAVE-mls-epoch",
                context=int(commit.epoch).to_bytes(4, "big"),
                length=EPOCH_SECRET_BYTES,
            )
            members = list(self._epoch.members)
            for added in commit.add_members:
                if added not in members:
                    members.append(added)
            for removed in commit.remove_members:
                if removed in members:
                    members.remove(removed)
            self._epoch = GroupEpoch(
                epoch=int(commit.epoch),
                group_id=commit.group_id,
                epoch_secret=new_secret,
                members=members,
            )

    def propose_add(self, key_package: KeyPackage) -> Commit:
        """Build a commit that adds ``key_package`` to the group.

        The first commit creates the group from the local key package alone;
        subsequent commits include only the added members. Every commit
        advances the epoch by one and emits a :class:`Welcome` carrying the
        new epoch secret so newly admitted members can derive frame keys.
        """
        next_epoch = (self._epoch.epoch + 1) if self._epoch is not None else 0
        if self._epoch is None:
            current_secret = self._initial_epoch_secret
        else:
            current_secret = self._epoch.epoch_secret

        new_secret = hkdf_expand_label(
            secret=current_secret,
            label=b"DAVE-mls-epoch",
            context=int(next_epoch).to_bytes(4, "big"),
            length=EPOCH_SECRET_BYTES,
        )
        existing = list(self._epoch.members) if self._epoch is not None else []
        if self._member_id not in existing:
            existing.append(self._member_id)
        added = (key_package.member_id,) if key_package.member_id not in existing else ()
        members_after = (*existing, *added)

        welcome = Welcome(
            epoch=next_epoch,
            group_id=self._group_id,
            epoch_secret=new_secret,
            members=members_after,
        )
        commit = Commit(
            epoch=next_epoch,
            group_id=self._group_id,
            add_members=added,
            remove_members=(),
            welcomes=(welcome,),
        )
        self.apply_commit(commit)
        return commit


__all__ = ["InProcessMLSProvider", "EPOCH_SECRET_BYTES"]
