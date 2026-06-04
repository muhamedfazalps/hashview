"""Forms Page to manage Settings"""
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    IntegerField,
    StringField,
    SubmitField,
    ValidationError,
)
from wtforms.validators import DataRequired, NumberRange


class HashviewSettingsForm(FlaskForm):
    """Class representing an Settings Forms"""

    retention_period = StringField('Retention Period (in days)', validators=[DataRequired()])
    max_runtime_jobs = StringField('Maximum runtime per Job in hours. (0 = infinate)', validators=[DataRequired()])
    max_runtime_tasks = StringField('Maximum runtime per Task in hours. (0 = infinate)', validators=[DataRequired()])
    enabled_job_weights = BooleanField('Allow users to set job priority during job creations.')
    # Website-keywords crawler settings
    crawl_min_word_length = IntegerField('Minimum word length', validators=[DataRequired(), NumberRange(min=1, max=65535)])
    crawl_user_agent = StringField('Crawler user-agent', validators=[DataRequired()])
    crawl_force_lowercase = BooleanField('Force crawled words to lowercase.')
    crawl_depth = IntegerField('Crawl depth', validators=[DataRequired(), NumberRange(min=1, max=100)])
    crawl_threads = IntegerField('Crawler threads', validators=[DataRequired(), NumberRange(min=1, max=256)])
    submit = SubmitField('Update')

    def validate_rention_period(self, retention_period):
        """Function to validate retention period range"""
        if int(retention_period.data) < 1 or int(retention_period.data) > 65535:
            raise ValidationError('Range must be between 1 and 65535.')

    def validate_max_runtime(self, max_runtime_jobs, max_runtime_tasks):
        """Function to validate max runtime period range"""
        if max_runtime_jobs < 0 or max_runtime_jobs > 65535:
            raise ValidationError('Range must be between 0 and 65535.')
        if max_runtime_tasks < 0 or max_runtime_tasks > 65535:
            raise ValidationError('Range must be between 0 and 65535.')


class DatabaseBackupForm(FlaskForm):
    """CSRF-only form backing the (fetch-driven) database backup action."""

    submit = SubmitField('Back up database')
