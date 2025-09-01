#!/usr/bin/env python3
"""
Database Migration Script for Scripter Application

This script updates the database schema to include user management and TACACS+ authentication.
It creates a backup of the existing database before making any changes.
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Database paths
INSTANCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
DB_PATH = os.path.join(INSTANCE_DIR, 'scripter.db')
BACKUP_DIR = os.path.join(INSTANCE_DIR, 'backups')

def backup_database():
    """Create a backup of the current database"""
    if not os.path.exists(DB_PATH):
        logger.error(f"Database file not found at {DB_PATH}")
        return False
    
    # Create backup directory if it doesn't exist
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        logger.info(f"Created backup directory at {BACKUP_DIR}")
    
    # Create a timestamped backup file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'scripter_backup_{timestamp}.db')
    
    try:
        shutil.copy2(DB_PATH, backup_path)
        logger.info(f"Database backup created at {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create database backup: {str(e)}")
        return False

def check_column_exists(conn, table, column):
    """Check if a column exists in a table"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [info[1] for info in cursor.fetchall()]
    return column in columns

def check_table_exists(conn, table):
    """Check if a table exists in the database"""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None

def migrate_database():
    """Perform the database migration"""
    if not os.path.exists(DB_PATH):
        logger.error(f"Database file not found at {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Start a transaction
        conn.execute("BEGIN TRANSACTION")
        
        # 1. Update User table with new fields
        if check_table_exists(conn, 'user'):
            logger.info("Updating User table...")
            
            # Add new columns to User table if they don't exist
            new_columns = [
                ('auth_type', 'VARCHAR(20) DEFAULT "local"'),
                ('full_name', 'VARCHAR(100)'),
                ('created_at', 'DATETIME'),
                ('last_login', 'DATETIME'),
                ('is_active', 'BOOLEAN DEFAULT 1')
            ]
            
            for col_name, col_def in new_columns:
                if not check_column_exists(conn, 'user', col_name):
                    cursor.execute(f"ALTER TABLE user ADD COLUMN {col_name} {col_def}")
                    logger.info(f"Added column {col_name} to User table")
        else:
            logger.warning("User table not found. It will be created when the app runs.")
        
        # 2. Create AuthConfig table if it doesn't exist
        if not check_table_exists(conn, 'auth_config'):
            logger.info("Creating AuthConfig table...")
            cursor.execute('''
            CREATE TABLE auth_config (
                id INTEGER PRIMARY KEY,
                auth_type VARCHAR(20) DEFAULT 'local',
                tacacs_server VARCHAR(255),
                tacacs_port INTEGER DEFAULT 49,
                tacacs_secret VARCHAR(255),
                tacacs_timeout INTEGER DEFAULT 10,
                tacacs_service VARCHAR(50) DEFAULT 'scripter',
                created_at DATETIME,
                updated_at DATETIME
            )
            ''')
            
            # Insert default record
            cursor.execute('''
            INSERT INTO auth_config (auth_type, created_at, updated_at)
            VALUES ('local', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''')
            logger.info("Created AuthConfig table with default settings")
        
        # 3. Add script_instructions column to Script table
        if check_table_exists(conn, 'script'):
            if not check_column_exists(conn, 'script', 'script_instructions'):
                logger.info("Adding script_instructions column to Script table...")
                cursor.execute("ALTER TABLE script ADD COLUMN script_instructions TEXT")
                logger.info("Added script_instructions column to Script table")
            else:
                logger.info("script_instructions column already exists in Script table")
        
        # 4. Update any references from Submission to FormSubmission if needed
        if check_table_exists(conn, 'submission') and not check_table_exists(conn, 'form_submission'):
            logger.info("Renaming Submission table to FormSubmission...")
            cursor.execute('''
            ALTER TABLE submission RENAME TO form_submission
            ''')
            logger.info("Renamed Submission table to FormSubmission")
        
        # Commit the transaction
        conn.commit()
        logger.info("Database migration completed successfully")
        return True
        
    except Exception as e:
        # Rollback in case of error
        conn.rollback()
        logger.error(f"Migration failed: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def main():
    """Main function to run the migration"""
    logger.info("Starting database migration...")
    
    # Check if database exists
    if not os.path.exists(DB_PATH):
        logger.error(f"Database file not found at {DB_PATH}")
        logger.info("The database will be created when you run the application.")
        return
    
    # Backup the database
    if not backup_database():
        logger.error("Migration aborted due to backup failure")
        return
    
    # Perform the migration
    if migrate_database():
        logger.info("Migration completed successfully")
    else:
        logger.error("Migration failed. Please restore from backup.")

if __name__ == "__main__":
    main() 