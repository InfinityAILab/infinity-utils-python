# infinity-utils-python

This repository contains a collection of utility functions and classes designed to streamline development for Python projects at Infinity AI Lab.

## Firestore ODM

A lightweight, asynchronous Object-Document Mapper (ODM) for Google Cloud Firestore, built on top of Pydantic and the official Google Cloud Firestore library.

### Features

- **Pydantic-based validation**: Define your models using Pydantic for automatic data validation.
- **Asynchronous API**: All database operations are `async`, designed for modern Python applications.
- **Simple, Django-like API**: Familiar `save()`, `get()`, `find()`, and `delete()` methods.
- **Automatic Timestamps**: `created_at` and `updated_at` fields are automatically managed.

### Installation

Make sure you have `google-cloud-firestore` and `pydantic` installed in your environment.

```bash
uv sync
```

### Authentication

Make sure `GOOGLE_APPLICATION_CREDENTIALS` is set to the path of your service account key file.

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
```

### Defining Models

To define a model, inherit from `infinity_utils.firestore.model.Model` and define your fields using Pydantic. You must also define an inner `Meta` class with at least a `collection_name`.

```python
from infinity_utils.firestore.model import Model

class User(Model):
    name: str
    email: str
    age: int | None = None

    class Meta:
        collection_name = "users"
```

### Creating and Saving Documents

Instantiate your model and call the `save()` method.

```python
import asyncio
from infinity_utils.firestore.model import Model

class User(Model):
    name: str
    email: str
    age: int | None = None

    class Meta:
        collection_name = "users"

async def main():
    # Create a new user
    new_user = User(name="John Doe", email="john.doe@example.com", age=30)

    # Save it to Firestore
    await new_user.save()

    print(f"User created with ID: {new_user.id}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Retrieving Documents

**Get a document by ID:**

```python
async def get_user(user_id: str):
    user = await User.get(user_id)
    if user:
        print(f"Found user: {user.name}")
    else:
        print("User not found.")

# Example usage:
# asyncio.run(get_user("some_user_id"))
```

**Find documents with queries:**
Use the `find()` method with `google.cloud.firestore.FieldFilter` to query the collection.

```python
from google.cloud.firestore import FieldFilter

async def find_users():
    # Find all users older than 25
    users = await User.find(FieldFilter("age", ">", 25))
    for user in users:
        print(f"Found user: {user.name}, Age: {user.age}")

    # Find a specific user by email
    users = await User.find(FieldFilter("email", "==", "john.doe@example.com"))
    if users:
        print(f"Found user by email: {users[0].name}")

# Example usage:
# asyncio.run(find_users())
```

The `find` method also supports `order_by` and `limit`:

```python
# Get the 2 oldest users
users = await User.find(order_by=["-age"], limit=2)
```

### Updating Documents

To update a document, simply change its attributes and call `save()` again. The `updated_at` timestamp will be automatically updated.

```python
async def update_user(user_id: str):
    user = await User.get(user_id)
    if user:
        user.age = 31
        await user.save()
        print(f"User {user.name} updated.")

# Example usage:
# asyncio.run(update_user("some_user_id"))
```

### Deleting Documents

Call the `delete()` method on a model instance to remove it from Firestore.

```python
async def delete_user(user_id: str):
    user = await User.get(user_id)
    if user:
        await user.delete()
        print(f"User with ID {user_id} deleted.")

# Example usage:
# asyncio.run(delete_user("some_user_id"))
```
