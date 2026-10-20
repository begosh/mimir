"""
scripts/agy_swarm.py
Portabel bakåtkompatibilitets-wrapper för Antigravity CLI (agy).
Vidarebefordrar till den modulära backend-motorn i backend.py.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from backend import AgySwarmBackend, SwarmResult, SwarmTask

# Alias för 100% bakåtkompatibilitet
AgySwarm = AgySwarmBackend

__all__ = ["AgySwarm", "AgySwarmBackend", "SwarmResult", "SwarmTask"]
