from pydantic import BaseModel
from typing import Generic, TypeVar

T = TypeVar('T')

class A(BaseModel, Generic[T]):
    items: list[T]

try:
    print(A[dict](items=[{'a': 1}]).model_dump())
except Exception as e:
    print(e)
