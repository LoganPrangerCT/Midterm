"""Volatile storage for one current league; reports are generated on demand."""
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4


class LeagueRepository:
    def __init__(self):
        self._league = None
        self._lock = RLock()

    def all(self):
        with self._lock:
            return [deepcopy(self._league)] if self._league is not None else []

    def current(self):
        with self._lock:
            return deepcopy(self._league)

    def exists(self, league_id):
        with self._lock:
            return self._league is not None and self._league['id'] == league_id

    def create(self, fields):
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        resource = {**fields, 'id': str(uuid4()), 'createdAt': timestamp, 'updatedAt': timestamp}
        with self._lock:
            if self._league is not None:
                return None
            self._league = deepcopy(resource)
            return deepcopy(resource)

    def replace(self, league_id, fields):
        with self._lock:
            if not self.exists(league_id):
                return None
            old = self._league
            timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            replacement = {**fields, 'id': league_id, 'createdAt': old['createdAt'],
                           'updatedAt': timestamp}
            self._league = deepcopy(replacement)
            return deepcopy(replacement)

    def delete(self, league_id):
        with self._lock:
            if not self.exists(league_id):
                return False
            self._league = None
            return True


repository = LeagueRepository()
