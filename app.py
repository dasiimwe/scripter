from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

def _utcnow():
    """Naive UTC datetime — preserves the pre-existing naive-UTC semantics
    of stored timestamps while avoiding the deprecated `_utcnow()`."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
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
import difflib
import re
import csv as _csv
import io
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
    created_at = db.Column(db.DateTime, default=_utcnow)
    last_login = db.Column(db.DateTime)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Script(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), index=True)  # stable cross-instance identity
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    tags = db.Column(db.String(200))
    script_instructions = db.Column(db.Text)  # rich HTML (Trix) — shown to end users on Run
    created_at = db.Column(db.DateTime, default=_utcnow)
    modified_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='draft')  # draft, active, archived

    # Relationships
    creator = db.relationship('User', backref='scripts')
    template = db.relationship('Template', backref='script', uselist=False, cascade='all, delete-orphan')
    form_fields = db.relationship('FormField', backref='script', cascade='all, delete-orphan')
    submissions = db.relationship('FormSubmission', backref='script', cascade='all, delete-orphan')
    changes = db.relationship('ScriptChange', backref='script', cascade='all, delete-orphan', order_by='ScriptChange.change_date.desc()')
    generated_scripts = db.relationship('GeneratedScript', backref='original_script', cascade='all, delete-orphan')

class Template(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, default=1)
    output_format = db.Column(db.String(20), default='Plain Text')
    created_at = db.Column(db.DateTime, default=_utcnow)
    modified_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

class FormField(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)  # Variable name in template
    label = db.Column(db.String(100), nullable=False)  # Display label
    field_type = db.Column(db.String(30), nullable=False)  # see FIELD_TYPES
    required = db.Column(db.Boolean, default=False)
    default_value = db.Column(db.Text)
    help_text = db.Column(db.Text)
    validation_rules = db.Column(db.Text)
    conditional_logic = db.Column(db.Text)
    field_config = db.Column(db.Text)  # JSON: {options, min, max, step, pattern, placeholder, rows}
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow)

class FormSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    submission_date = db.Column(db.DateTime, default=_utcnow)
    field_values = db.Column(db.Text)  # JSON string of field values
    output = db.Column(db.Text)  # Generated output or reference to it
    
    # Relationship
    user = db.relationship('User', backref='submissions')

class AuthConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    auth_type = db.Column(db.String(20), default='local')  # 'local' or 'tacacs'
    auth_enabled = db.Column(db.Boolean, default=False)  # default: open mode. User runs /install or Auth page to enable auth.
    tacacs_server = db.Column(db.String(255))
    tacacs_port = db.Column(db.Integer, default=49)
    tacacs_secret = db.Column(db.String(255))
    tacacs_timeout = db.Column(db.Integer, default=10)
    tacacs_service = db.Column(db.String(50), default='scripter')
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

class ScriptChange(db.Model):
    """Append-only audit log of edits to a script and its children."""
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    change_type = db.Column(db.String(50), nullable=False)  # script_edit, template_edit, field_add, field_edit, field_delete
    change_date = db.Column(db.DateTime, default=_utcnow, index=True)
    field_name = db.Column(db.String(100))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    description = db.Column(db.Text)

    user = db.relationship('User', backref='script_changes')

class GeneratedScript(db.Model):
    """A rendered output from a Script. Acts as the user-visible library entry."""
    id = db.Column(db.Integer, primary_key=True)
    original_script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(200), nullable=False)
    generated_content = db.Column(db.Text, nullable=False)
    csv_row_data = db.Column(db.Text)   # JSON blob of the input values
    batch_id = db.Column(db.String(50), index=True)  # groups bulk runs
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    modified_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    user = db.relationship('User', backref='generated_scripts')

class FormDraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    field_values = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    
    # Relationships
    script = db.relationship('Script', backref='drafts')
    user = db.relationship('User', backref='form_drafts')

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------------------------------------------------------------------
# Auth toggle + permission helpers
# ---------------------------------------------------------------------------
# Env override wins. If unset, the effective state comes from AuthConfig.auth_enabled.
# Values: 'true'/'1'/'yes' -> force on, 'false'/'0'/'no' -> force off, unset -> DB.
_AUTH_ENV = os.environ.get('AUTH_ENABLED', '').strip().lower()
LOCAL_USERNAME = 'local'

def _env_override():
    if _AUTH_ENV in ('1', 'true', 'yes', 'on'):
        return True
    if _AUTH_ENV in ('0', 'false', 'no', 'off'):
        return False
    return None

def is_auth_enabled():
    override = _env_override()
    if override is not None:
        return override
    # Cache per-request: this is called from before_request, the context
    # processor, maybe_login_required, and several views. Without caching,
    # every workbench GET runs `SELECT * FROM auth_config LIMIT 1` 4-5 times.
    try:
        if 'auth_enabled' in g:
            return g.auth_enabled
    except RuntimeError:
        pass  # outside request context (e.g., during `flask shell`)
    try:
        cfg = AuthConfig.query.first()
        # Default on fresh install is OPEN (no login). Existing cfg rows win.
        val = False if cfg is None else bool(cfg.auth_enabled)
    except Exception:
        val = True  # fail closed on DB error: require auth rather than accidentally expose
    try:
        g.auth_enabled = val
    except RuntimeError:
        pass
    return val

def ensure_local_user():
    """Seed the shared 'local' user used when auth is disabled. Idempotent."""
    user = User.query.filter_by(username=LOCAL_USERNAME).first()
    if user is None:
        user = User(
            username=LOCAL_USERNAME,
            email='local@scripter.local',
            full_name='Local User',
            is_admin=True,
            is_active=True,
            auth_type='local',
        )
        user.set_password(uuid.uuid4().hex)  # unusable password; never logged in via form
        db.session.add(user)
        db.session.commit()
    return user

@app.before_request
def auto_login_local_user():
    """In no-auth mode, transparently log in as the shared local user."""
    if not is_auth_enabled():
        if not current_user.is_authenticated:
            try:
                user = ensure_local_user()
                login_user(user)
            except Exception as e:
                app.logger.warning(f"auto_login failed: {e}")

def maybe_login_required(view):
    """login_required when auth is on; pass-through when off."""
    from functools import wraps
    @wraps(view)
    def wrapper(*args, **kwargs):
        if is_auth_enabled():
            return login_required(view)(*args, **kwargs)
        return view(*args, **kwargs)
    return wrapper

def _viewer_sees_all():
    """True when the current request should see every row regardless of ownership:
    auth disabled (open mode) or authenticated admin."""
    if not is_auth_enabled():
        return True
    return bool(current_user.is_authenticated and current_user.is_admin)

def can_admin(user):
    """Who can see Settings (Users, Auth Config)? Never in no-auth mode — those pages
    are meaningless without real identities."""
    if not is_auth_enabled():
        return False
    return bool(user and getattr(user, 'is_authenticated', False) and user.is_admin)

def can_edit(user, script):
    """Who can add/edit/delete scripts?

    TODO(you): implement this. Rules to encode:
      1. If auth is disabled (is_auth_enabled() == False), everyone can edit.
      2. Otherwise, admins can edit any script.
      3. Otherwise, only the script's creator can edit their own.

    Return True or False.
    """
    if not is_auth_enabled():
        return True
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_admin:
        return True
    return script is not None and script.creator_id == user.id

@app.context_processor
def inject_auth_helpers():
    """Make helpers usable inside Jinja templates."""
    return dict(
        auth_enabled=is_auth_enabled(),
        can_admin=can_admin,
        can_edit=can_edit,
        _AUTH_ENV_ACTIVE=(_env_override() is not None),
    )

# ---------------------------------------------------------------------------
# Audit log + diff + template-variable helpers
# ---------------------------------------------------------------------------
CHANGE_TYPE_LABELS = {
    'script_edit':   'Script',
    'template_edit': 'Template',
    'field_add':     'Field added',
    'field_edit':    'Field edited',
    'field_delete':  'Field removed',
}

def _log_change(script_id, change_type, field_name=None, old=None, new=None, description=None):
    """Append a ScriptChange row. Caller is responsible for db.session.commit()."""
    if old is None and new is None and description is None:
        return  # nothing meaningful to record
    uid = current_user.id if current_user.is_authenticated else None
    db.session.add(ScriptChange(
        script_id=script_id,
        user_id=uid,
        change_type=change_type,
        field_name=field_name,
        old_value=None if old is None else str(old),
        new_value=None if new is None else str(new),
        description=description,
    ))

def generate_diff(old_text, new_text):
    """Return a list of {type, content} dicts for templated rendering of a unified diff."""
    old_lines = (old_text or '').splitlines(keepends=True)
    new_lines = (new_text or '').splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile='Previous', tofile='Current', lineterm=''
    )
    out = []
    for line in diff:
        if line.startswith('+++') or line.startswith('---'):
            continue
        if line.startswith('@@'):
            out.append({'type': 'header',  'content': line})
        elif line.startswith('+'):
            out.append({'type': 'add',     'content': line[1:]})
        elif line.startswith('-'):
            out.append({'type': 'delete',  'content': line[1:]})
        elif line.startswith(' '):
            out.append({'type': 'context', 'content': line[1:]})
        else:
            out.append({'type': 'context', 'content': line})
    return out

# ---------------------------------------------------------------------------
# Template-time IP value wrapper
# ---------------------------------------------------------------------------
# Form fields typed ipv4_address / ipv6_address / cidr get their string value
# wrapped in this object before it reaches jinja_template.render(). Users can
# then write {{ site_ip.first }}, {{ site_ip.netmask }}, etc. Bare {{ site_ip }}
# still renders the raw input verbatim.
import ipaddress as _ipaddress

_IP_TYPES = frozenset({'ipv4_address', 'ipv6_address', 'cidr'})

class IPValue:
    """Smart proxy around a user-entered IP string.

    Accepts bare addresses, CIDRs, and host-within-subnet specs. Parse failures
    are tolerated: `str(IPValue(bad))` returns the original input; derived
    attributes return ''. The Jinja render never crashes on a bad IP value.
    """

    def __init__(self, raw):
        self._raw = '' if raw is None else str(raw)
        self._iface = None
        self._net = None
        self._host = None
        if self._raw:
            try:
                spec = self._raw if '/' in self._raw else f'{self._raw}/{32 if _ipaddress.ip_address(self._raw).version == 4 else 128}'
                self._iface = _ipaddress.ip_interface(spec)
                self._net = self._iface.network
                self._host = self._iface.ip
            except ValueError:
                pass

    def __str__(self):     return self._raw
    def __repr__(self):    return self._raw
    def __bool__(self):    return bool(self._raw)
    def __html__(self):    return self._raw  # Jinja safe-markup hook

    def _safe(self, fn, v4_only=False):
        if self._net is None:
            return ''
        if v4_only and self._net.version != 4:
            return ''
        try:
            return fn()
        except Exception:
            return ''

    # --- address / subnet identity ---
    @property
    def address(self):   return self._safe(lambda: str(self._host))
    @property
    def network(self):   return self._safe(lambda: str(self._net.network_address))
    @property
    def netmask(self):   return self._safe(lambda: str(self._net.netmask))
    @property
    def wildcard(self):  return self._safe(lambda: str(self._net.hostmask), v4_only=True)
    @property
    def hostmask(self):  return self.wildcard
    @property
    def broadcast(self): return self._safe(lambda: str(self._net.broadcast_address), v4_only=True)
    @property
    def cidr(self):      return self._safe(lambda: str(self._net))
    @property
    def host_cidr(self):
        # Host IP with the network prefix, e.g. '192.168.1.5/24'.
        # For a bare /32 or /128 this equals .address + '/32' (or '/128').
        return self._safe(lambda: str(self._iface))
    @property
    def prefix(self):    return self._safe(lambda: self._net.prefixlen)

    # --- usable host range ---
    @property
    def first(self):
        def _f():
            n = self._net
            full = 32 if n.version == 4 else 128
            if n.prefixlen == full:
                return str(n.network_address)
            if n.version == 4 and n.prefixlen == 31:
                return str(list(n.hosts())[0])
            return str(n.network_address + 1)
        return self._safe(_f)

    @property
    def last(self):
        def _l():
            n = self._net
            full = 32 if n.version == 4 else 128
            if n.prefixlen == full:
                return str(n.network_address)
            if n.version == 4:
                if n.prefixlen == 31:
                    return str(list(n.hosts())[-1])
                return str(n.broadcast_address - 1)
            return str(n.broadcast_address)
        return self._safe(_l)

    @property
    def hosts(self):
        def _c():
            n = self._net
            full = 32 if n.version == 4 else 128
            if n.prefixlen == full:
                return 1
            if n.version == 4:
                if n.prefixlen == 31:
                    return 2
                return n.num_addresses - 2
            return n.num_addresses - 1
        return self._safe(_c)

    @property
    def size(self):      return self._safe(lambda: self._net.num_addresses)
    @property
    def version(self):   return self._safe(lambda: self._net.version)

    # --- classification ---
    @property
    def is_private(self):    return self._safe(lambda: self._net.is_private)
    @property
    def is_global(self):     return self._safe(lambda: self._net.is_global)
    @property
    def is_loopback(self):   return self._safe(lambda: self._net.is_loopback)
    @property
    def is_multicast(self):  return self._safe(lambda: self._net.is_multicast)
    @property
    def is_link_local(self): return self._safe(lambda: self._net.is_link_local)

    # --- DNS / canonical forms ---
    @property
    def reverse_pointer(self): return self._safe(lambda: self._host.reverse_pointer)
    @property
    def exploded(self):        return self._safe(lambda: self._host.exploded)
    @property
    def compressed(self):      return self._safe(lambda: self._host.compressed)


_VAR_RE       = re.compile(r'\{\{\s*(\w+)\s*\}\}')
_VAR_ATTR_RE  = re.compile(r'\{\{\s*(\w+)\.\w+\s*\}\}')

def _detect_template_variables(content):
    """Return the set of undeclared variable names the template references.

    Uses Jinja's AST walker (meta.find_undeclared_variables) so references
    inside `{% if %}`, `{% for x in y %}`, `{% set z = w %}` and all other
    tag forms are caught — not just `{{ }}` output expressions. Loop-local
    and set-local variables are correctly excluded.

    Falls back to regex if the template has a syntax error (so the user can
    still see the partial picture while they fix it).
    """
    if not content:
        return set()
    try:
        from jinja2 import Environment, meta
        parsed = Environment().parse(content)
        return set(meta.find_undeclared_variables(parsed))
    except Exception:
        found = set(_VAR_RE.findall(content))
        found.update(_VAR_ATTR_RE.findall(content))
        return found

@app.template_filter('from_json')
def _from_json_filter(value):
    try:
        return json.loads(value) if value else {}
    except (ValueError, TypeError):
        return {}

def _build_output_header(script, form_data, form_fields, batch_id=None, row_num=None, total_rows=None):
    """Standard comment-header prepended to every rendered output.

    Used by both single-run (workbench_run) and bulk-generate (wb_bulk_generate)
    so both outputs look identical and are traceable back to their inputs.
    """
    rule_eq = '# ' + '=' * 64
    rule_hy = '# ' + '-' * 64
    lines = [rule_eq]
    lines.append(f'# {script.name}   (#{script.id:04d})')
    lines.append(f'# Generated {_utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC')
    if batch_id:
        tail = f'  ·  row {row_num} of {total_rows}' if (row_num and total_rows) else ''
        lines.append(f'# Batch {batch_id}{tail}')
    if form_fields:
        lines.append(rule_hy)
        pad = max((len(f.label or '') for f in form_fields), default=0)
        for f in form_fields:
            raw = form_data.get(f.name, '')
            val = ', '.join(str(x) for x in raw) if isinstance(raw, list) else str(raw)
            if len(val) > 56:
                val = val[:53] + '...'
            lines.append(f'# {(f.label or f.name).ljust(pad)}   {val}')
    lines.append(rule_eq)
    lines.append('')
    return '\n'.join(lines)

def _safe_filename(name, fallback):
    """Make a filesystem-friendly filename component from user-supplied text."""
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name or '') or fallback

def _text_download(body, filename, mime='text/plain'):
    resp = make_response(body)
    resp.headers['Content-Type'] = f'{mime}; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp

# ---------------------------------------------------------------------------
# Form field type registry
# ---------------------------------------------------------------------------
# Each entry: (value, label, group, {sections: set, multi: bool, html_input: str})
# sections -- which config panels apply in the edit UI:
#   'options'    — list of {value,label}
#   'numeric'    — min/max/step
#   'datetime'   — min/max (date/time/datetime-local)
#   'textbox'    — pattern + placeholder  (single-line free text)
#   'textarea'   — rows + placeholder
#   'network'    — informational note, no user config
NETWORK_PATTERNS = {
    'ipv4_address': r'^((25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(25[0-5]|2[0-4]\d|1?\d?\d)$',
    'ipv6_address': r'^[0-9a-fA-F:]+$',
    'cidr':         r'^[0-9a-fA-F\.:]+/\d{1,3}$',
    'mac_address':  r'^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$|^([0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4}$',
    'hostname':     r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$',
}

FIELD_TYPES = [
    # (value, label, group, sections, multi)
    ('text',           'Text',                 'Core',    {'textbox'},  False),
    ('textarea',       'Textarea',             'Core',    {'textarea'}, False),
    ('password',       'Password',             'Core',    set(),        False),
    ('email',          'Email',                'Core',    set(),        False),
    ('url',            'URL',                  'Core',    set(),        False),
    ('tel',            'Phone',                'Core',    {'textbox'},  False),
    ('number',         'Number',               'Core',    {'numeric'},  False),
    ('range',          'Range slider',         'Core',    {'numeric'},  False),
    ('date',           'Date',                 'Core',    {'datetime'}, False),
    ('time',           'Time',                 'Core',    {'datetime'}, False),
    ('datetime',       'Date + time',          'Core',    {'datetime'}, False),
    ('color',          'Color',                'Core',    set(),        False),

    ('select',         'Dropdown (single)',    'Choice',  {'options'},  False),
    ('multiselect',    'Dropdown (multiple)',  'Choice',  {'options'},  True),
    ('radio',          'Radio buttons',        'Choice',  {'options'},  False),
    ('checkbox_group', 'Checkbox group',       'Choice',  {'options'},  True),
    ('checkbox',       'Single checkbox',      'Choice',  set(),        False),

    ('ipv4_address',   'IPv4 address',         'Network', {'network'},  False),
    ('ipv6_address',   'IPv6 address',         'Network', {'network'},  False),
    ('cidr',           'CIDR (addr/prefix)',   'Network', {'network'},  False),
    ('mac_address',    'MAC address',          'Network', {'network'},  False),
    ('hostname',       'Hostname',             'Network', {'network'},  False),
]

_MULTI_VALUE_TYPES = {'multiselect', 'checkbox_group'}

def _field_is_multi(field_type):
    return field_type in _MULTI_VALUE_TYPES

def _build_field_config(form):
    """Collect type-specific config keys from a form submission into a dict.
    Server is permissive: stores whatever the client sent, ignores empty keys."""
    cfg = {}
    def _num(k):
        v = (form.get(k) or '').strip()
        if v == '':
            return None
        try:
            return int(v) if '.' not in v else float(v)
        except ValueError:
            return None

    for key in ('config_min', 'config_max', 'config_step'):
        v = _num(key)
        if v is not None:
            cfg[key.replace('config_', '')] = v
    for key in ('config_pattern', 'config_placeholder'):
        v = (form.get(key) or '').strip()
        if v:
            cfg[key.replace('config_', '')] = v
    rows = _num('config_rows')
    if rows is not None:
        cfg['rows'] = rows

    opt_values = form.getlist('option_value')
    opt_labels = form.getlist('option_label')
    options = []
    for v, l in zip(opt_values, opt_labels):
        v = (v or '').strip()
        if not v:
            continue
        options.append({'value': v, 'label': (l or '').strip() or v})
    if options:
        cfg['options'] = options
    return cfg

@app.context_processor
def inject_field_types():
    # Group FIELD_TYPES for the edit UI's <optgroup> rendering.
    groups = {}
    for t in FIELD_TYPES:
        groups.setdefault(t[2], []).append(t)
    return dict(
        FIELD_TYPES=FIELD_TYPES,
        FIELD_TYPE_GROUPS=groups,
        NETWORK_PATTERNS=NETWORK_PATTERNS,
    )

# One-time additive schema patches for SQLite: add columns if missing.
def _ensure_column(table, column, ddl):
    try:
        with db.engine.connect() as conn:
            cols = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")]
            if cols and column not in cols:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {ddl}")
                conn.commit()
                app.logger.info(f"Migrated: added {table}.{column}")
    except Exception as e:
        app.logger.warning(f"migration {table}.{column} skipped: {e}")

def _startup_migrations():
    _ensure_column('auth_config', 'auth_enabled', 'auth_enabled BOOLEAN DEFAULT 1')
    _ensure_column('script',      'script_instructions', 'script_instructions TEXT')
    _ensure_column('script',      'uuid', 'uuid VARCHAR(36)')
    _ensure_column('form_field',  'field_config', 'field_config TEXT')
    _backfill_script_uuids()

def _backfill_script_uuids():
    try:
        missing = Script.query.filter(Script.uuid.is_(None)).all()
        if not missing:
            return
        for s in missing:
            s.uuid = str(uuid.uuid4())
        db.session.commit()
        app.logger.info(f'Backfilled uuid for {len(missing)} existing scripts')
    except Exception as e:
        app.logger.warning(f'uuid backfill skipped: {e}')

with app.app_context():
    try:
        db.create_all()
        _startup_migrations()
    except Exception as e:
        app.logger.warning(f"startup schema init skipped: {e}")

# Routes
@app.route('/')
def index():
    try:
        Script.query.limit(1).all()
    except Exception as e:
        app.logger.error(f"Error accessing database: {str(e)}")
        return redirect(url_for('install'))
    # Fresh DB + auth on → direct the user through first-run setup.
    if is_auth_enabled() and not _install_done():
        return redirect(url_for('install'))
    return redirect(url_for('workbench'))

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if not _install_done():
        return redirect(url_for('install'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        auth_config = get_auth_config()
        
        # Check if user exists and determine authentication method
        if user and user.auth_type == 'tacacs':
            # TACACS+ authentication
            if authenticate_tacacs(form.username.data, form.password.data):
                login_user(user, remember=form.remember_me.data)
                user.last_login = _utcnow()
                db.session.commit()
                return redirect(url_for('index'))
        elif user and user.auth_type == 'local':
            # Local authentication
            if user.check_password(form.password.data):
                login_user(user, remember=form.remember_me.data)
                user.last_login = _utcnow()
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
    script = Script.query.get_or_404(script_id)
    
    # Check if user owns the script or is admin
    if not current_user.is_admin and script.creator_id != current_user.id:
        flash('Access denied: You can only edit your own scripts')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        script.name = request.form.get('name')
        script.description = request.form.get('description')
        script.category = request.form.get('category')
        script.tags = request.form.get('tags')
        script.status = request.form.get('status')
        
        db.session.commit()
        flash(f'Script "{script.name}" updated successfully')
        return redirect(url_for('my_scripts') if not current_user.is_admin else url_for('admin_dashboard'))
    
    return render_template('admin/edit_script.html', script=script)

@app.route('/admin/scripts/<int:script_id>/template', methods=['GET', 'POST'])
@maybe_login_required
def edit_template(script_id):
    return redirect(url_for('workbench', script_id=script_id, tab='template'), code=301)

@app.route('/scripts/<int:script_id>/fields', methods=['GET'])
@maybe_login_required
def manage_fields(script_id):
    return redirect(url_for('workbench', script_id=script_id, tab='fields'), code=301)

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
            field_values=json.dumps(form_data, default=str),
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

def _install_done():
    """True if this instance has been through initial setup: users exist."""
    try:
        return User.query.count() > 0
    except Exception:
        # DB not ready yet — treat as not installed.
        return False

@app.route('/install', methods=['GET', 'POST'])
def install():
    """First-run wizard. Creates an admin OR flips the app into open mode.

    Accessible only when zero users exist. Once the first user is created
    (or open mode is chosen), /install redirects to the app.
    """
    # Ensure schema exists — the startup hook does this too, but a fresh DB
    # could still be missing tables if that failed.
    try:
        db.create_all()
    except Exception as e:
        app.logger.warning(f'install: db.create_all failed: {e}')

    if _install_done():
        flash('This instance is already installed. Use /login or the Auth settings page to manage access.')
        return redirect(url_for('index'))

    form = {}
    if request.method == 'POST':
        mode = request.form.get('mode', '')
        form = dict(request.form)

        if mode == 'open':
            cfg = get_auth_config()
            cfg.auth_enabled = False
            cfg.updated_at = _utcnow()
            db.session.commit()
            flash('Installed in open mode. No login required.')
            return redirect(url_for('index'))

        if mode == 'auth':
            username = (request.form.get('username') or '').strip()
            email    = (request.form.get('email') or '').strip()
            full_name= (request.form.get('full_name') or '').strip()
            password = request.form.get('password') or ''
            confirm  = request.form.get('confirm') or ''

            errors = []
            if len(username) < 3:                         errors.append('Username must be at least 3 characters.')
            if '@' not in email or '.' not in email:      errors.append('A valid email is required.')
            if len(password) < 8:                         errors.append('Password must be at least 8 characters.')
            if password != confirm:                       errors.append('Password and confirmation do not match.')

            if errors:
                for e in errors:
                    flash(e)
                return render_template('install.html', form=form)

            cfg = get_auth_config()
            cfg.auth_enabled = True
            cfg.updated_at = _utcnow()
            user = User(
                username=username,
                email=email,
                full_name=full_name or None,
                is_admin=True,
                is_active=True,
                auth_type='local',
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f'Admin user "{username}" created. Please sign in.')
            return redirect(url_for('login'))

        flash('Please choose a mode.')

    return render_template('install.html', form=form)

# Legacy /setup URL forwards to the new wizard.
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    return redirect(url_for('install'), code=301)

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
        config.auth_enabled = bool(form.auth_enabled.data)
        config.auth_type = form.auth_type.data
        config.tacacs_server = form.tacacs_server.data
        config.tacacs_port = int(form.tacacs_port.data)
        
        if form.tacacs_secret.data:  # Only update if provided
            config.tacacs_secret = form.tacacs_secret.data
            
        config.tacacs_timeout = int(form.tacacs_timeout.data)
        config.tacacs_service = form.tacacs_service.data
        config.updated_at = _utcnow()
        
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
@maybe_login_required
def admin_dashboard():
    return redirect(url_for('workbench'), code=301)

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
    
    auth_enabled = BooleanField('Require login', default=False)
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
    script = Script.query.get_or_404(script_id)
    
    # Check if user owns the script or is admin
    if not current_user.is_admin and script.creator_id != current_user.id:
        flash('Access denied: You can only delete your own scripts')
        return redirect(url_for('index'))
    
    try:
        # Delete the script (cascade will handle related records)
        db.session.delete(script)
        db.session.commit()
        flash(f'Script "{script.name}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting script: {str(e)}', 'error')
    
    return redirect(url_for('admin_scripts'))

# User script management routes
@app.route('/my-scripts')
@maybe_login_required
def my_scripts():
    # Legacy entry point — forwards to the unified workbench.
    return redirect(url_for('workbench'), code=301)

@app.route('/my-scripts/new', methods=['GET', 'POST'])
@login_required
def create_my_script():
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
            creator_id=current_user.id,
            status='draft'  # Default to draft for user-created scripts
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
        return redirect(url_for('edit_my_script', script_id=script.id))
    
    return render_template('user/create_script.html')

@app.route('/my-scripts/<int:script_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_my_script(script_id):
    script = Script.query.get_or_404(script_id)
    
    # Check if user owns the script
    if script.creator_id != current_user.id:
        flash('Access denied: You can only edit your own scripts')
        return redirect(url_for('my_scripts'))
    
    if request.method == 'POST':
        script.name = request.form.get('name')
        script.description = request.form.get('description')
        script.category = request.form.get('category')
        script.tags = request.form.get('tags')
        script.status = request.form.get('status')
        
        db.session.commit()
        flash(f'Script "{script.name}" updated successfully')
        return redirect(url_for('my_scripts'))
    
    return render_template('user/edit_script.html', script=script)

@app.route('/my-scripts/<int:script_id>/template', methods=['GET', 'POST'])
@login_required
def edit_my_template(script_id):
    script = Script.query.get_or_404(script_id)
    
    # Check if user owns the script
    if script.creator_id != current_user.id:
        flash('Access denied: You can only edit your own scripts')
        return redirect(url_for('my_scripts'))
    
    template = script.template
    
    if request.method == 'POST':
        template_content = request.form.get('content')
        output_format = request.form.get('output_format')
        
        template.version += 1
        template.content = template_content
        template.output_format = output_format
        
        db.session.commit()
        flash('Template updated successfully')
        return redirect(url_for('edit_my_template', script_id=script_id))
    
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
    
    return render_template('user/edit_template.html', script=script, template=template, jinja_snippets=jinja_snippets)

@app.route('/my-scripts/<int:script_id>/fields', methods=['GET'])
@login_required
def manage_my_fields(script_id):
    script = Script.query.get_or_404(script_id)
    
    # Check if user owns the script
    if script.creator_id != current_user.id:
        flash('Access denied: You can only edit your own scripts')
        return redirect(url_for('my_scripts'))
    
    return render_template('user/manage_fields.html', script=script)

@app.route('/my-scripts/<int:script_id>/delete', methods=['POST'])
@login_required
def delete_my_script(script_id):
    script = Script.query.get_or_404(script_id)
    
    # Check if user owns the script
    if script.creator_id != current_user.id:
        flash('Access denied: You can only delete your own scripts')
        return redirect(url_for('my_scripts'))
    
    try:
        db.session.delete(script)
        db.session.commit()
        flash(f'Script "{script.name}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting script: {str(e)}', 'error')
    
    return redirect(url_for('my_scripts'))

@app.route('/scripts/<int:script_id>/save-draft', methods=['POST'])
@login_required
def save_form_draft(script_id):
    script = Script.query.get_or_404(script_id)
    form_data = request.form.to_dict()
    
    # Find existing draft or create new one
    draft = FormDraft.query.filter_by(
        script_id=script_id,
        user_id=current_user.id
    ).first()
    
    if not draft:
        draft = FormDraft(
            script_id=script_id,
            user_id=current_user.id,
            field_values=form_data
        )
        db.session.add(draft)
    else:
        draft.field_values = form_data
    
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/scripts/<int:script_id>/load-draft', methods=['GET'])
@login_required
def load_form_draft(script_id):
    script = Script.query.get_or_404(script_id)
    draft = FormDraft.query.filter_by(
        script_id=script_id,
        user_id=current_user.id
    ).first()
    
    print(f"Loading draft for script {script_id} and user {current_user.id}")  # Debug print
    print(f"Draft found: {draft is not None}")  # Debug print
    
    if draft:
        print(f"Draft values: {draft.field_values}")  # Debug print
        return jsonify({
            'status': 'success',
            'data': draft.field_values
        })
    return jsonify({'status': 'not_found'})

@app.route('/scripts/<int:script_id>/submissions', methods=['GET'])
@login_required
def get_script_submissions(script_id):
    script = Script.query.get_or_404(script_id)
    
    # Get submissions for this script by the current user
    submissions = FormSubmission.query.filter_by(
        script_id=script_id,
        user_id=current_user.id
    ).order_by(FormSubmission.submission_date.desc()).all()
    
    # Format submissions for the dropdown
    submission_list = [{
        'id': sub.id,
        'date': sub.submission_date.strftime('%Y-%m-%d %H:%M:%S'),
        'values': json.loads(sub.field_values) if isinstance(sub.field_values, str) else sub.field_values
    } for sub in submissions]
    
    return jsonify({'submissions': submission_list})

# ---------------------------------------------------------------------------
# Unified /workbench single pane
# ---------------------------------------------------------------------------
# One page, four tabs in the right pane, swapped in-place via HTMX.
# Old URLs continue to work; this page supersedes /admin/dashboard and /my-scripts.

_RAIL_SORTS = {
    'modified_desc': (Script.modified_at, True),
    'modified_asc':  (Script.modified_at, False),
    'created_desc':  (Script.created_at,  True),
    'created_asc':   (Script.created_at,  False),
    'name_asc':      (Script.name,        False),
    'name_desc':     (Script.name,        True),
    'status_asc':    (Script.status,      False),
}
RAIL_SORT_LABELS = [
    ('modified_desc', 'Recently modified'),
    ('created_desc',  'Recently created'),
    ('name_asc',      'Name A–Z'),
    ('name_desc',     'Name Z–A'),
    ('status_asc',    'Status'),
]

def _visible_scripts(q='', sort_key='modified_desc', page=1, per_page=15):
    query = Script.query
    if not _viewer_sees_all():
        query = query.filter(
            (Script.creator_id == current_user.id) | (Script.status == 'active')
        )
    if q:
        pat = f'%{q}%'
        query = query.filter(db.or_(
            Script.name.ilike(pat),
            Script.description.ilike(pat),
            Script.category.ilike(pat),
            Script.tags.ilike(pat),
        ))
    col, desc = _RAIL_SORTS.get(sort_key, _RAIL_SORTS['modified_desc'])
    query = query.order_by(col.desc() if desc else col.asc())
    return query.paginate(page=page, per_page=per_page, error_out=False)

def _guard_edit(script):
    if not can_edit(current_user, script):
        flash('You do not have permission to edit this script.')
        return redirect(url_for('workbench', script_id=script.id))
    return None

@app.route('/workbench', methods=['GET'])
@app.route('/workbench/<int:script_id>', methods=['GET'])
@maybe_login_required
def workbench(script_id=None):
    rail_q    = (request.args.get('q') or '').strip()
    rail_sort = request.args.get('sort', 'modified_desc')
    rail_page = request.args.get('page', 1, type=int)
    rail = _visible_scripts(q=rail_q, sort_key=rail_sort, page=rail_page)

    selected = Script.query.get(script_id) if script_id else None
    tab = request.args.get('tab', 'run')

    script_outputs = None
    if selected and tab == 'outputs':
        q = GeneratedScript.query.filter_by(original_script_id=selected.id)
        if not _viewer_sees_all():
            uid = current_user.id if current_user.is_authenticated else None
            q = q.filter(GeneratedScript.user_id == uid)
        script_outputs = q.order_by(GeneratedScript.created_at.desc()).limit(50).all()

    return render_template(
        'workbench.html',
        rail=rail,
        rail_q=rail_q,
        rail_sort=rail_sort,
        RAIL_SORT_LABELS=RAIL_SORT_LABELS,
        selected=selected,
        tab=tab,
        script_outputs=script_outputs,
    )

@app.route('/workbench/new', methods=['POST'])
@maybe_login_required
def workbench_new():
    name = (request.form.get('name') or 'Untitled Script').strip()
    script = Script(
        uuid=str(uuid.uuid4()),
        name=name,
        description='',
        category='',
        tags='',
        creator_id=current_user.id if current_user.is_authenticated else None,
        status='draft',
    )
    db.session.add(script)
    db.session.commit()
    db.session.add(Template(script_id=script.id, content='', version=1))
    db.session.commit()
    return redirect(url_for('workbench', script_id=script.id, tab='template'))

@app.route('/workbench/<int:script_id>/delete', methods=['POST'])
@maybe_login_required
def workbench_delete(script_id):
    script = Script.query.get_or_404(script_id)
    guard = _guard_edit(script)
    if guard:
        return guard
    db.session.delete(script)
    db.session.commit()
    flash(f'Deleted "{script.name}".')
    return redirect(url_for('workbench'))

@app.route('/workbench/<int:script_id>/details', methods=['POST'])
@maybe_login_required
def workbench_save_details(script_id):
    script = Script.query.get_or_404(script_id)
    guard = _guard_edit(script)
    if guard:
        return guard

    tracked = [
        ('name',                 request.form.get('name', script.name)),
        ('status',               request.form.get('status', script.status)),
        ('description',          request.form.get('description', script.description) or ''),
        ('category',             request.form.get('category', script.category) or ''),
        ('tags',                 request.form.get('tags', script.tags) or ''),
        ('script_instructions',  request.form.get('script_instructions', script.script_instructions) or ''),
    ]
    for field, new_val in tracked:
        old_val = getattr(script, field) or ''
        if (old_val or '') != (new_val or ''):
            _log_change(
                script_id, 'script_edit', field_name=field,
                old=old_val, new=new_val,
                description=f'Changed {field}',
            )
            setattr(script, field, new_val)
    db.session.commit()
    return redirect(url_for('workbench', script_id=script.id, tab='details'))

@app.route('/workbench/<int:script_id>/template', methods=['POST'])
@maybe_login_required
def workbench_save_template(script_id):
    script = Script.query.get_or_404(script_id)
    guard = _guard_edit(script)
    if guard:
        return guard
    if script.template is None:
        db.session.add(Template(script_id=script.id, content='', version=1))
        db.session.commit()

    new_content = request.form.get('content', '')
    new_format  = request.form.get('output_format', script.template.output_format)

    # Validation is advisory, not blocking. The user's content is always saved
    # so they never lose work; issues are surfaced as flash warnings.
    from jinja2 import Environment, TemplateSyntaxError, meta
    warnings = []
    try:
        parsed = Environment().parse(new_content)
        tmpl_vars = meta.find_undeclared_variables(parsed)
        missing = sorted(tmpl_vars - {f.name for f in script.form_fields})
        if missing:
            warnings.append(
                'References undefined variables: ' + ', '.join(missing)
                + ' — add matching fields on the Fields tab, or use "Detect variables".'
            )
    except TemplateSyntaxError as e:
        warnings.append(f'Template syntax error at line {e.lineno}: {e.message}')

    old_content = script.template.content
    old_format  = script.template.output_format
    changed = False
    if old_content != new_content:
        _log_change(script_id, 'template_edit', field_name='content',
                    old=old_content, new=new_content, description='Updated template content')
        script.template.content = new_content
        script.template.version = (script.template.version or 1) + 1
        changed = True
    if old_format != new_format:
        _log_change(script_id, 'template_edit', field_name='output_format',
                    old=old_format, new=new_format,
                    description=f'Changed output format from "{old_format}" to "{new_format}"')
        script.template.output_format = new_format
        changed = True
    if changed:
        db.session.commit()
    if warnings:
        # Tagged category so these render inline above the editor, not in the global flash bar.
        for w in warnings:
            flash(w, 'template_warning')
    elif changed:
        flash('Template saved.')
    return redirect(url_for('workbench', script_id=script.id, tab='template'))

@app.route('/workbench/<int:script_id>/run', methods=['POST'])
@maybe_login_required
def workbench_run(script_id):
    script = Script.query.get_or_404(script_id)
    form_fields = FormField.query.filter_by(script_id=script_id).order_by(FormField.display_order).all()
    form_data = {}
    for f in form_fields:
        if _field_is_multi(f.field_type):
            form_data[f.name] = request.form.getlist(f.name)
        elif f.field_type == 'checkbox':
            form_data[f.name] = bool(request.form.get(f.name))
        elif f.field_type in _IP_TYPES:
            form_data[f.name] = IPValue(request.form.get(f.name, ''))
        else:
            form_data[f.name] = request.form.get(f.name, '')
    try:
        tmpl = jinja2.Template(script.template.content if script.template else '')
        output = tmpl.render(**form_data)
    except Exception as e:
        output = f"[Template error] {e}"
    full_output = _build_output_header(script, form_data, form_fields) + output
    uid = current_user.id if current_user.is_authenticated else None
    submission = FormSubmission(
        script_id=script_id,
        user_id=uid,
        field_values=json.dumps(form_data, default=str),
        output=full_output,
    )
    db.session.add(submission)
    # Also write to the user-facing library.
    def _first_str(val):
        if isinstance(val, list):
            val = val[0] if val else ''
        return str(val)[:20] if val else ''
    name_bits = [s for s in (_first_str(form_data.get(f.name)) for f in form_fields[:2]) if s]
    gname = f"{script.name} — " + (' '.join(name_bits) if name_bits
                                    else _utcnow().strftime('%Y-%m-%d %H:%M'))
    generated = GeneratedScript(
        original_script_id=script_id,
        user_id=uid,
        name=gname[:200],
        generated_content=full_output,
        csv_row_data=json.dumps(form_data, default=str),
    )
    db.session.add(generated)
    db.session.commit()
    return render_template(
        'partials/run_output.html',
        script=script,
        output=full_output,
        submission_id=submission.id,
        output_id=generated.id,
    )

@app.route('/workbench/<int:script_id>/fields/add', methods=['POST'])
@maybe_login_required
def workbench_add_field(script_id):
    script = Script.query.get_or_404(script_id)
    guard = _guard_edit(script)
    if guard:
        return guard
    name = (request.form.get('name') or '').strip()
    label = (request.form.get('label') or name).strip()
    field_type = request.form.get('field_type') or 'text'
    if not name:
        flash('Variable name is required.')
        return redirect(url_for('workbench', script_id=script_id, tab='fields'))
    # +10 spacing so manual reordering can insert between
    last = FormField.query.filter_by(script_id=script_id).order_by(FormField.display_order.desc()).first()
    order = (last.display_order + 10) if last else 10
    cfg = _build_field_config(request.form)
    field = FormField(
        script_id=script_id,
        name=name,
        label=label,
        field_type=field_type,
        required=bool(request.form.get('required')),
        default_value=request.form.get('default_value') or None,
        help_text=request.form.get('help_text') or None,
        validation_rules=request.form.get('validation_rules') or None,
        conditional_logic=request.form.get('conditional_logic') or None,
        field_config=json.dumps(cfg) if cfg else None,
        display_order=order,
    )
    db.session.add(field)
    _log_change(script_id, 'field_add', field_name=name,
                new=f'{label} ({field_type})',
                description=f'Added field "{name}"')
    db.session.commit()
    return redirect(url_for('workbench', script_id=script_id, tab='fields'))

@app.route('/workbench/<int:script_id>/fields/<int:field_id>/edit', methods=['POST'])
@maybe_login_required
def workbench_edit_field(script_id, field_id):
    script = Script.query.get_or_404(script_id)
    guard = _guard_edit(script)
    if guard:
        return guard
    field = FormField.query.get_or_404(field_id)
    if field.script_id != script_id:
        flash('Invalid field.')
        return redirect(url_for('workbench', script_id=script_id, tab='fields'))

    new_name = (request.form.get('name') or field.name).strip()
    if not new_name:
        flash('Variable name is required.')
        return redirect(url_for('workbench', script_id=script_id, tab='fields'))
    if new_name != field.name:
        clash = FormField.query.filter(
            FormField.script_id == script_id,
            FormField.name == new_name,
            FormField.id != field_id,
        ).first()
        if clash:
            flash(f'Field "{new_name}" already exists.')
            return redirect(url_for('workbench', script_id=script_id, tab='fields'))

    cfg = _build_field_config(request.form)
    new_config = json.dumps(cfg) if cfg else None
    tracked = [
        ('name',              new_name),
        ('label',             (request.form.get('label') or new_name).strip()),
        ('field_type',        request.form.get('field_type') or 'text'),
        ('required',          bool(request.form.get('required'))),
        ('default_value',     request.form.get('default_value') or None),
        ('help_text',         request.form.get('help_text') or None),
        ('validation_rules',  request.form.get('validation_rules') or None),
        ('conditional_logic', request.form.get('conditional_logic') or None),
        ('field_config',      new_config),
    ]
    changed = False
    for attr, new_val in tracked:
        old_val = getattr(field, attr)
        if old_val != new_val:
            _log_change(
                script_id, 'field_edit', field_name=field.name,
                old=str(old_val) if old_val is not None else '',
                new=str(new_val) if new_val is not None else '',
                description=f'Changed {attr} on field "{field.name}"',
            )
            setattr(field, attr, new_val)
            changed = True
    if changed:
        db.session.commit()
        flash(f'Field "{field.name}" updated.')
    return redirect(url_for('workbench', script_id=script_id, tab='fields'))

@app.route('/workbench/<int:script_id>/fields/<int:field_id>/delete', methods=['POST'])
@maybe_login_required
def workbench_delete_field(script_id, field_id):
    script = Script.query.get_or_404(script_id)
    guard = _guard_edit(script)
    if guard:
        return guard
    field = FormField.query.get_or_404(field_id)
    if field.script_id != script_id:
        flash('Invalid field.')
        return redirect(url_for('workbench', script_id=script_id, tab='fields'))
    _log_change(script_id, 'field_delete', field_name=field.name,
                old=f'{field.label} ({field.field_type})',
                description=f'Deleted field "{field.name}"')
    db.session.delete(field)
    db.session.commit()
    return redirect(url_for('workbench', script_id=script_id, tab='fields'))

# ---------------------------------------------------------------------------
# Template-authoring APIs (JSON) + downloads
# ---------------------------------------------------------------------------
@app.route('/workbench/<int:script_id>/api/detect_variables', methods=['POST'])
@maybe_login_required
def wb_detect_variables(script_id):
    script = Script.query.get_or_404(script_id)
    if not can_edit(current_user, script):
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    content = data.get('template_content', '')
    found = _detect_template_variables(content)
    existing = {f.name for f in script.form_fields}
    return jsonify({
        'variables': sorted(found),
        'existing':  sorted(found & existing),
        'missing':   sorted(found - existing),
    })

@app.route('/workbench/<int:script_id>/api/validate_template', methods=['POST'])
@maybe_login_required
def wb_validate_template(script_id):
    script = Script.query.get_or_404(script_id)
    if not can_edit(current_user, script):
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    content = data.get('template_content', '')
    from jinja2 import Environment, TemplateSyntaxError
    try:
        Environment().parse(content)
        return jsonify({'valid': True, 'message': 'Template syntax is valid.'})
    except TemplateSyntaxError as e:
        return jsonify({
            'valid': False,
            'line':  e.lineno,
            'error': e.message,
            'message': f'Syntax error at line {e.lineno}: {e.message}',
        })

@app.route('/workbench/<int:script_id>/api/add_variable_field', methods=['POST'])
@maybe_login_required
def wb_add_variable_field(script_id):
    script = Script.query.get_or_404(script_id)
    if not can_edit(current_user, script):
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    varname = (data.get('variable_name') or '').strip()
    if not varname:
        return jsonify({'success': False, 'error': 'missing variable_name'}), 400
    if FormField.query.filter_by(script_id=script_id, name=varname).first():
        return jsonify({'success': False, 'error': f'Field "{varname}" already exists'}), 409
    last = FormField.query.filter_by(script_id=script_id).order_by(FormField.display_order.desc()).first()
    order = (last.display_order + 10) if last else 10
    label = varname.replace('_', ' ').title()
    field = FormField(
        script_id=script_id,
        name=varname,
        label=label,
        field_type='text',
        required=False,
        display_order=order,
    )
    db.session.add(field)
    _log_change(script_id, 'field_add', field_name=varname,
                new=f'{label} (text)',
                description=f'Auto-added field from template variable "{varname}"')
    db.session.commit()
    return jsonify({'success': True, 'field_id': field.id, 'name': varname, 'label': label})

@app.route('/workbench/<int:script_id>/api/fields/reorder', methods=['POST'])
@maybe_login_required
def wb_reorder_fields(script_id):
    script = Script.query.get_or_404(script_id)
    if not can_edit(current_user, script):
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    order = data.get('fields') or []
    for idx, item in enumerate(order):
        fid = item.get('id')
        if not fid:
            continue
        field = FormField.query.filter_by(id=fid, script_id=script_id).first()
        if field:
            field.display_order = (idx + 1) * 10
    db.session.commit()
    return jsonify({'success': True})

# ---------------------------------------------------------------------------
# Script import / export (cross-instance)
# ---------------------------------------------------------------------------
_EXPORT_FORMAT = 'scripter.script.v1'

def _export_script_dict(script):
    """Serialize a script + its template + its form fields into a portable dict."""
    return {
        'format':       _EXPORT_FORMAT,
        'exported_at':  _utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source_uuid':  script.uuid,
        'script': {
            'name':                 script.name,
            'description':          script.description or '',
            'category':             script.category or '',
            'tags':                 script.tags or '',
            'script_instructions':  script.script_instructions or '',
        },
        'template': {
            'content':        (script.template.content or '') if script.template else '',
            'output_format':  (script.template.output_format or 'text') if script.template else 'text',
        },
        'form_fields': [
            {
                'name':               f.name,
                'label':              f.label,
                'field_type':         f.field_type,
                'required':           bool(f.required),
                'default_value':      f.default_value,
                'help_text':          f.help_text,
                'validation_rules':   f.validation_rules,
                'conditional_logic':  f.conditional_logic,
                'field_config':       f.field_config,
                'display_order':      f.display_order,
            }
            for f in sorted(script.form_fields, key=lambda x: x.display_order)
        ],
    }

def _import_script_from_dict(data, target=None, user=None):
    """Apply an export dict. When target is None, creates a new Script.
    Returns (script, created_bool). Replace-all strategy for template + fields."""
    if not isinstance(data, dict) or data.get('format') != _EXPORT_FORMAT:
        raise ValueError(f'Unsupported export format: {data.get("format") if isinstance(data, dict) else "not an object"}')

    sd = data.get('script') or {}
    td = data.get('template') or {}
    ff = data.get('form_fields') or []

    created = target is None
    if created:
        target = Script(
            uuid=str(uuid.uuid4()),
            status='draft',
            name=(sd.get('name') or 'Imported Script').strip(),
            creator_id=user.id if (user and getattr(user, 'is_authenticated', False)) else None,
        )
        db.session.add(target)
        db.session.flush()  # get id before children reference it

    target.name                = (sd.get('name') or target.name or 'Imported Script').strip()
    target.description         = sd.get('description') or None
    target.category            = sd.get('category') or None
    target.tags                = sd.get('tags') or None
    target.script_instructions = sd.get('script_instructions') or None

    # Template — upsert on the singleton relationship.
    if target.template is None:
        target.template = Template(
            content=td.get('content') or '',
            output_format=td.get('output_format') or 'text',
            version=1,
        )
    else:
        target.template.content       = td.get('content') or ''
        target.template.output_format = td.get('output_format') or 'text'
        target.template.version       = (target.template.version or 0) + 1

    # Form fields — wipe & replace. Submissions reference script_id, not field_id, so they survive.
    for f in list(target.form_fields):
        db.session.delete(f)
    db.session.flush()

    for fd in ff:
        name = (fd.get('name') or '').strip()
        if not name:
            continue
        db.session.add(FormField(
            script_id=target.id,
            name=name,
            label=(fd.get('label') or name),
            field_type=fd.get('field_type') or 'text',
            required=bool(fd.get('required')),
            default_value=fd.get('default_value'),
            help_text=fd.get('help_text'),
            validation_rules=fd.get('validation_rules'),
            conditional_logic=fd.get('conditional_logic'),
            field_config=fd.get('field_config'),
            display_order=int(fd.get('display_order') or 0),
        ))

    return target, created


@app.route('/workbench/<int:script_id>/export')
@maybe_login_required
def wb_export_script(script_id):
    script = Script.query.get_or_404(script_id)
    if not can_edit(current_user, script):
        flash('You do not have permission to export this script.')
        return redirect(url_for('workbench', script_id=script_id))
    payload = json.dumps(_export_script_dict(script), indent=2, ensure_ascii=False)
    safe = _safe_filename(script.name, f'script_{script_id}')
    return _text_download(payload, f'{safe}.scripter.json', mime='application/json')


@app.route('/workbench/import', methods=['GET', 'POST'])
@maybe_login_required
def wb_import_script():
    if request.method == 'GET':
        return render_template('import_script.html', step='upload')

    file = request.files.get('import_file')
    if not file or not file.filename:
        flash('No file uploaded.')
        return redirect(url_for('wb_import_script'))
    try:
        raw = file.read().decode('utf-8')
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        flash(f'Could not parse file: {e}')
        return redirect(url_for('wb_import_script'))
    if not isinstance(data, dict) or data.get('format') != _EXPORT_FORMAT:
        flash(f'Unsupported export format. Expected "{_EXPORT_FORMAT}", got {data.get("format")!r}.')
        return redirect(url_for('wb_import_script'))

    # Suggest a target by matching source_uuid on the current instance.
    matched = None
    src_uuid = data.get('source_uuid')
    if src_uuid:
        matched = Script.query.filter_by(uuid=src_uuid).first()
        if matched and not can_edit(current_user, matched):
            matched = None  # user can't overwrite — don't preselect

    # Full list of overwrite candidates the user may target.
    all_scripts = Script.query.order_by(Script.modified_at.desc()).all()
    editable_targets = [s for s in all_scripts if can_edit(current_user, s)]

    return render_template(
        'import_script.html',
        step='preview',
        data=data,
        payload_json=json.dumps(data),  # round-trip through hidden field
        matched=matched,
        editable_targets=editable_targets,
    )


@app.route('/workbench/import/commit', methods=['POST'])
@maybe_login_required
def wb_import_commit():
    payload = request.form.get('payload_json') or ''
    try:
        data = json.loads(payload)
    except Exception:
        flash('Import payload was missing or malformed — start over.')
        return redirect(url_for('wb_import_script'))

    mode = request.form.get('mode', '')
    target = None
    if mode == 'overwrite':
        target_id = request.form.get('target_id', type=int)
        if not target_id:
            flash('Pick a script to overwrite.')
            return redirect(url_for('wb_import_script'))
        target = Script.query.get(target_id)
        if target is None or not can_edit(current_user, target):
            flash('Target script not found or not editable.')
            return redirect(url_for('wb_import_script'))
    elif mode != 'new':
        flash('Choose a target mode.')
        return redirect(url_for('wb_import_script'))

    try:
        script, created = _import_script_from_dict(data, target=target, user=current_user)
    except ValueError as e:
        flash(str(e))
        return redirect(url_for('wb_import_script'))

    _log_change(
        script.id, 'script_edit', field_name='import',
        new=data.get('source_uuid') or 'unknown',
        description=('Imported as new script.' if created else 'Overwritten from imported file.'),
    )
    db.session.commit()
    flash(f'Imported "{script.name}".')
    return redirect(url_for('workbench', script_id=script.id))


@app.route('/workbench/<int:script_id>/export-template')
@maybe_login_required
def wb_export_template(script_id):
    script = Script.query.get_or_404(script_id)
    if script.template is None:
        flash('No template to export.')
        return redirect(url_for('workbench', script_id=script_id, tab='template'))
    lines = []
    if script.form_fields:
        lines.append('# Template Variables')
        lines.append('# =================')
        for f in sorted(script.form_fields, key=lambda x: x.display_order):
            lines.append(f'# {f.name} — {{{{ {f.name} }}}}')
        lines.append('')
    body = '\n'.join(lines) + (script.template.content or '')
    safe = _safe_filename(script.name, f'script_{script_id}')
    return _text_download(body, f'{safe}_template.txt')

@app.route('/workbench/<int:script_id>/csv-template')
@maybe_login_required
def wb_csv_template(script_id):
    script = Script.query.get_or_404(script_id)
    fields = sorted(script.form_fields, key=lambda f: f.display_order)
    if not fields:
        flash('Add at least one field before downloading a CSV template.')
        return redirect(url_for('workbench', script_id=script_id, tab='fields'))
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow([f.name for f in fields])
    w.writerow([f'{f.label} ({f.field_type})' for f in fields])
    safe = _safe_filename(script.name, f'script_{script_id}')
    return _text_download(buf.getvalue(), f'{safe}_template.csv', mime='text/csv')

# ---------------------------------------------------------------------------
# History tab
# ---------------------------------------------------------------------------
@app.route('/workbench/<int:script_id>/history-partial')
@maybe_login_required
def wb_history_partial(script_id):
    """Returns a rendered history list — used inline inside the workbench history tab."""
    script = Script.query.get_or_404(script_id)
    page       = request.args.get('page', 1, type=int)
    per_page   = max(5, min(100, request.args.get('per_page', 20, type=int)))
    search     = (request.args.get('search') or '').strip()
    type_f     = (request.args.get('type') or '').strip()

    q = ScriptChange.query.filter_by(script_id=script_id)
    if search:
        pat = f'%{search}%'
        q = q.filter(db.or_(
            ScriptChange.description.ilike(pat),
            ScriptChange.field_name.ilike(pat),
            ScriptChange.old_value.ilike(pat),
            ScriptChange.new_value.ilike(pat),
        ))
    if type_f:
        q = q.filter(ScriptChange.change_type == type_f)

    pagination = q.order_by(ScriptChange.change_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    changes = pagination.items
    for ch in changes:
        ch.diff = None
        if ch.change_type == 'template_edit' and ch.field_name == 'content':
            ch.diff = generate_diff(ch.old_value or '', ch.new_value or '')

    change_types = sorted({
        t for (t,) in db.session.query(ScriptChange.change_type)
                       .filter_by(script_id=script_id).distinct().all()
    })
    return render_template(
        'partials/history.html',
        script=script,
        changes=changes,
        pagination=pagination,
        search=search,
        type_filter=type_f,
        change_types=change_types,
        per_page=per_page,
        CHANGE_TYPE_LABELS=CHANGE_TYPE_LABELS,
    )

# ---------------------------------------------------------------------------
# CSV bulk generation + Outputs library (GeneratedScript)
# ---------------------------------------------------------------------------
@app.route('/workbench/<int:script_id>/bulk-preview', methods=['POST'])
@maybe_login_required
def wb_bulk_preview(script_id):
    """Accept a CSV upload, parse, and render an editable preview table."""
    script = Script.query.get_or_404(script_id)
    fields = sorted(script.form_fields, key=lambda f: f.display_order)
    if not fields:
        flash('Add form fields before bulk-generating.')
        return redirect(url_for('workbench', script_id=script_id, tab='fields'))

    if 'csv_file' not in request.files:
        flash('No CSV file uploaded.')
        return redirect(url_for('workbench', script_id=script_id, tab='run', mode='bulk'))
    file = request.files['csv_file']
    if not file.filename:
        flash('No file selected.')
        return redirect(url_for('workbench', script_id=script_id, tab='run', mode='bulk'))
    if not file.filename.lower().endswith('.csv'):
        flash('Please upload a .csv file.')
        return redirect(url_for('workbench', script_id=script_id, tab='run', mode='bulk'))
    try:
        content = file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        flash('CSV must be UTF-8 encoded.')
        return redirect(url_for('workbench', script_id=script_id, tab='run', mode='bulk'))

    reader = _csv.DictReader(content.splitlines())
    headers = reader.fieldnames or []
    missing = {f.name for f in fields} - set(headers)
    if missing:
        flash(f'CSV is missing required columns: {", ".join(sorted(missing))}')
        return redirect(url_for('workbench', script_id=script_id, tab='run', mode='bulk'))

    # Keep rows in field-display order for consistent UI.
    rows = []
    for raw_row in reader:
        if not any((raw_row or {}).values()):
            continue
        rows.append({f.name: (raw_row.get(f.name) or '').strip() for f in fields})

    if not rows:
        flash('CSV has no data rows.')
        return redirect(url_for('workbench', script_id=script_id, tab='run', mode='bulk'))

    return render_template(
        'bulk_preview.html',
        script=script,
        fields=fields,
        rows=rows,
    )


@app.route('/workbench/<int:script_id>/bulk-generate', methods=['POST'])
@maybe_login_required
def wb_bulk_generate(script_id):
    """Receive the edited preview form, render one output per kept row."""
    script = Script.query.get_or_404(script_id)
    fields = sorted(script.form_fields, key=lambda f: f.display_order)
    if not fields:
        flash('Add form fields before bulk-generating.')
        return redirect(url_for('workbench', script_id=script_id, tab='fields'))

    try:
        row_count = int(request.form.get('row_count', '0'))
    except ValueError:
        row_count = 0
    if row_count <= 0:
        flash('No rows submitted.')
        return redirect(url_for('workbench', script_id=script_id, tab='run', mode='bulk'))

    batch_id = uuid.uuid4().hex[:8]
    from jinja2 import Environment
    env = Environment()
    uid = current_user.id if current_user.is_authenticated else None

    # Assemble per-row form_data for kept rows only.
    kept = []
    for i in range(row_count):
        if request.form.get(f'drop_{i}'):
            continue
        form_data = {}
        for f in fields:
            raw = (request.form.get(f'r{i}_{f.name}') or '').strip()
            form_data[f.name] = IPValue(raw) if f.field_type in _IP_TYPES else raw
        kept.append(form_data)

    if not kept:
        flash('All rows were dropped — nothing to generate.')
        return redirect(url_for('workbench', script_id=script_id, tab='run', mode='bulk'))

    created = 0
    errors = 0
    total_rows = len(kept)
    for idx, form_data in enumerate(kept, start=1):
        try:
            rendered = env.from_string(script.template.content or '').render(**form_data)
        except Exception as e:
            app.logger.error(f'bulk row {idx} error: {e}')
            errors += 1
            continue
        full_output = _build_output_header(
            script, form_data, fields,
            batch_id=batch_id, row_num=idx, total_rows=total_rows,
        ) + rendered
        name_bits = [str(form_data[f.name])[:20] for f in fields[:3] if form_data.get(f.name)]
        name = f"{script.name} — " + (' '.join(name_bits) if name_bits else f'Row {idx}')
        db.session.add(GeneratedScript(
            original_script_id=script_id,
            user_id=uid,
            name=name[:200],
            generated_content=full_output,
            csv_row_data=json.dumps(form_data, default=str),
            batch_id=batch_id,
        ))
        created += 1
    if created:
        db.session.commit()
        flash(f'Generated {created} script{"s" if created != 1 else ""}.'
              + (f' {errors} row(s) failed.' if errors else ''))
        return redirect(url_for('outputs_list', batch=batch_id))
    flash('No scripts were generated.')
    return redirect(url_for('workbench', script_id=script_id, tab='run', mode='bulk'))

@app.route('/outputs')
@maybe_login_required
def outputs_list():
    page       = request.args.get('page', 1, type=int)
    per_page   = max(5, min(100, request.args.get('per_page', 25, type=int)))
    sort_by    = request.args.get('sort', 'created_at')
    order      = request.args.get('order', 'desc')
    search     = (request.args.get('search') or '').strip()
    batch      = (request.args.get('batch') or '').strip()
    script_id  = request.args.get('script_id', type=int)

    q = GeneratedScript.query
    if not _viewer_sees_all():
        q = q.filter(GeneratedScript.user_id == current_user.id)
    if search:
        pat = f'%{search}%'
        q = q.filter(GeneratedScript.name.ilike(pat))
    if batch:
        q = q.filter(GeneratedScript.batch_id == batch)
    if script_id:
        q = q.filter(GeneratedScript.original_script_id == script_id)

    columns = {
        'name':        GeneratedScript.name,
        'batch':       GeneratedScript.batch_id,
        'created_at':  GeneratedScript.created_at,
        'modified_at': GeneratedScript.modified_at,
    }
    col = columns.get(sort_by, GeneratedScript.created_at)
    q = q.order_by(col.desc() if order == 'desc' else col.asc())

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        'outputs.html',
        outputs=pagination.items,
        pagination=pagination,
        search=search,
        batch=batch,
        per_page=per_page,
        current_sort=sort_by,
        current_order=order,
    )

def _owned_output_or_404(output_id):
    out = GeneratedScript.query.get_or_404(output_id)
    if not _viewer_sees_all():
        uid = current_user.id if current_user.is_authenticated else None
        if out.user_id != uid:
            flash('Not found.')
            return None
    return out

@app.route('/outputs/<int:output_id>')
@maybe_login_required
def outputs_view(output_id):
    out = _owned_output_or_404(output_id)
    if out is None:
        return redirect(url_for('outputs_list'))
    return render_template('output_view.html', output=out)

@app.route('/outputs/<int:output_id>/edit', methods=['GET', 'POST'])
@maybe_login_required
def outputs_edit(output_id):
    out = _owned_output_or_404(output_id)
    if out is None:
        return redirect(url_for('outputs_list'))
    if request.method == 'POST':
        out.name = (request.form.get('name') or out.name).strip()
        out.generated_content = request.form.get('content', out.generated_content)
        out.modified_at = _utcnow()
        db.session.commit()
        flash('Output saved.')
        return redirect(url_for('outputs_view', output_id=out.id))
    return render_template('output_edit.html', output=out)

@app.route('/outputs/<int:output_id>/download')
@maybe_login_required
def outputs_download(output_id):
    out = _owned_output_or_404(output_id)
    if out is None:
        return redirect(url_for('outputs_list'))
    safe = _safe_filename(out.name, f'output_{output_id}')
    return _text_download(out.generated_content, f'{safe}.txt')

@app.route('/outputs/<int:output_id>/delete', methods=['POST'])
@maybe_login_required
def outputs_delete(output_id):
    out = _owned_output_or_404(output_id)
    if out is None:
        return redirect(url_for('outputs_list'))
    name = out.name
    db.session.delete(out)
    db.session.commit()
    flash(f'Deleted "{name}".')
    return redirect(url_for('outputs_list'))

# ---------------------------------------------------------------------------
# IP Helper — subnet math for IPv4 and IPv6 via stdlib `ipaddress`
# ---------------------------------------------------------------------------
@app.route('/api/ip-helper')
@maybe_login_required
def api_ip_helper():
    import ipaddress
    addr = (request.args.get('address') or '').strip()
    mask = (request.args.get('mask') or '').strip()
    if not addr:
        return jsonify({'valid': False, 'error': 'missing address'}), 400

    # Compose a CIDR-style spec from address + optional mask override.
    bare = addr.split('/')[0].strip()
    if mask:
        spec = f"{bare}/{mask.lstrip('/')}"
    elif '/' in addr:
        spec = addr
    else:
        try:
            ip = ipaddress.ip_address(bare)
        except ValueError as e:
            return jsonify({'valid': False, 'error': str(e)}), 400
        spec = f"{bare}/{32 if ip.version == 4 else 128}"

    # ip_interface preserves the user's specific host inside a subnet.
    # e.g. '192.168.1.5/24' -> iface.ip = 192.168.1.5, iface.network = 192.168.1.0/24.
    try:
        iface = ipaddress.ip_interface(spec)
        net = iface.network
        host_ip = iface.ip
    except ValueError as e:
        return jsonify({'valid': False, 'error': str(e)}), 400

    tags = []
    if net.is_private:       tags.append('private')
    elif net.is_global:      tags.append('global')
    if net.is_loopback:      tags.append('loopback')
    if net.is_link_local:    tags.append('link-local')
    if net.is_multicast:     tags.append('multicast')
    if net.is_reserved:      tags.append('reserved')
    if net.is_unspecified:   tags.append('unspecified')
    classification = f'IPv{net.version}' + (' · ' + ' · '.join(tags) if tags else '')

    resp = {
        'valid':          True,
        'version':        net.version,
        'input':          addr,
        'network':        str(net.network_address),
        'cidr':           str(net),
        'prefix_length':  net.prefixlen,
        'num_addresses':  str(net.num_addresses),
        'classification': classification,
        # When the user typed a specific host inside a subnet
        # (e.g. 192.168.1.5/24), preserve it alongside the network math.
        'host_address':    str(host_ip) if host_ip != net.network_address else None,
        'host_cidr':       str(iface)   if host_ip != net.network_address else None,
    }

    if net.version == 4:
        resp['broadcast'] = str(net.broadcast_address)
        resp['netmask']   = str(net.netmask)
        resp['wildcard']  = str(net.hostmask)
        if net.prefixlen == 32:
            resp['first_host'] = str(net.network_address)
            resp['last_host']  = str(net.network_address)
            resp['num_hosts']  = '1'
        elif net.prefixlen == 31:
            hosts = list(net.hosts())
            resp['first_host'] = str(hosts[0]) if hosts else ''
            resp['last_host']  = str(hosts[-1]) if hosts else ''
            resp['num_hosts']  = str(len(hosts))
        else:
            resp['first_host'] = str(net.network_address + 1)
            resp['last_host']  = str(net.broadcast_address - 1)
            resp['num_hosts']  = str(net.num_addresses - 2)
    else:
        # IPv6: no broadcast; anycast at network_address is typically avoided for hosts.
        resp['broadcast'] = None
        resp['netmask']   = str(net.netmask)
        resp['wildcard']  = None
        if net.prefixlen == 128:
            resp['first_host'] = str(net.network_address)
            resp['last_host']  = str(net.network_address)
            resp['num_hosts']  = '1'
        else:
            resp['first_host'] = str(net.network_address + 1)
            resp['last_host']  = str(net.broadcast_address)
            resp['num_hosts']  = str(net.num_addresses - 1)

    return jsonify(resp)

if __name__ == '__main__':
    app.run(debug=True, port=5500)
