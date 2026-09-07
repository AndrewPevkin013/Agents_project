from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union


HandlerOutput = Union[str, List[Dict[str, Any]]]


class BaseHandler(ABC):
    @abstractmethod
    def handle(self, user_request: str) -> HandlerOutput:
        """Process a user request and return natural language or engine commands."""
        raise NotImplementedError