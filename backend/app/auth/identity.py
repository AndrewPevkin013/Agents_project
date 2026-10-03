from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentIdentity:
    user_id: uuid.UUID
    identity_subject: str