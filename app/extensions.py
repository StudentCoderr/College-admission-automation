"""Flask extension singletons (imported by the application factory)."""

from flask_login import LoginManager

from app.utils.security import CSRFProtect

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"

csrf = CSRFProtect()
