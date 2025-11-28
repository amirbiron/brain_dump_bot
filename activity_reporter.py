from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError, ConfigurationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ReporterConfig:
    mongodb_uri: str
    service_id: str
    service_name: str
    database_name: str
    collection_name: str


class _NoopActivityReporter:
    """
    Fallback reporter used when MongoDB is unavailable.
    """

    def __init__(self, config: _ReporterConfig):
        self._config = config
        self._warned = False

    def report_activity(self, user_id: Optional[int]) -> None:
        if self._warned:
            return
        self._warned = True
        logger.warning(
            "Activity reporter disabled (noop). service=%s service_id=%s",
            self._config.service_name,
            self._config.service_id,
        )


class _MongoActivityReporter:
    """
    Persists activity events into MongoDB.
    """

    def __init__(self, config: _ReporterConfig):
        self._config = config
        self._client = MongoClient(
            config.mongodb_uri,
            serverSelectionTimeoutMS=5000,
            tz_aware=True,
            appname=f"{config.service_name}-activity-reporter",
        )
        self._collection: Collection = self._client[config.database_name][config.collection_name]
        self._had_error = False

    def report_activity(self, user_id: Optional[int]) -> None:
        if user_id is None:
            return

        event = {
            "service_id": self._config.service_id,
            "service_name": self._config.service_name,
            "user_id": user_id,
            "reported_at": datetime.now(timezone.utc),
        }

        try:
            self._collection.insert_one(event)
            if self._had_error:
                logger.info("Activity reporter connection restored.")
                self._had_error = False
        except PyMongoError:
            if not self._had_error:
                logger.exception("Failed to persist activity event; will keep retrying.")
            self._had_error = True


def _build_config(
    mongodb_uri: str,
    service_id: str,
    service_name: str,
    database_name: Optional[str],
    collection_name: Optional[str],
) -> _ReporterConfig:
    db_name = database_name or os.getenv("ACTIVITY_REPORT_DB", "activity_reporting")
    coll_name = collection_name or os.getenv("ACTIVITY_REPORT_COLLECTION", "user_activity")
    return _ReporterConfig(
        mongodb_uri=mongodb_uri,
        service_id=service_id,
        service_name=service_name,
        database_name=db_name,
        collection_name=coll_name,
    )


def create_reporter(
    mongodb_uri: str,
    service_id: str,
    service_name: str,
    *,
    database_name: Optional[str] = None,
    collection_name: Optional[str] = None,
):
    """
    Factory that creates an activity reporter that can be used by the bot handlers.
    Falls back to a no-op implementation if MongoDB cannot be reached.
    """
    if not mongodb_uri:
        logger.warning(
            "MongoDB URI not provided; activity reporting disabled for %s",
            service_name,
        )
        config = _build_config("", service_id, service_name, database_name, collection_name)
        return _NoopActivityReporter(config)

    config = _build_config(mongodb_uri, service_id, service_name, database_name, collection_name)

    try:
        return _MongoActivityReporter(config)
    except (PyMongoError, ConfigurationError, Exception):
        logger.exception("Failed to create Mongo activity reporter; falling back to noop.")
        return _NoopActivityReporter(config)


__all__ = ["create_reporter"]
