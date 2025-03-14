from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import jinja2
import os
import uuid
import sqlalchemy
import json
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional
import tacacs_plus
from tacacs_plus.client import TACACSClient
# from flask_wtf.csrf import CSRFProtect

# Create instance directory if it doesn't exist
instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)
    print(f"Created instance directory at {instance_path}")

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing')

# Use a relative path for SQLite that will work regardless of current directory
db_path = os.path.join(instance_path, 'scripter.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for the entire application

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'
# csrf = CSRFProtect(app)

# Data Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    auth_type = db.Column(db.String(20), default='local')  # 'local' or 'tacacs'
    full_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Script(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    tags = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='draft')  # draft, active, archived
    
    # Relationships
    creator = db.relationship('User', backref='scripts')
    template = db.relationship('Template', backref='script', uselist=False, cascade='all, delete-orphan')
    form_fields = db.relationship('FormField', backref='script', cascade='all, delete-orphan')
    submissions = db.relationship('FormSubmission', backref='script', cascade='all, delete-orphan')

class Template(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, default=1)
    output_format = db.Column(db.String(20), default='Plain Text')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class FormField(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)  # Variable name in template
    label = db.Column(db.String(100), nullable=False)  # Display label
    field_type = db.Column(db.String(20), nullable=False)  # text, textarea, select, etc.
    required = db.Column(db.Boolean, default=False)
    default_value = db.Column(db.Text)
    help_text = db.Column(db.Text)
    validation_rules = db.Column(db.Text)  # JSON or simple rules
    conditional_logic = db.Column(db.Text)  # JSON for conditional display
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FormSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)
    field_values = db.Column(db.Text)  # JSON string of field values
    output = db.Column(db.Text)  # Generated output or reference to it
    
    # Relationship
    user = db.relationship('User', backref='submissions')

class AuthConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    auth_type = db.Column(db.String(20), default='local')  # 'local' or 'tacacs'
    tacacs_server = db.Column(db.String(255))
    tacacs_port = db.Column(db.Integer, default=49)
    tacacs_secret = db.Column(db.String(255))
    tacacs_timeout = db.Column(db.Integer, default=10)
    tacacs_service = db.Column(db.String(50), default='scripter')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    try:
        active_scripts = Script.query.filter_by(status='active').all()
        return render_template('index.html', scripts=active_scripts)
    except Exception as e:
        app.logger.error(f"Error accessing database: {str(e)}")
        # If there's a database error, redirect to setup
        flash('Database not initialized. Please set up the application first.')
        return redirect(url_for('setup'))

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        auth_config = get_auth_config()
        
        # Check if user exists and determine authentication method
        if user and user.auth_type == 'tacacs':
            # TACACS+ authentication
            if authenticate_tacacs(form.username.data, form.password.data):
                login_user(user, remember=form.remember_me.data)
                user.last_login = datetime.utcnow()
                db.session.commit()
                return redirect(url_for('index'))
        elif user and user.auth_type == 'local':
            # Local authentication
            if user.check_password(form.password.data):
                login_user(user, remember=form.remember_me.data)
                user.last_login = datetime.utcnow()
                db.session.commit()
                return redirect(url_for('index'))
        elif not user and auth_config.auth_type == 'tacacs':
            # Try TACACS+ for unknown users if it's the default auth method
            if authenticate_tacacs(form.username.data, form.password.data):
                # Create a new user account for this TACACS+ user
                user = User(
                    username=form.username.data,
                    email=f"{form.username.data}@tacacs.local",  # Placeholder email
                    auth_type='tacacs',
                    is_active=True
                )
                db.session.add(user)
                db.session.commit()
                login_user(user, remember=form.remember_me.data)
                return redirect(url_for('index'))
        
        flash('Invalid username or password')
        return redirect(url_for('login'))
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Admin routes
@app.route('/admin')
@login_required
def admin_dashboard_main():
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('index'))
    
    scripts = Script.query.all()
    submission_count = FormSubmission.query.count()
    return render_template('admin/dashboard.html', scripts=scripts, submission_count=submission_count)

