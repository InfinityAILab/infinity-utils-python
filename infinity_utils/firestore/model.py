from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar, Generic, TypeVar, get_args, get_origin

from google.cloud.firestore import AsyncClient, FieldFilter
from google.cloud.firestore_v1.base_collection import _auto_id
from google.cloud.firestore_v1.query import Query
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from infinity_utils.firestore.exception import ModelValidationError
from infinity_utils.firestore.validation import _validate_field_path_and_get_type

T = TypeVar("T", bound="Model")


class QueryBuilder(Generic[T]):
    def __init__(self, model_cls: type[T]) -> None:
        self._model_cls = model_cls
        db = model_cls._get_db()
        self._query: Query = db.collection(model_cls._collection_name)

    def filter(self, *queries: FieldFilter) -> QueryBuilder[T]:
        """Add where clauses to the query."""
        for f in queries:
            try:
                field_path = f.field_path
                op = f.op_string
                value = f.value
                field_type = _validate_field_path_and_get_type(self._model_cls, field_path)
                if op in ("in", "not_in", "array_contains_any"):
                    if not isinstance(value, (list, tuple)):
                        raise TypeError(f"Value for operator '{op}' on field '{field_path}' must be a list or tuple.")
                    if get_origin(field_type) in (list, set):  # array_contains_any
                        item_type = get_args(field_type)[0]
                        TypeAdapter(list[item_type]).validate_python(value)
                    else:  # in, not_in
                        TypeAdapter(list[field_type]).validate_python(value)
                elif get_origin(field_type) in (list, set) and op == "array_contains":
                    item_type = get_args(field_type)[0]
                    TypeAdapter(item_type).validate_python(value)
                else:
                    TypeAdapter(field_type).validate_python(value)
            except (ValueError, TypeError, ValidationError) as e:
                raise ValueError(f"Validation failed for query ('{field_path}', '{op}', ...): {e}") from e
            self._query = self._query.where(filter=f)
        return self

    def order_by(self, *fields: str) -> QueryBuilder[T]:
        """Add order by clauses to the query."""
        for field in fields:
            field_name = field.lstrip("-")
            try:
                _validate_field_path_and_get_type(self._model_cls, field_name)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Validation failed for order_by field '{field_name}': {e}") from e
            direction = "DESCENDING" if field.startswith("-") else "ASCENDING"
            self._query = self._query.order_by(field_name, direction=direction)
        return self

    def limit(self, limit: int) -> QueryBuilder[T]:
        """Add a limit to the query."""
        self._query = self._query.limit(limit)
        return self

    def offset(self, offset: int) -> QueryBuilder[T]:
        """Add an offset to the query."""
        self._query = self._query.offset(offset)
        return self

    async def get(self) -> list[T]:
        """Execute the query and return the results."""
        docs = await self._query.get()
        results = []
        for doc in docs:
            try:
                results.append(self._model_cls(**doc.to_dict(), id=doc.id))
            except ValidationError as e:
                raise ModelValidationError(
                    model_name=self._model_cls.__name__,
                    doc_id=doc.id,
                    collection_name=self._model_cls._collection_name,
                    validation_error=e,
                ) from e
        return results


class Model(BaseModel):
    id: str = Field(default_factory=_auto_id)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    _collection_name: ClassVar[str]
    _database_name: ClassVar[str | None] = None
    _clients: ClassVar[dict[str | None, AsyncClient]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        This method is called when a class is subclassed.
        It is used to read the collection_name and database_name from the Meta class.
        """
        super().__init_subclass__(**kwargs)

        # Skip this logic for the base class itself
        if cls.__name__ == "Model":
            return

        meta = getattr(cls, "Meta", None)

        # Read collection_name from Meta, with fallback to the class attribute for backward compatibility
        collection_name = getattr(meta, "collection_name", getattr(cls, "_collection_name", None))
        if collection_name:
            cls._collection_name = collection_name
        else:
            raise TypeError(
                f"Firestore model {cls.__name__} must have a `_collection_name` attribute "
                "or a `Meta` class with a `collection_name` attribute."
            )

        # Read database_name from Meta, with fallback to the class attribute for backward compatibility
        database_name = getattr(meta, "database_name", getattr(cls, "_database_name", None))
        cls._database_name = database_name

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    @classmethod
    def _get_db(cls: type[T]) -> AsyncClient:
        """Get the database client, creating it if it doesn't exist."""
        if cls._database_name not in cls._clients:
            cls._clients[cls._database_name] = AsyncClient(database=cls._database_name)
        return cls._clients[cls._database_name]

    async def save(self: T) -> T:
        """Save the document to Firestore."""
        self.updated_at = datetime.now(timezone.utc)
        try:
            type(self).model_validate(self.model_dump())
        except ValidationError as e:
            raise ModelValidationError(
                model_name=self.__class__.__name__,
                doc_id=self.id,
                collection_name=self._collection_name,
                validation_error=e,
            ) from e
        db = self._get_db()
        await db.collection(self._collection_name).document(self.id).set(self.model_dump(exclude={"id"}))
        return self

    @classmethod
    async def get(cls: type[T], id: str) -> T | None:
        """Get a document from Firestore by id."""
        db = cls._get_db()
        doc = await db.collection(cls._collection_name).document(id).get()
        if not doc.exists:
            return None
        try:
            return cls(**doc.to_dict(), id=doc.id)
        except ValidationError as e:
            raise ModelValidationError(
                model_name=cls.__name__,
                doc_id=doc.id,
                collection_name=cls._collection_name,
                validation_error=e,
            ) from e

    async def delete(self: T) -> None:
        """Delete the document from Firestore."""
        db = self._get_db()
        await db.collection(self._collection_name).document(self.id).delete()

    @classmethod
    def filter(cls: type[T], *queries: FieldFilter) -> QueryBuilder[T]:
        """Creates a query builder with the specified filters."""
        return QueryBuilder(cls).filter(*queries)

    @classmethod
    def order_by(cls: type[T], *fields: str) -> QueryBuilder[T]:
        """Creates a query builder with the specified ordering."""
        return QueryBuilder(cls).order_by(*fields)

    @classmethod
    def limit(cls: type[T], limit: int) -> QueryBuilder[T]:
        """Creates a query builder with the specified limit."""
        return QueryBuilder(cls).limit(limit)

    @classmethod
    def offset(cls: type[T], offset: int) -> QueryBuilder[T]:
        """Creates a query builder with the specified offset."""
        return QueryBuilder(cls).offset(offset)
