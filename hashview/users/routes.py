"""Flask routes to handle Users"""
import uuid
from datetime import datetime
from textwrap import dedent

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_bcrypt import Bcrypt
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from hashview.models import (
    Customers,
    Hashfiles,
    Jobs,
    Rules,
    TaskGroups,
    Tasks,
    Users,
    Wordlists,
    db,
)
from hashview.users.forms import (
    LoginForm,
    ProfileForm,
    RequestResetForm,
    ResetPasswordForm,
    UsersForm,
)
from hashview.utils.utils import send_email, send_pushover

bcrypt = Bcrypt()


def _safe_next(default_endpoint='users.profile'):
    """Return a safe same-site redirect target from ?next= / form 'next', else the
    default endpoint. Lets the account-settings modal (in the layout) return the user
    to the page they opened it from. Guards against open-redirects."""
    nxt = request.values.get('next')
    if nxt and nxt.startswith('/') and not nxt.startswith('//'):
        return nxt
    return url_for(default_endpoint)


login_manager = LoginManager()
login_manager.login_view = 'users.login_get'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))


users = Blueprint('users', __name__)


@users.route("/login", methods=['GET'])
def login_get():
    """Function to present login page"""

    form = LoginForm()
    return render_template('login.html.j2', title='Login', form=form)

@users.route("/login", methods=['POST'])
def login_post():
    """Function to handle login requests"""

    def failed():
        flash('Login Unsuccessful. Please check email and password', 'danger')
        return render_template('login.html.j2', title='Login', form=form)

    form = LoginForm()
    if not form.validate_on_submit():
        current_app.logger.info('Login is Complete with Failure(Form Validation).')
        return failed()

    user = Users.query.filter_by(email_address=form.email.data).first()
    if not user:
        current_app.logger.info('Login is Complete with Failure(Invalid User from Email:%s).', form.email.data)
        return failed()

    if not bcrypt.check_password_hash(user.password, form.password.data):
        current_app.logger.info('Login is Complete with Failure(Invalid Password).')
        return failed()

    login_user(user, remember=form.remember.data)
    user.last_login_utc = datetime.utcnow()
    db.session.commit()
    current_app.logger.info('Login is Complete with Success(User:%s).', user.email_address)
    return redirect(
        request.args.get("next", url_for('main.home'))
    )

@users.route("/logout")
def logout():
    """Function to handle logout requests"""

    logout_user()
    return redirect(url_for('main.home'))

@users.route("/users", methods=['GET', 'POST'])
@login_required
def users_list():
    """Function to list users"""

    users = Users.query.all()
    jobs = Jobs.query.all()
    wordlists = Wordlists.query.all()
    rules = Rules.query.all()
    tasks = Tasks.query.all()
    task_groups = TaskGroups.query.all()
    hashfiles = Hashfiles.query.all()
    customers = Customers.query.all()
    return render_template('users.html.j2', title='Users', users=users, jobs=jobs, wordlists=wordlists, rules=rules, tasks=tasks, task_groups=task_groups, hashfiles=hashfiles, customers=customers, usersForm=UsersForm())

@users.route("/users/add", methods=['GET', 'POST'])
@login_required
def users_add():
    """Function to add new user"""

    if current_user.admin:
        form = UsersForm()
        if form.validate_on_submit():
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('latin-1')
            if form.pushover_app_id.data and form.pushover_user_key.data:
                user = Users(first_name=form.first_name.data, last_name=form.last_name.data, email_address=form.email.data, admin=form.is_admin.data, password=hashed_password, pushover_app_id=form.pushover_app_id.data, pushover_user_key=form.pushover_user_key.data)
            else:
                user = Users(first_name=form.first_name.data, last_name=form.last_name.data, email_address=form.email.data, admin=form.is_admin.data, password=hashed_password)
            db.session.add(user)
            db.session.commit()
            # Optional "send invite email" toggle from the add-user modal. Best-effort:
            # send_email already swallows errors / returns False if mail isn't configured.
            if request.form.get('send_invite'):
                send_email(user, 'Your Hashview account',
                           f'An account has been created for you on Hashview. '
                           f'Sign in with your email address ({user.email_address}).')
            flash(f'Account created for {form.email.data}!', 'success')
            return redirect(url_for('users.users_list'))
        return render_template('users_add.html.j2', title='User Add', form=form)
    else:
        flash('Unauthorized to add users account.', 'danger')
        return redirect(url_for('users.users_list'))

@users.route("/users/edit/<int:user_id>", methods=['POST'])
@login_required
def users_edit(user_id):
    """Update an existing user's name, email, role, and (optionally) password.

    Driven by the edit-user modal, which mirrors the add-user modal. Password fields
    are optional on edit — left blank, the current password is kept.
    """
    if not current_user.admin:
        flash('Unauthorized to edit users account.', 'danger')
        return redirect(url_for('users.users_list'))

    user = Users.query.get_or_404(user_id)
    first = (request.form.get('first_name') or '').strip()
    last = (request.form.get('last_name') or '').strip()
    email = (request.form.get('email') or '').strip()
    is_admin = bool(request.form.get('is_admin'))
    password = request.form.get('password') or ''
    confirm = request.form.get('confirm_password') or ''

    if not (first and last and email):
        flash('First name, last name, and email are required.', 'danger')
        return redirect(url_for('users.users_list'))

    # Email must be unique, but the user keeping their own email is fine.
    clash = Users.query.filter_by(email_address=email).first()
    if clash and clash.id != user.id:
        flash('That email address is taken. Please choose a different one.', 'danger')
        return redirect(url_for('users.users_list'))

    if password:
        if len(password) < 14:
            flash('Password must be at least 14 characters.', 'danger')
            return redirect(url_for('users.users_list'))
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('users.users_list'))
        user.password = bcrypt.generate_password_hash(password).decode('latin-1')

    user.first_name = first
    user.last_name = last
    user.email_address = email
    user.admin = is_admin
    db.session.commit()
    flash(f'Account updated for {email}!', 'success')
    return redirect(url_for('users.users_list'))