@app.route('/admin/scripts/new', methods=['GET', 'POST'])
@login_required
def create_script():
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        category = request.form.get('category')
        tags = request.form.get('tags')
        
        script = Script(
            name=name,
            description=description,
            category=category,
            tags=tags,
            creator_id=current_user.id
        )
        
        db.session.add(script)
        db.session.commit()
        
        # Create empty template
        template = Template(
            script_id=script.id,
            content="",
            version=1
        )
        
        db.session.add(template)
        db.session.commit()
        
        flash(f'Script "{name}" created successfully')
        return redirect(url_for('edit_script', script_id=script.id))
    
    return render_template('admin/create_script.html')

@app.route('/admin/scripts/<int:script_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_script(script_id):
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('index'))
    
    script = Script.query.get_or_404(script_id)
    
    if request.method == 'POST':
        script.name = request.form.get('name')
        script.description = request.form.get('description')
        script.category = request.form.get('category')
        script.tags = request.form.get('tags')
        script.status = request.form.get('status')
        
        db.session.commit()
        flash(f'Script "{script.name}" updated successfully')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/edit_script.html', script=script)

@app.route('/admin/scripts/<int:script_id>/template', methods=['GET', 'POST'])
@login_required
def edit_template(script_id):
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('index'))
    
    script = Script.query.get_or_404(script_id)
    template = script.template
    
    if request.method == 'POST':
        template_content = request.form.get('content')
        output_format = request.form.get('output_format')
        
        # Increment version
        template.version += 1
        template.content = template_content
        template.output_format = output_format
        
        db.session.commit()
        flash('Template updated successfully')
        
        # Stay on the template page instead of redirecting to edit_script
        return redirect(url_for('edit_template', script_id=script_id))
    
    # Define Jinja2 snippets for the template editor
    jinja_snippets = [
        {
            'name': 'If Condition',
            'code': '{% if condition %}\n    content\n{% endif %}'
        },
        {
            'name': 'If-Else Condition',
            'code': '{% if condition %}\n    content if true\n{% else %}\n    content if false\n{% endif %}'
        },
        {
            'name': 'If-Elif-Else Condition',
            'code': '{% if condition1 %}\n    content if condition1 is true\n{% elif condition2 %}\n    content if condition2 is true\n{% else %}\n    content if all conditions are false\n{% endif %}'
        },
        {
            'name': 'Variable',
            'code': '{{ variable_name }}'
        },
        {
            'name': 'For Loop',
            'code': '{% for item in items %}\n    {{ item }}\n{% endfor %}'
        }
    ]
    
    return render_template('admin/edit_template.html', script=script, template=template, jinja_snippets=jinja_snippets)

