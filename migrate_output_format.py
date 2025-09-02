#!/usr/bin/env python
"""
Migration script to update output_format values from 'Plain Text' to 'text'
for consistency across the application.
"""

from app import app, db, Template

def migrate_output_format():
    """Update all Template records with 'Plain Text' to 'text'"""
    with app.app_context():
        # Find all templates with 'Plain Text' format
        templates = Template.query.filter_by(output_format='Plain Text').all()
        
        if templates:
            print(f"Found {len(templates)} templates with 'Plain Text' format")
            
            for template in templates:
                template.output_format = 'text'
                print(f"Updated template ID {template.id} for script ID {template.script_id}")
            
            db.session.commit()
            print(f"Successfully migrated {len(templates)} templates")
        else:
            print("No templates found with 'Plain Text' format - nothing to migrate")
        
        # Verify the migration
        remaining = Template.query.filter_by(output_format='Plain Text').count()
        if remaining > 0:
            print(f"WARNING: {remaining} templates still have 'Plain Text' format")
        else:
            print("Migration complete - all templates now use 'text' format")

if __name__ == '__main__':
    migrate_output_format()