@users.route("/users/delete/<int:user_id>", methods=['POST'])
@login_required
def users_delete(user_id):
    """Function to delete user"""

    if current_user.admin:
        user = Users.query.get_or_404(user_id)
        db.session.delete(user)
        db.session.commit()
        flash('User has been deleted!', 'success')
        return redirect(url_for('users.users_list'))
    else:
        flash('Unauthorized to delete users account.', 'danger')
        return redirect(url_for('users.users_list'))

@users.route("/profile", methods=['GET', 'POST'])
@login_required
def profile():
    """Function to display user profile"""

    form = ProfileForm()
    if form.validate_on_submit():
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.email_address = form.email.data
        if form.pushover_user_key.data:
            current_user.pushover_user_key = form.pushover_user_key.data
        if form.pushover_app_id.data:
            current_user.pushover_app_id = form.pushover_app_id.data
        db.session.commit()
        flash('Profile Updated!', 'success')
        return redirect(_safe_next())
    elif request.method == 'GET':
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.email.data = current_user.email_address
    return render_template('profile.html.j2', title='Profile', form=form, current_user=current_user)

@users.route("/profile/send_test_pushover", methods=['GET'])
@login_required
def send_test_pushover():
    """Function to test pushover notification"""

    user = Users.query.get(current_user.id)
    send_pushover(user, 'Test Message From Hashview', 'This is a test pushover message from hashview')
    flash('Pushover Sent', 'success')
    return redirect(_safe_next())

@users.route("/profile/send_test_email", methods=['GET'])
@login_required
def send_test_email():
    """Function to test send email"""

    user = Users.query.get(current_user.id)
    if send_email(user, 'Test Message From Hashview', 'This is a test email message from hashview'):
        flash('Email Sent', 'success')
    else:
        flash('Email Failure. Check SMTP settings.', 'danger')
    return redirect(_safe_next())

@users.route("/profile/generate_api_key", methods=['GET'])
@login_required
def generate_api_key():
    """Function to generate API key"""

    user = Users.query.get(current_user.id)
    user.api_key = str(uuid.uuid4())
    db.session.commit()
    flash('New API Key Set', 'success')
    return redirect(_safe_next())

@users.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    """Function to present password reset request"""

    form = RequestResetForm()
    if form.validate_on_submit():
        user = Users.query.filter_by(email_address=form.email.data).first()
        if user:
            token = user.get_reset_token()
            subject = 'Password Reset Request.'
            message = f'''To reset your password, vist the following link:
    {url_for('users.reset_token', user_id=user.id, token=token, _external=False)}

    If you did not make this request... then something phishy is going on.
    '''
            send_email(user, subject, message)
        flash('An email has been sent to '+  form.email.data, 'info')
        return redirect(url_for('users.login_get'))
    return render_template('reset_request.html.j2', title='Reset Password', form=form)

@users.route("/admin_reset_password/<int:user_id>", methods=['GET', 'POST'])
@login_required
def admin_reset(user_id):
    """Function to manage admin initiated password reset"""

    if not current_user.admin:
        flash('Unauthorized to reset users account.', 'danger')
        return redirect(url_for('users.users_list'))

    user = Users.query.get(user_id)
    token = user.get_reset_token()
    subject = 'Password Reset Request.'
    message = dedent(f'''\
        To reset your password, vist the following link:
        {url_for('users.reset_token', user_id=user_id, token=token, _external=True)}

        If you did not make this request... then something phishy is going on.
    ''')
    send_email(user, subject, message)
    flash('An email has been sent to '+  user.email_address, 'info')
    return redirect(url_for('users.users_list'))


@users.route("/reset_password/<int:user_id>/<string:token>", methods=['GET', 'POST'])
def reset_token(user_id :int, token :str):
    """Function to manage password reset token"""

    user = Users.query.get(user_id)
    if not user:
        flash('Invalid User Id!', 'warning')
        return redirect(url_for('main.home'))

    if not user.verify_reset_token(token):
        flash('Invalid or Expired Token!', 'warning')
        return redirect(url_for('main.home'))

    form = ResetPasswordForm()
    if not form.validate_on_submit():
        return render_template('reset_token.html.j2', title='Reset Password', form=form)

    else:
        hashed_password = bcrypt.generate_password_hash(form.password.data)
        user.password = hashed_password
        db.session.commit()
        flash('Your password has been updated! You are now able to login.', 'success')
        return redirect(url_for('users.login_get'))

# Promote a user to admin
@users.route("/users/promote/<int:user_id>", methods=['POST'])
@login_required
def promote_user(user_id):
    if not current_user.admin:
        abort(403)
    user = Users.query.get_or_404(user_id)
    user.admin = True
    db.session.commit()
    flash(f'User {user.email_address} promoted to admin.', 'success')
    return redirect(url_for('users.users_list'))

# Demote a user to regular user
@users.route("/users/demote/<int:user_id>", methods=['POST'])
@login_required
def demote_user(user_id):
    if not current_user.admin:
        abort(403)
    user = Users.query.get_or_404(user_id)
    user.admin = False
    db.session.commit()
    flash(f'User {user.email_address} demoted to regular user.', 'success')
    return redirect(url_for('users.users_list'))
