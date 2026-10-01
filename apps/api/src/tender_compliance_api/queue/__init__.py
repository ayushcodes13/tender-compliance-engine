"""Queue adapter package (CP18).

Exports the abstract :class:`QueueAdapter`, the :class:`RedisQueueAdapter`
for production, and the :class:`FakeQueueAdapter` for tests.
"""

from tender_compliance_api.queue.adapter import (
    DEFAULT_QUEUE,
    DEFAULT_VISIBILITY_TIMEOUT,
    QueueAdapter,
    QueuedJob,
    QueueMessage,
    make_job_id,
)
from tender_compliance_api.queue.fake import FakeQueueAdapter
from tender_compliance_api.queue.redis import RedisQueueAdapter

__all__ = [
    "DEFAULT_QUEUE",
    "DEFAULT_VISIBILITY_TIMEOUT",
    "QueuedJob",
    "QueueAdapter",
    "QueueMessage",
    "make_job_id",
    "RedisQueueAdapter",
    "FakeQueueAdapter",
]