@app.route('/scripts/<int:script_id>/fields', methods=['GET'])
@login_required
def manage_fields(script_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    script = Script.query.get_or_404(script_id)
    return render_template('admin/manage_fields.html', script=script)

@app.route('/scripts/<int:script_id>/fields/add', methods=['GET', 'POST'])
@login_required
def add_field(script_id):
    app.logger.info(f"Add/edit field called for script {script_id}")
    
    if not current_user.is_admin:
        app.logger.warning("Access denied - user is not admin")
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    script = Script.query.get_or_404(script_id)
    field_id = request.args.get('edit', None)
    app.logger.info(f"Edit field ID: {field_id}")
    
    field = None
    if field_id:
        field = FormField.query.get_or_404(field_id)
        app.logger.info(f"Found field: {field.name}")
        
        if field.script_id != script.id:
            app.logger.warning(f"Field script_id {field.script_id} doesn't match script.id {script.id}")
            flash('Invalid field ID', 'error')
            return redirect(url_for('manage_fields', script_id=script_id))
    
    if request.method == 'POST':
        app.logger.info(f"POST data: {request.form}")
        try:
            name = request.form.get('name')
            label = request.form.get('label')
            field_type = request.form.get('field_type')
            required = 'required' in request.form
            default_value = request.form.get('default_value', '')
            help_text = request.form.get('help_text', '')
            validation_rules = request.form.get('validation_rules', '')
            conditional_logic = request.form.get('conditional_logic', '')
            
            # Get the highest display order if creating a new field
            if not field:
                max_order = db.session.query(db.func.max(FormField.display_order)).filter_by(script_id=script_id).scalar() or 0
                display_order = max_order + 10
            else:
                display_order = field.display_order
            
            if field:
                # Update existing field
                field.name = name
                field.label = label
                field.field_type = field_type
                field.required = required
                field.default_value = default_value
                field.help_text = help_text
                field.validation_rules = validation_rules
                field.conditional_logic = conditional_logic
            else:
                # Create new field
                field = FormField(
                    script_id=script_id,
                    name=name,
                    label=label,
                    field_type=field_type,
                    required=required,
                    default_value=default_value,
                    help_text=help_text,
                    validation_rules=validation_rules,
                    conditional_logic=conditional_logic,
                    display_order=display_order
                )
                db.session.add(field)
            
            db.session.commit()
            flash(f'Field {"updated" if field_id else "added"} successfully', 'success')
            return redirect(url_for('manage_fields', script_id=script_id))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error adding/editing field: {str(e)}", exc_info=True)
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('admin/add_field.html', script=script, field=field)

# End user routes
@app.route('/scripts/<int:script_id>', methods=['GET', 'POST'])
@login_required
def view_script(script_id):
    script = Script.query.get_or_404(script_id)
    form_fields = FormField.query.filter_by(script_id=script_id).order_by(FormField.display_order).all()
    
    output = None
    submission_id = None
    form_data = {}
    
    if request.method == 'POST':
        # Process form submission
        form_data = request.form.to_dict()
        
        # Generate script from template
        template_content = script.template.content
        jinja_template = jinja2.Template(template_content)
        raw_output = jinja_template.render(**form_data)
        
        # Create header with form name and field values
        header_lines = ["#" * 50]
        header_lines.append(f"### Script - {script.name}")
        
        # Add field names and values
        for field in form_fields:
            value = form_data.get(field.name, '')
            # Truncate long values for the header
            if len(value) > 50:
                value = value[:47] + "..."
            header_lines.append(f"# {field.label} - {value}")
        
        header_lines.append("#" * 50)
        header_lines.append("")  # Empty line after header
        
        # Combine header and output
        output = "\n".join(header_lines) + raw_output
        
        # Save submission
        submission = FormSubmission(
            script_id=script_id,
            user_id=current_user.id,
            field_values=json.dumps(form_data),
            output=output
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id
    
    return render_template(
        'script_form.html', 
        script=script, 
        form_fields=form_fields, 
        output=output, 
        form_data=form_data, 
        submission_id=submission_id,
        is_preview=False,
        form_action=url_for('view_script', script_id=script.id)
    )

@app.route('/scripts/<int:script_id>/submit', methods=['POST'])
def submit_form(script_id):
    script = Script.query.filter_by(id=script_id, status='active').first_or_404()
    
    # Collect form data
    form_data = {}
    for field in script.form_fields:
        form_data[field.name] = request.form.get(field.name, '')
    
    # Process template with form data
    template_content = script.template.content
    try:
        template = jinja2.Template(template_content)
        output = template.render(**form_data)
    except Exception as e:
        flash(f'Error processing template: {str(e)}')
        return redirect(url_for('view_script', script_id=script_id))
    
    # Store submission
    submission = FormSubmission(
        script_id=script_id,
        user_id=current_user.id if current_user.is_authenticated else None,
        field_values=str(form_data),  # In a real app, use proper JSON serialization
        output=output
    )
    
    db.session.add(submission)
    db.session.commit()
    
    # Store in session for preview
    session['preview_output'] = output
    session['submission_id'] = submission.id
    
    return redirect(url_for('preview_output', script_id=script_id))

@app.route('/scripts/<int:script_id>/preview', methods=['GET'])
def preview_output(script_id):
    script = Script.query.filter_by(id=script_id, status='active').first_or_404()
    
    output = session.get('preview_output')
    submission_id = session.get('submission_id')
    
    if not output:
        flash('No preview available')
        return redirect(url_for('view_script', script_id=script_id))
    
    return render_template('preview_output.html', script=script, output=output, submission_id=submission_id)

@app.route('/scripts/<int:script_id>/submissions/<int:submission_id>/download')
def download_submission(script_id, submission_id):
    script = Script.query.get_or_404(script_id)
    submission = FormSubmission.query.get_or_404(submission_id)
    
    # Verify the submission belongs to the script
    if submission.script_id != script_id:
        flash('Invalid submission ID')
        return redirect(url_for('index'))
    
    # Generate file based on template output format
    if script.template.output_format == 'html':
        response = make_response(submission.output)
        response.headers['Content-Type'] = 'text/html'
        response.headers['Content-Disposition'] = f'attachment; filename=script_{script_id}_{submission_id}.html'
    elif script.template.output_format == 'text':
        response = make_response(submission.output)
        response.headers['Content-Type'] = 'text/plain'
        response.headers['Content-Disposition'] = f'attachment; filename=script_{script_id}_{submission_id}.txt'
    elif script.template.output_format == 'markdown':
        response = make_response(submission.output)
        response.headers['Content-Type'] = 'text/markdown'
        response.headers['Content-Disposition'] = f'attachment; filename=script_{script_id}_{submission_id}.md'
    else:
        # Default to plain text for unknown formats
        response = make_response(submission.output)
        response.headers['Content-Type'] = 'text/plain'
        response.headers['Content-Disposition'] = f'attachment; filename=script_{script_id}_{submission_id}.txt'
    return response

# API routes for AJAX operations
@app.route('/api/scripts/<int:script_id>/detect_variables', methods=['POST'])
@login_required
def detect_variables(script_id):
    app.logger.info(f"Detect variables called for script {script_id}")
    app.logger.info(f"Request content type: {request.content_type}")
    app.logger.info(f"Request data: {request.data}")
    
    if not current_user.is_admin:
        app.logger.warning("Access denied - user is not admin")
        return jsonify({'error': 'Access denied'}), 403
    
    # Check if we received JSON data
    if not request.is_json:
        app.logger.warning(f"Expected JSON data but got content type: {request.content_type}")
        return jsonify({'error': 'Expected JSON data'}), 400
    
    try:
        data = request.get_json()
        app.logger.info(f"Parsed JSON data: {data}")
        
        if data is None:
            app.logger.warning("JSON data is None")
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        template_content = data.get('template_content', '')
        app.logger.info(f"Template content length: {len(template_content)}")
        
        # Simple variable detection (a more robust implementation would be needed)
        import re
        variables = set()
        
        # Match {{ variable }} pattern
        variables.update(re.findall(r'\{\{\s*(\w+)\s*\}\}', template_content))
        
        # Also match {{ variable.attribute }} pattern, extracting just the variable part
        for var_with_attr in re.findall(r'\{\{\s*(\w+\.\w+)\s*\}\}', template_content):
            if '.' in var_with_attr:
                variables.add(var_with_attr.split('.')[0])
        
        app.logger.info(f"Detected variables: {variables}")
        return jsonify({'variables': list(variables)})
    except Exception as e:
        app.logger.error(f"Error in detect_variables: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error detecting variables: {str(e)}'}), 500

@app.route('/api/scripts/<int:script_id>/add_variable_field', methods=['POST'])
@login_required
def add_variable_field(script_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    script = Script.query.get_or_404(script_id)
    data = request.json
    variable_name = data.get('variable_name')
    
    if not variable_name:
        return jsonify({'success': False, 'error': 'No variable name provided'})
    
    # Check if field already exists
    existing_field = FormField.query.filter_by(script_id=script_id, name=variable_name).first()
    if existing_field:
        return jsonify({'success': False, 'error': f'Field "{variable_name}" already exists'})
    
    # Get the highest display order
    max_order = db.session.query(db.func.max(FormField.display_order)).filter_by(script_id=script_id).scalar() or 0
    
    # Create a new form field
    field = FormField(
        script_id=script_id,
        name=variable_name,
        label=variable_name.replace('_', ' ').title(),  # Convert snake_case to Title Case
        field_type='text',  # Default to text field
        required=False,
        display_order=max_order + 10  # Add some space between fields
    )
    
    try:
        db.session.add(field)
        db.session.commit()
        return jsonify({'success': True, 'field_id': field.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/scripts/<int:script_id>/fields/<int:field_id>/delete', methods=['POST'])
@login_required
def delete_field(script_id, field_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    field = FormField.query.get_or_404(field_id)
    
    # Verify the field belongs to the script
    if field.script_id != script_id:
        return jsonify({'success': False, 'error': 'Invalid field ID'}), 400
    
    try:
        db.session.delete(field)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('errors/500.html'), 500

@app.errorhandler(sqlalchemy.exc.OperationalError)
def handle_db_error(e):
    app.logger.error(f"Database error: {str(e)}")
    # Check if the error is about missing tables
    if "no such table" in str(e):
        flash('Database tables not found. Please set up the application.')
        return redirect(url_for('setup'))
    return render_template('errors/500.html'), 500

@app.errorhandler(403)
def forbidden_error(e):
    app.logger.error(f"Forbidden access: {str(e)}")
    if not current_user.is_authenticated:
        flash('You need to log in to access this page.')
        return redirect(url_for('login'))
    else:
        return render_template('errors/403.html'), 403

# Initialize database
@app.cli.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    db.create_all()
    print('Initialized the database.')

# Create admin user
@app.cli.command('create-admin')
def create_admin_command():
    """Create an admin user."""
    username = input('Username: ')
    email = input('Email: ')
    password = input('Password: ')
    
    user = User(username=username, email=email, is_admin=True)
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    print(f'Admin user {username} created successfully.')

# Modify the setup route to bypass authentication
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    app.logger.info("Setup route accessed")
    
    # Check if database already exists and has users
    try:
        user_count = User.query.count()
        app.logger.info(f"Found {user_count} users in database")
        if user_count > 0:
            flash('Database is already set up with users. Setup skipped.')
            return redirect(url_for('index'))
    except Exception as e:
        app.logger.info(f"Database not initialized yet: {str(e)}")
        # If there's an error (like no tables exist), we'll proceed with setup
        pass
    
    if request.method == 'POST':
        app.logger.info("Processing setup form submission")
        try:
            # Create all tables
            db.create_all()
            app.logger.info("Created all database tables")
            
            # Create admin user from form data
            username = request.form.get('username', 'admin')
            email = request.form.get('email', 'admin@example.com')
            password = request.form.get('password', 'admin123')
            
            admin_user = User(
                username=username,
                email=email,
                is_admin=True
            )
            admin_user.set_password(password)
            
            db.session.add(admin_user)
            db.session.commit()
            
            app.logger.info(f"Created admin user: {username}")
            flash(f'Database initialized successfully! Admin user "{username}" created.')
            return redirect(url_for('login'))
        except Exception as e:
            app.logger.error(f"Error during setup: {str(e)}")
            flash(f'Error during setup: {str(e)}')
            return render_template('setup.html')
    
    app.logger.info("Rendering setup template")
    return render_template('setup.html')

@app.route('/admin/migrate', methods=['GET', 'POST'])
@login_required
def migrate_database():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    migration_log = []
    
    if request.method == 'POST':
        try:
            # Backup the database first (optional but recommended)
            import shutil
            from datetime import datetime
            
            db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            backup_path = f"{db_path}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            try:
                shutil.copy2(db_path, backup_path)
                migration_log.append(f"Database backed up to {backup_path}")
            except Exception as e:
                migration_log.append(f"Warning: Could not create backup: {str(e)}")
            
            # Get the current schema version (you'd need to add this table)
            try:
                # Use the modern SQLAlchemy approach with connection
                with db.engine.connect() as conn:
                    result = conn.execute(db.text("SELECT version FROM schema_version ORDER BY id DESC LIMIT 1"))
                    current_version = result.fetchone()[0]
            except Exception as e:
                migration_log.append(f"Creating schema_version table: {str(e)}")
                # If the table doesn't exist, create it and set version to 0
                with db.engine.connect() as conn:
                    conn.execute(db.text("CREATE TABLE schema_version (id INTEGER PRIMARY KEY, version INTEGER, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
                    conn.execute(db.text("INSERT INTO schema_version (version) VALUES (0)"))
                    conn.commit()
                    current_version = 0
            
            migration_log.append(f"Current schema version: {current_version}")
            
            # Apply migrations based on current version
            if current_version < 1:
                migration_log.append("Applying migration v1: Initial schema")
                db.create_all()
                with db.engine.connect() as conn:
                    conn.execute(db.text("UPDATE schema_version SET version = 1"))
                    conn.commit()
            
            if current_version < 2:
                migration_log.append("Applying migration v2: Adding conditional_logic to form_field")
                try:
                    with db.engine.connect() as conn:
                        conn.execute(db.text("ALTER TABLE form_field ADD COLUMN conditional_logic TEXT"))
                        conn.commit()
                except Exception as e:
                    migration_log.append(f"Column conditional_logic might already exist: {str(e)}")
                
                with db.engine.connect() as conn:
                    conn.execute(db.text("UPDATE schema_version SET version = 2"))
                    conn.commit()
            
            if current_version < 3:
                migration_log.append("Applying migration v3: Adding created_at to form_field")
                try:
                    with db.engine.connect() as conn:
                        conn.execute(db.text("ALTER TABLE form_field ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                        conn.commit()
                except Exception as e:
                    migration_log.append(f"Column created_at might already exist: {str(e)}")
                
                with db.engine.connect() as conn:
                    conn.execute(db.text("UPDATE schema_version SET version = 3"))
                    conn.commit()
            
            # Get the new version
            with db.engine.connect() as conn:
                result = conn.execute(db.text("SELECT version FROM schema_version ORDER BY id DESC LIMIT 1"))
                new_version = result.fetchone()[0]
            
            migration_log.append(f"New schema version: {new_version}")
            
            flash('Database migration completed successfully!', 'success')
            return render_template('admin/migrate.html', migration_log=migration_log)
            
        except Exception as e:
            migration_log.append(f"Error during migration: {str(e)}")
            flash(f'Error during migration: {str(e)}', 'error')
            return render_template('admin/migrate.html', migration_log=migration_log)
    
    return render_template('admin/migrate.html', migration_log=migration_log)

@app.route('/scripts/<int:script_id>/submissions/<int:submission_id>')
def view_submission(script_id, submission_id):
    script = Script.query.get_or_404(script_id)
    submission = FormSubmission.query.get_or_404(submission_id)
    
    # Verify the submission belongs to the script
    if submission.script_id != script_id:
        flash('Invalid submission ID')
        return redirect(url_for('index'))
    
    # If user is not admin, check if they own the submission
    if not current_user.is_authenticated or (not current_user.is_admin and submission.user_id != current_user.id):
        flash('You do not have permission to view this submission')
        return redirect(url_for('index'))
    
    return render_template('view_submission.html', script=script, submission=submission)

@app.route('/admin/scripts/<int:script_id>/preview', methods=['GET', 'POST'])
@login_required
def script_preview(script_id):
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('index'))
    
    script = Script.query.get_or_404(script_id)
    form_fields = FormField.query.filter_by(script_id=script_id).order_by(FormField.display_order).all()
    
    output = None
    form_data = {}
    
    if request.method == 'POST':
        # Process form submission
        form_data = request.form.to_dict()
        
        # Generate script from template
        template_content = script.template.content
        jinja_template = jinja2.Template(template_content)
        raw_output = jinja_template.render(**form_data)
        
        # Create header with form name and field values
        header_lines = ["#" * 50]
        header_lines.append(f"### Script - {script.name}")
        
        # Add field names and values
        for field in form_fields:
            value = form_data.get(field.name, '')
            # Truncate long values for the header
            if len(value) > 50:
                value = value[:47] + "..."
            header_lines.append(f"# {field.label} - {value}")
        
        header_lines.append("#" * 50)
        header_lines.append("")  # Empty line after header
        
        # Combine header and output
        output = "\n".join(header_lines) + raw_output
    
    return render_template(
        'script_form.html', 
        script=script, 
        form_fields=form_fields, 
        output=output, 
        form_data=form_data,
        submission_id=None,
        is_preview=True,
        form_action=url_for('script_preview', script_id=script.id)
    )

# Add this at the end of the file, before the if __name__ == '__main__': block
with app.app_context():
    try:
        # Check if the script table exists
        Script.query.first()
        app.logger.info("Database tables exist")
    except Exception as e:
        app.logger.info(f"Creating database tables: {str(e)}")
        try:
            # If not, create all tables
            db.create_all()
            app.logger.info("Database tables created automatically on startup")
            
            # Check if we need to create a default admin user
            user_count = User.query.count()
            if user_count == 0:
                app.logger.info("Creating default admin user")
                admin_user = User(
                    username="admin",
                    email="admin@example.com",
                    is_admin=True
                )
                admin_user.set_password("admin123")
                db.session.add(admin_user)
                db.session.commit()
                app.logger.info("Default admin user created")
        except Exception as inner_e:
            app.logger.error(f"Failed to initialize database: {str(inner_e)}")
            print(f"ERROR: Failed to initialize database: {str(inner_e)}")
            print(f"Database path: {db_path}")
            print(f"Directory exists: {os.path.exists(os.path.dirname(db_path))}")
            print(f"Directory is writable: {os.access(os.path.dirname(db_path), os.W_OK)}")

# Add these helper functions
def get_auth_config():
    config = AuthConfig.query.first()
    if not config:
        config = AuthConfig()
        db.session.add(config)
        db.session.commit()
    return config

def authenticate_tacacs(username, password):
    config = get_auth_config()
    if not config.tacacs_server:
        return False
    
    try:
        client = TACACSClient(
            host=config.tacacs_server,
            port=config.tacacs_port,
            secret=config.tacacs_secret.encode(),
            timeout=config.tacacs_timeout
        )
        
        # Authenticate user
        authen = client.authenticate(username, password, config.tacacs_service)
        return authen.valid
    except Exception as e:
        app.logger.error(f"TACACS+ authentication error: {str(e)}")
        return False

# Add user management routes
@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.')
        return redirect(url_for('index'))
    
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.')
        return redirect(url_for('index'))
    
    form = UserForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            full_name=form.full_name.data,
            is_admin=form.is_admin.data,
            is_active=form.is_active.data,
            auth_type=form.auth_type.data
        )
        
        if form.password.data and form.auth_type.data == 'local':
            user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        flash(f'User {user.username} has been created.')
        return redirect(url_for('admin_users'))
    
    return render_template('admin/edit_user.html', form=form, user=None)

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin:
        flash('You do not have permission to access this page.')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    
    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        user.full_name = form.full_name.data
        user.is_admin = form.is_admin.data
        user.is_active = form.is_active.data
        user.auth_type = form.auth_type.data
        
        if form.password.data and form.auth_type.data == 'local':
            user.set_password(form.password.data)
        
        db.session.commit()
        flash(f'User {user.username} has been updated.')
        return redirect(url_for('admin_users'))
    
    return render_template('admin/edit_user.html', form=form, user=user)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('You do not have permission to access this page.')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot delete your own account.')
        return redirect(url_for('admin_users'))
    
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} has been deleted.')
    return redirect(url_for('admin_users'))

@app.route('/admin/auth-config', methods=['GET', 'POST'])
@login_required
def auth_config():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.')
        return redirect(url_for('index'))
    
    config = get_auth_config()
    form = AuthConfigForm(obj=config)
    
    if form.validate_on_submit():
        config.auth_type = form.auth_type.data
        config.tacacs_server = form.tacacs_server.data
        config.tacacs_port = int(form.tacacs_port.data)
        
        if form.tacacs_secret.data:  # Only update if provided
            config.tacacs_secret = form.tacacs_secret.data
            
        config.tacacs_timeout = int(form.tacacs_timeout.data)
        config.tacacs_service = form.tacacs_service.data
        config.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Authentication configuration has been updated.')
        return redirect(url_for('auth_config'))
    
    return render_template('admin/auth_config.html', form=form, config=config)

# Add the TACACS+ test endpoint
@app.route('/admin/test-tacacs', methods=['POST'])
@login_required
def test_tacacs():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'}), 400
    
    config = get_auth_config()
    
    if not config.tacacs_server:
        return jsonify({'success': False, 'message': 'TACACS+ server not configured'}), 400
    
    try:
        result = authenticate_tacacs(username, password)
        if result:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Authentication failed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.')
        return redirect(url_for('index'))
    
    # Add user stats to the dashboard
    user_count = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    admin_users = User.query.filter_by(is_admin=True).count()
    tacacs_users = User.query.filter_by(auth_type='tacacs').count()
    
    # Get existing stats
    script_count = Script.query.count()
    submission_count = FormSubmission.query.count()
    
    return render_template('admin/dashboard.html', 
                          script_count=script_count,
                          submission_count=submission_count,
                          user_count=user_count,
                          active_users=active_users,
                          admin_users=admin_users,
                          tacacs_users=tacacs_users)

# Add these forms
class LoginForm(FlaskForm):
    class Meta:
        csrf = False  # Disable CSRF for this form
    
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')

class UserForm(FlaskForm):
    class Meta:
        csrf = False  # Disable CSRF for this form
    
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[
        Optional(),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        EqualTo('password', message='Passwords must match')
    ])
    full_name = StringField('Full Name', validators=[Optional(), Length(max=100)])
    is_admin = BooleanField('Administrator')
    is_active = BooleanField('Active', default=True)
    auth_type = SelectField('Authentication Type', choices=[
        ('local', 'Local Authentication'),
        ('tacacs', 'TACACS+ Authentication')
    ])

class AuthConfigForm(FlaskForm):
    class Meta:
        csrf = False  # Disable CSRF for this form
    
    auth_type = SelectField('Default Authentication Method', choices=[
        ('local', 'Local Authentication'),
        ('tacacs', 'TACACS+ Authentication')
    ])
    tacacs_server = StringField('TACACS+ Server', validators=[Optional()])
    tacacs_port = StringField('TACACS+ Port', default='49', validators=[Optional()])
    tacacs_secret = PasswordField('TACACS+ Secret', validators=[Optional()])
    tacacs_timeout = StringField('TACACS+ Timeout (seconds)', default='10', validators=[Optional()])
    tacacs_service = StringField('TACACS+ Service Name', default='scripter', validators=[Optional()])

# Add the missing admin_scripts route
@app.route('/admin/scripts')
@login_required
def admin_scripts():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.')
        return redirect(url_for('index'))
    
    scripts = Script.query.all()
    return render_template('admin/manage_scripts.html', scripts=scripts)

# Add the missing delete_script route
@app.route('/admin/scripts/<int:script_id>/delete', methods=['POST'])
@login_required
def delete_script(script_id):
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('index'))
    
    script = Script.query.get_or_404(script_id)
    
    try:
        # Delete the script (cascade will handle related records)
        db.session.delete(script)
        db.session.commit()
        flash(f'Script "{script.name}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting script: {str(e)}', 'error')
    
    return redirect(url_for('admin_scripts'))

if __name__ == '__main__':
    app.run(debug=True)
