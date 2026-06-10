"""Forms Page to manage Tasks"""
from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, ValidationError

from hashview.models import Tasks


class TasksForm(FlaskForm):
    name = StringField('Name', validators=([DataRequired()]))
    hc_attackmode = SelectField('Attack Mode', choices=[(0, 'Straight (Wordlist w/Rules)'),
                                                        (1, 'Combination (Wordlist1, Rule1, Wordlist2, Rule2)'),
                                                        (3, 'Brute-force (A.K.A. Maskmode)'),
                                                        (6, 'Hybrid (Wordlist + Mask)'),
                                                        (7, 'Hybrid (Mask + Wordlist)')], coerce=int, validators=[InputRequired()])  # dictionary, maskmode, bruteforce, combinator
    wl_id = SelectField('Wordlist', choices=[])
    wl_id_2 = SelectField('Second Wordlist', choices=[])
    rule_id = SelectField('Rules', choices=[])
    j_rule = StringField('-j rule (i.e. $-)')
    k_rule = StringField('-k rule (i.e. $!)')
    mask = StringField('Hashcat Mask')
    loopback = BooleanField('Enable loopback')
    submit = SubmitField('Create')

    def validate_task(self, name):
        """Function to validate Task name group"""

        task = Tasks.query.filter_by(name = name.data).first()
        if task:
            raise ValidationError('That task name is taken. Please choose a different one.')
