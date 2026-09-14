import pytest

from core.replay_policy import prevalidate_replay_cases


def test_accepts_arbitrary_number_of_valid_scenarios():
    cases = [{"score": index} for index in range(101)]
    assert len(prevalidate_replay_cases(cases)) == 101


def test_accepts_generator_without_a_scenario_count_ceiling():
    seen = []

    def stream():
        for index in range(101):
            seen.append(index)
            yield {"score": index}

    accepted = prevalidate_replay_cases(stream())

    assert len(accepted) == 101
    assert seen == list(range(101))


def test_rejects_invalid_scenario_before_returning_any_accepted_batch():
    cases = [{"score": 90}, "invalid", {"score": 80}]

    with pytest.raises(ValueError, match="posição 2"):
        prevalidate_replay_cases(cases)
