from django.core.cache import cache
from django.test import TestCase

from monitoring.task_locks import task_lease


class MonitoringLeaseTests(TestCase):
    def test_only_one_holder_can_acquire_named_lease(self):
        cache.clear()
        with task_lease('architecture-test', timeout=30) as first:
            self.assertTrue(first)
            with task_lease('architecture-test', timeout=30) as second:
                self.assertFalse(second)
        with task_lease('architecture-test', timeout=30) as after_release:
            self.assertTrue(after_release)
