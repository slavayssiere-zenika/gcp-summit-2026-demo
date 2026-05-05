import pytest
from pydantic import ValidationError
from src.competencies.schemas import BatchEvaluationRequest, BatchUsersEvaluationRequest

def test_batch_evaluation_request_standard():
    req = BatchEvaluationRequest(user_id=1, competency_ids=[1, 2])
    assert req.user_id == 1
    assert req.competency_ids == [1, 2]

def test_batch_evaluation_request_alias():
    # Test tolerance for user_ids and competency_id aliases
    req = BatchEvaluationRequest.model_validate({"user_ids": [42], "competency_id": 99})
    assert req.user_id == 42
    assert req.competency_ids == [99]

    # Test tolerance with empty user_ids (should trigger validation error since user_id is missing/empty)
    with pytest.raises(ValidationError):
        BatchEvaluationRequest.model_validate({"user_ids": [], "competency_ids": [1]})

    # Test tolerance with singular int in user_ids (edge case)
    req = BatchEvaluationRequest.model_validate({"user_ids": 42, "competency_id": 99})
    assert req.user_id == 42


def test_batch_users_evaluation_request_standard():
    req = BatchUsersEvaluationRequest(competency_id=99, user_ids=[1, 2])
    assert req.competency_id == 99
    assert req.user_ids == [1, 2]

def test_batch_users_evaluation_request_alias():
    # Test tolerance for competency_ids and user_id aliases
    req = BatchUsersEvaluationRequest.model_validate({"competency_ids": [99], "user_id": 42})
    assert req.competency_id == 99
    assert req.user_ids == [42]

    # Test tolerance with empty competency_ids
    with pytest.raises(ValidationError):
        BatchUsersEvaluationRequest.model_validate({"competency_ids": [], "user_ids": [1]})

    # Test tolerance with singular int in competency_ids (edge case)
    req = BatchUsersEvaluationRequest.model_validate({"competency_ids": 99, "user_id": 42})
    assert req.competency_id == 99
