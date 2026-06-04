"""Tests for the per-session telemetry in auth/stats.py."""
import time

from custom_components.inkview.auth.stats import SessionStats


def test_counts_and_last_timestamps():
    s = SessionStats()
    s.record_token_issued(expires_at=123.0)
    s.record_failed_auth()
    s.record_state_fetch()

    snap = s.snapshot()
    assert snap["tokens_issued_24h"] == 1
    assert snap["failed_auth_24h"] == 1
    assert snap["last_token_expires_at"] == 123.0
    assert snap["last_token_minted_at"] is not None
    assert snap["last_failed_auth_at"] is not None
    assert snap["last_state_fetch_at"] is not None


def test_evicts_entries_older_than_24h():
    s = SessionStats()
    stale = time.time() - 25 * 3600
    s._tokens.append(stale)
    s._failures.append(stale)

    s.record_token_issued()  # one fresh token; also triggers eviction

    snap = s.snapshot()
    assert snap["tokens_issued_24h"] == 1  # stale token evicted, fresh kept
    assert snap["failed_auth_24h"] == 0    # stale failure evicted


def test_empty_snapshot():
    snap = SessionStats().snapshot()
    assert snap["tokens_issued_24h"] == 0
    assert snap["failed_auth_24h"] == 0
    assert snap["last_token_minted_at"] is None
