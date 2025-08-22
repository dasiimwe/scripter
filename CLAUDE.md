# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scripter is a Flask-based web application that enables administrators to create custom forms with Jinja2 templates. End users can fill out these forms to generate customized configuration scripts and documents. The system manages multiple scripts, each consisting of a template and its associated form fields.

## Tech Stack

- **Backend**: Python Flask
- **Database**: SQLAlchemy with SQLite
- **Template Engine**: Jinja2 (for both app templates and user-created templates)
- **Authentication**: Flask-Login with support for local and TACACS+ authentication
- **Frontend**: HTML templates with Bulma CSS framework
- **Forms**: Flask-WTF/WTForms for form handling

## Development Commands

### Running the Application

```bash
# Activate virtual environment (required)
source ../venv/bin/activate

# Run Flask development server
python app.py
```

The app runs on http://localhost:5000 in debug mode by default.

### Database Management

```bash
# Run database migrations
python migrate_db.py
```

## Application Architecture

### Core Components

1. **Script Management System** (`/admin/scripts/*`)
   - Create, edit, and manage scripts (templates + form definitions)
   - Scripts have status: draft, active, or archived
   - Scripts can be organized by category and tags

2. **Template Editor** (`/admin/scripts/<id>/template`)
   - Jinja2 template creation and editing
   - Variable detection from templates
   - Template validation and preview capabilities

3. **Form Builder** (`/scripts/<id>/fields/*`)
   - Dynamic form field creation
   - Multiple field types: text, textarea, select, checkbox, number, date, email, url, password
   - Field validation rules and conditional logic
   - Auto-generation of fields from template variables

4. **Form Renderer** (`/scripts/<id>`)
   - Public-facing forms for end users
   - Real-time validation
   - Preview before submission

5. **Authentication System**
   - Local user authentication with password hashing
   - TACACS+ authentication support
   - Role-based access (admin vs regular user)
   - Initial setup wizard at `/setup` for first admin user

### Database Models

- **User**: Authentication and user management
- **Script**: Main entity containing templates and forms
- **Template**: Jinja2 template content for each script
- **FormField**: Field definitions for script forms
- **FormSubmission**: Stores user submissions and generated output
- **AuthConfig**: Authentication configuration (TACACS+ settings)

### Key Routes

- `/` - Public homepage listing available scripts
- `/login`, `/logout` - Authentication
- `/setup` - Initial admin setup
- `/admin` - Admin dashboard
- `/admin/scripts/*` - Script management
- `/scripts/<id>` - Public form for a script
- `/scripts/<id>/preview` - Preview generated output
- `/api/scripts/<id>/detect_variables` - API to detect Jinja2 variables
- `/admin/migrate` - Database migration interface

### Frontend Structure

- `templates/` - Flask HTML templates
  - `admin/` - Admin interface templates
  - `errors/` - Error pages (403, 404, 500)
  - `partials/` - Reusable template components
- `static/`
  - `css/styles.css` - Custom styles on top of Bulma
  - `js/main.js` - Core JavaScript functionality
  - `js/script-form.js` - Form handling logic
  - `js/template-editor.js` - Template editing features

## Security Considerations

- CSRF protection is currently disabled (`WTF_CSRF_ENABLED = False`)
- Password hashing using Werkzeug security
- Login required decorators for admin routes
- Input sanitization for Jinja2 template processing
- SQL injection protection via SQLAlchemy ORM

## Important Implementation Details

1. **Database Initialization**: The app automatically creates an `instance/` directory for the SQLite database if it doesn't exist

2. **Jinja2 Template Processing**: The app uses Jinja2 both for its own templates and for processing user-created templates with form data

3. **Variable Detection**: The system can automatically detect variables in Jinja2 templates and suggest form fields

4. **Authentication Flow**: 
   - First-time setup requires creating an admin user via `/setup`
   - Supports both local and TACACS+ authentication methods
   - User roles: admin (full access) and regular user (form submission only)

5. **Form Field Types**: Extensive support for HTML5 input types with validation

6. **Script Workflow**: Draft → Active → Archived status management for scripts