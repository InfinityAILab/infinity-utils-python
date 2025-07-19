from __future__ import annotations

from pydantic import ValidationError


class ModelValidationError(ValueError):
    """Custom exception for Firestore ORM validation errors."""

    def __init__(self, model_name: str, doc_id: str, collection_name: str, validation_error: ValidationError) -> None:
        self.model_name = model_name
        self.doc_id = doc_id
        self.collection_name = collection_name
        self.validation_error = validation_error

        errors = validation_error.errors()
        error_messages: list[str] = []
        for error in errors:
            field = ".".join(map(str, error["loc"]))
            message = error["msg"]
            input_value = error.get("input")
            error_messages.append(f"  - Field `{field}`: {message}. Received: {repr(input_value)}")

        helpful_message = (
            f"Pydantic validation failed for `{model_name}(id='{doc_id}')` in collection `{collection_name}`:\n"
            + "\n".join(error_messages)
            + f"\n\nHint: Check that the document data in Firestore for this record matches the `{model_name}` Pydantic model definition."
        )
        super().__init__(helpful_message)
