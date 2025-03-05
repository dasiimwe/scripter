from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import jinja2
import os
import uuid
import sqlalchemy
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
app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for debugging

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
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
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
    output_format = db.Column(db.String(20), default='html')
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
    app.logger.info("Login route accessed")
    
    if current_user.is_authenticated:
        app.logger.info(f"User {current_user.username} already authenticated, redirecting to index")
        return redirect(url_for('index'))
    
    # Check if database is initialized
    try:
        user_count = User.query.count()
        app.logger.info(f"Found {user_count} users in database")
        if user_count == 0:
            app.logger.info("No users found, redirecting to setup")
            flash('No users found. Please set up the application first.')
            return redirect(url_for('setup'))
    except Exception as e:
        app.logger.error(f"Database error in login route: {str(e)}")
        # If there's a database error, redirect to setup
        flash('Database not initialized. Please set up the application first.')
        return redirect(url_for('setup'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        app.logger.info(f"Login attempt for user: {username}")
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            app.logger.info(f"Login successful for user: {username}")
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            app.logger.warning(f"Login failed for user: {username}")
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Admin routes
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('index'))
    
    scripts = Script.query.all()
    return render_template('admin/dashboard.html', scripts=scripts)

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
def view_script(script_id):
    script = Script.query.get_or_404(script_id)
    
    # Check if script is active
    if script.status != 'active' and not (current_user.is_authenticated and current_user.is_admin):
        flash('This script is not currently available.')
        return redirect(url_for('index'))
    
    # Get form fields sorted by display order
    form_fields = FormField.query.filter_by(script_id=script_id).order_by(FormField.display_order).all()
    
    # Initialize variables for the template
    output = None
    form_data = {}
    submission_id = None
    
    # Check if we're loading a previous submission
    load_submission_id = request.args.get('load_submission')
    if load_submission_id:
        try:
            submission = FormSubmission.query.get(load_submission_id)
            if submission and submission.script_id == script_id:
                import json
                form_data = json.loads(submission.field_values)
                output = submission.output
                submission_id = submission.id
        except Exception as e:
            app.logger.error(f"Error loading submission: {str(e)}")
    
    if request.method == 'POST':
        # Collect form data
        form_data = {}
        for field in form_fields:
            value = request.form.get(field.name, '')
            form_data[field.name] = value
        
        # Store form data as JSON
        import json
        field_values_json = json.dumps(form_data)
        
        try:
            # Process template with form data
            template_content = script.template.content
            template = jinja2.Template(template_content)
            output = template.render(**form_data)
            
            # Create submission record
            submission = FormSubmission(
                script_id=script_id,
                user_id=current_user.id if current_user.is_authenticated else None,
                field_values=field_values_json,
                output=output
            )
            
            db.session.add(submission)
            db.session.commit()
            submission_id = submission.id
            
            # If AJAX request, return JSON response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'output': output,
                    'submission_id': submission_id
                })
            
            # Otherwise, render the template with the output
            # We don't redirect so the user stays on the same page
        except Exception as e:
            app.logger.error(f"Error processing template: {str(e)}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 400
            flash(f'Error processing template: {str(e)}')
    
    # Render the template with the form and output
    return render_template(
        'script_preview.html', 
        script=script, 
        form_fields=form_fields, 
        output=output,
        form_data=form_data,
        submission_id=submission_id
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

if __name__ == '__main__':
    app.run(debug=True)
