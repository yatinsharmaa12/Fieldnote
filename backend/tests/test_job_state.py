import pytest
from app.domain.job_state import JobState, InvalidStateTransition, transition_job_state


class MockJob:
    def __init__(self, status, attempt_count=0):
        self.status = status
        self.started_at = None
        self.completed_at = None
        self.last_heartbeat_at = None
        self.error = None
        self.attempt_count = attempt_count


def test_valid_transitions():
    # QUEUED -> RUNNING
    job = MockJob(JobState.QUEUED.value)
    transition_job_state(job, JobState.RUNNING)
    assert job.status == JobState.RUNNING.value
    assert job.started_at is not None
    assert job.last_heartbeat_at is not None

    # RUNNING -> COMPLETED
    job = MockJob(JobState.RUNNING.value)
    transition_job_state(job, JobState.COMPLETED)
    assert job.status == JobState.COMPLETED.value
    assert job.completed_at is not None

    # RUNNING -> FAILED
    job = MockJob(JobState.RUNNING.value)
    transition_job_state(job, JobState.FAILED, "Error message")
    assert job.status == JobState.FAILED.value
    assert job.completed_at is not None
    assert job.error == "Error message"

    # RUNNING -> TIMED_OUT
    job = MockJob(JobState.RUNNING.value)
    transition_job_state(job, JobState.TIMED_OUT, "Crawl exceeded its limit")
    assert job.status == JobState.TIMED_OUT.value
    assert job.completed_at is not None
    assert job.error == "Crawl exceeded its limit"

    # RUNNING -> QUEUED
    job = MockJob(JobState.RUNNING.value)
    transition_job_state(job, JobState.QUEUED, "Transient error")
    assert job.status == JobState.QUEUED.value
    assert job.error == "Transient error"

    # QUEUED -> FAILED (queue failure)
    job = MockJob(JobState.QUEUED.value)
    transition_job_state(job, JobState.FAILED, "Failed to start")
    assert job.status == JobState.FAILED.value
    assert job.error == "Failed to start"


def test_invalid_transitions():
    job = MockJob(JobState.COMPLETED.value)
    with pytest.raises(InvalidStateTransition):
        transition_job_state(job, JobState.RUNNING)

    job = MockJob(JobState.FAILED.value)
    with pytest.raises(InvalidStateTransition):
        transition_job_state(job, JobState.QUEUED)

    job = MockJob(JobState.QUEUED.value)
    with pytest.raises(InvalidStateTransition):
        transition_job_state(job, JobState.COMPLETED)


def test_attempt_count_increments():
    # 1. First QUEUED -> RUNNING increments attempt_count correctly.
    job = MockJob(JobState.QUEUED.value, attempt_count=0)
    transition_job_state(job, JobState.RUNNING)
    assert job.attempt_count == 1
    
    # 2. RUNNING -> QUEUED does NOT increment attempt_count.
    transition_job_state(job, JobState.QUEUED, "Transient error")
    assert job.attempt_count == 1
    
    # 3. Second QUEUED -> RUNNING increments it again.
    transition_job_state(job, JobState.RUNNING)
    assert job.attempt_count == 2
    
    # 4. Permanent failure does not incorrectly increment it.
    transition_job_state(job, JobState.FAILED, "Permanent error")
    assert job.attempt_count == 2


def test_completed_to_queued_resets_temporal_fields():
    """COMPLETED → QUEUED must clear started_at/completed_at/last_heartbeat_at
    so a rerun starts with clean timestamps."""
    from datetime import datetime

    job = MockJob(JobState.QUEUED.value, attempt_count=0)
    transition_job_state(job, JobState.RUNNING)
    transition_job_state(job, JobState.COMPLETED)

    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.last_heartbeat_at is not None

    # Reset for rerun
    transition_job_state(job, JobState.QUEUED)
    assert job.started_at is None
    assert job.completed_at is None
    assert job.last_heartbeat_at is None
    assert job.status == JobState.QUEUED.value

    # Rerun increments attempt_count again
    transition_job_state(job, JobState.RUNNING)
    assert job.attempt_count == 2
    assert job.started_at is not None


def test_terminal_states_cannot_transition():
    """FAILED, CANCELLED and TIMED_OUT must be terminal — no outgoing edges."""
    for terminal in (JobState.FAILED, JobState.CANCELLED, JobState.TIMED_OUT):
        for target in JobState:
            job = MockJob(terminal.value)
            with pytest.raises(InvalidStateTransition):
                transition_job_state(job, target)
