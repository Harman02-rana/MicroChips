import os
from dotenv import load_dotenv
from supabase import create_client, Client
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import UserModel

def migrate_users():
    print("Starting user migration to Supabase Auth...")
    
    # Load environment variables
    load_dotenv()
    
    supabase_url = os.getenv("SUPABASE_URL")
    # For migration, you need the service role key to bypass RLS and create users directly
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env to run this migration.")
        return
        
    supabase: Client = create_client(supabase_url, supabase_key)
    
    # We will use the app's existing database connection
    # It relies on DATABASE_URL
    from app import engine, DBSession
    
    db = DBSession()
    try:
        users = db.query(UserModel).all()
        print(f"Found {len(users)} users in the local database. Attempting migration...")
        
        migrated_count = 0
        for user in users:
            try:
                # Use Supabase Admin API to create user
                # Ensure you are using the service_role key to access admin functions
                # Note: creating user with existing password hash is not supported directly via the API without postgres access
                # For this migration script, we will prompt a reset or set a dummy password if needed,
                # but Supabase auth.admin.create_user doesn't require a password.
                print(f"Migrating {user.email}...")
                
                # Check if user exists in Supabase
                # Since we don't have a direct "get user by email" in the simple client without throwing errors, 
                # we'll just attempt to create and catch exceptions.
                
                # Try to create user
                response = supabase.auth.admin.create_user({
                    "email": user.email,
                    "email_confirm": True,
                    "phone": user.phone if user.phone else None,
                    "phone_confirm": bool(user.phone),
                    "user_metadata": {
                        "name": user.name,
                        "account_type": user.account_type
                    }
                })
                
                if response.user:
                    print(f"Successfully migrated: {user.email}")
                    # Update local UUID to match Supabase UUID
                    new_id = response.user.id
                    user.id = new_id
                    db.commit()
                    migrated_count += 1
                
            except Exception as e:
                print(f"Could not migrate {user.email} (they may already exist in Supabase Auth): {e}")
                
        print(f"Migration completed! Migrated {migrated_count} out of {len(users)} users.")
        
    except Exception as e:
        print(f"Database error during migration: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate_users()
