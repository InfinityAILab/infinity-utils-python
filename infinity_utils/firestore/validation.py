from __future__ import annotations

from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel


def _validate_field_path_and_get_type(model: type[BaseModel], field_path: str) -> Any:
    """
    Validates a field path against a Pydantic model and returns the field's type.
    Supports nested models and Optional types.
    """
    current_type: Any = model
    parts = field_path.split(".")
    for i, part in enumerate(parts):
        origin = get_origin(current_type)
        resolved_type = origin or current_type

        # Resolve Optional[T] to T
        if origin is Union:
            args = [arg for arg in get_args(current_type) if arg is not type(None)]
            if len(args) == 1:
                resolved_type = args[0]
                origin = get_origin(resolved_type) or resolved_type
            else:
                raise TypeError(
                    f"Querying on Union fields with multiple types is not supported for '{'.'.join(parts[:i])}'"
                )

        if not isinstance(resolved_type, type) or not issubclass(resolved_type, BaseModel):
            if i < len(parts) - 1:
                raise TypeError(
                    f"Field '{'.'.join(parts[:i])}' of type '{current_type.__name__}' is not a Pydantic model, so cannot access nested field '{part}'."
                )

        if not hasattr(resolved_type, "model_fields") or part not in resolved_type.model_fields:
            raise ValueError(f"Field '{part}' not found in {resolved_type.__name__} for path '{field_path}'.")

        current_type = resolved_type.model_fields[part].annotation

    return current_type
