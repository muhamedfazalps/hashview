"""Forms Page to manage Rules"""
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField, TextAreaField
from wtforms.validators import DataRequired


class RulesForm(FlaskForm):
    """Class representing an Rules Forms"""

    name = StringField('Name', validators=[DataRequired()])
    rules = FileField('Upload Rules')
    submit = SubmitField('upload')

class RulesEditForm(FlaskForm):
    """Class representing a Rules Edit Form"""
    name = StringField('Name', validators=[DataRequired()])
    content = TextAreaField('Contents', validators=[DataRequired()])
    submit = SubmitField('update')
