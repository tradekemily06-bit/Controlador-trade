import pytest

from core.replay_policy import MAX_REPLAY_CASES, prevalidate_replay_cases


def test_accepts_up_to_maximum_scenarios():
    cases = [{"score": 50} for _ in range(MAX_REPLAY_CASES)]
    assert len(prevalidate_replay_cases(cases)) == MAX_REPLAY_CASES


def test_rejects_51st_scenario_before_processing_it():
    seen = []

    def stream():
        for index in range(MAX_REPLAY_CASES + 1):
            seen.append(index)
            yield {"score": index}

    with pytest.raises(ValueError, match="50"):
        prevalidate_replay_cases(stream())

    # The guard reads only the 51st item as the rejection sentinel; it never
    # hands an oversized request to the analysis layer.
    assert seen == list(range(MAX_REPLAY_CASES + 1))


def test_rejects_invalid_scenario_before_returning_any_accepted_batch():
    cases = [{"score": 90}, "invalid", {"score": 80}]

    with pytest.raises(ValueError, match="posição 2"):
        prevalidate_replay_cases(cases)
