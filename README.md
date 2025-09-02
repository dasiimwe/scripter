# Scripter

A web-based configuration script generator that uses Jinja2 templating to create customized scripts and documents through dynamic forms.

## Overview

Scripter is a Flask-based web application that enables administrators to create custom forms with Jinja2 templates. End users can fill out these forms to generate customized configuration scripts and documents. The system manages multiple scripts, each consisting of a template and its associated form fields.

## Features

- **Template Management**: Create and edit Jinja2 templates with syntax highlighting
- **Dynamic Form Builder**: Automatically generate form fields from template variables
- **Multiple Field Types**: Support for text, textarea, select, checkbox, number, date, email, URL, and password fields
- **Script Versioning**: Track changes to templates and scripts with full history
- **User Authentication**: Support for local and TACACS+ authentication
- **Role-Based Access**: Admin and regular user roles
- **Export Functionality**: Export templates with variable documentation
- **Generated Script Management**: Save, edit, and manage generated configurations

## Requirements

- Python 3.8 or higher
- SQLite (included with Python)
- Virtual environment (recommended)

## Installation

### Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/scripter.git
cd scripter
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run database migrations:
```bash
python migrate_db.py
```

5. Start the development server:
```bash
python app.py
```

6. Access the application at `http://localhost:5000`

7. Complete the initial setup at `/setup` to create your first admin user

## Deployment Instructions

### Production Deployment with Gunicorn (Linux/Unix)

1. **Install additional production dependencies:**
```bash
pip install gunicorn
```

2. **Configure environment variables:**
Create a `.env` file in the project root:
```bash
# Flask Configuration
FLASK_ENV=production
SECRET_KEY=your-very-secret-key-here-change-this
DATABASE_URL=sqlite:///instance/scripter.db

# Optional: External database (PostgreSQL example)
# DATABASE_URL=postgresql://user:password@localhost/scripter_db
```

3. **Run with Gunicorn:**
```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Deployment with systemd (Linux)

1. **Create a systemd service file:**
```bash
sudo nano /etc/systemd/system/scripter.service
```

2. **Add the following configuration:**
```ini
[Unit]
Description=Scripter Web Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/scripter
Environment="PATH=/path/to/scripter/venv/bin"
ExecStart=/path/to/scripter/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:app

[Install]
WantedBy=multi-user.target
```

3. **Enable and start the service:**
```bash
sudo systemctl enable scripter
sudo systemctl start scripter
sudo systemctl status scripter
```

### Nginx Reverse Proxy Configuration

1. **Install Nginx:**
```bash
sudo apt-get update
sudo apt-get install nginx
```

2. **Create Nginx configuration:**
```bash
sudo nano /etc/nginx/sites-available/scripter
```

3. **Add the following configuration:**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /path/to/scripter/static;
        expires 30d;
    }
}
```

4. **Enable the site:**
```bash
sudo ln -s /etc/nginx/sites-available/scripter /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

### Docker Deployment

1. **Create a Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

RUN python migrate_db.py

EXPOSE 8000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
```

2. **Create docker-compose.yml:**
```yaml
version: '3.8'

services:
  scripter:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./instance:/app/instance
    environment:
      - FLASK_ENV=production
      - SECRET_KEY=${SECRET_KEY}
    restart: unless-stopped
```

3. **Build and run:**
```bash
docker-compose up -d
```

### Production Security Considerations

1. **SSL/TLS Configuration:**
   - Use Let's Encrypt for free SSL certificates
   - Configure Nginx to redirect HTTP to HTTPS
   
2. **Environment Variables:**
   - Never commit `.env` files to version control
   - Use strong, unique secret keys
   - Rotate secrets regularly

3. **Database:**
   - For production, consider using PostgreSQL or MySQL instead of SQLite
   - Regular backups of the database
   - Use connection pooling for better performance

4. **File Permissions:**
   - Ensure proper ownership of application files
   - Restrict write permissions to only necessary directories
   - Secure the instance directory containing the database

5. **Monitoring:**
   - Set up logging to track errors and access
   - Use monitoring tools like Prometheus or New Relic
   - Configure alerts for critical issues

### Backup and Recovery

1. **Database Backup:**
```bash
# SQLite backup
cp instance/scripter.db instance/backup/scripter_$(date +%Y%m%d).db

# PostgreSQL backup (if using PostgreSQL)
pg_dump scripter_db > backup/scripter_$(date +%Y%m%d).sql
```

2. **Automated Backups with Cron:**
```bash
# Add to crontab (crontab -e)
0 2 * * * /path/to/backup_script.sh
```

### Performance Optimization

1. **Enable caching:**
   - Configure Flask-Caching for template caching
   - Use Redis for session storage in production

2. **Database optimization:**
   - Add appropriate indexes for frequently queried fields
   - Use query optimization and eager loading

3. **Static file serving:**
   - Let Nginx serve static files directly
   - Enable gzip compression
   - Set appropriate cache headers

## Usage

### For Administrators

1. **Create a Script:**
   - Navigate to Scripts → Add New Script
   - Enter script details and create a Jinja2 template
   - Use the "Detect Variables" feature to automatically identify template variables
   - Add form fields for each variable

2. **Manage Form Fields:**
   - Define field types, labels, and validation rules
   - Set default values and help text
   - Reorder fields using drag-and-drop

3. **Template Features:**
   - Syntax highlighting for Jinja2 templates
   - Variable detection and validation
   - Export templates with variable documentation

### For End Users

1. Access available scripts from the homepage
2. Fill out the form with required information
3. Preview the generated output
4. Download or save the generated script

## API Endpoints

- `/api/scripts/<id>/detect_variables` - Detect variables in a template
- `/api/scripts/<id>/fields/<field_id>` - Get field details
- `/api/scripts/<id>/fields/create` - Create a new field
- `/api/scripts/<id>/fields/<field_id>/update` - Update a field
- `/api/scripts/<id>/fields/<field_id>/delete` - Delete a field
- `/api/scripts/<id>/fields/reorder` - Reorder fields

## Troubleshooting

### Common Issues

1. **Port Already in Use:**
   - Change the port in app.py or gunicorn command
   - Check for other services using the port: `lsof -i :5000`

2. **Database Migration Errors:**
   - Ensure the instance directory exists
   - Check file permissions
   - Run `python migrate_db.py` to update schema

3. **Authentication Issues:**
   - Verify TACACS+ server settings if using external auth
   - Check user roles and permissions
   - Ensure session secret key is set

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Specify your license here]

## Support

For issues and questions, please use the GitHub issue tracker or contact the maintainers
