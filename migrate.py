# migrate.py
from backend.storage.db import Base, engine  # ← engine is imported from storage

def migrate():
    print("Adding user_profiles table...")
    Base.metadata.create_all(engine)  # ← using the engine from storage
    print("✅ Migration complete!")

if __name__ == "__main__":
    migrate()