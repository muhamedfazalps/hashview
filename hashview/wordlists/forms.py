"""Forms Page to manage Wordlists"""
from flask_wtf import FlaskForm
from wtforms import FileField, StringField, SubmitField
from wtforms.validators import DataRequired


class WordlistsForm(FlaskForm):
    """Class representing Wordlist Form"""

    name = StringField('Name', validators=[DataRequired()])
    wordlist = FileField('Upload Wordlist')
    submit = SubmitField('upload')
