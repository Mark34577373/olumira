from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, EmailField, SelectField, TextAreaField
from wtforms.validators import InputRequired, Length, EqualTo, ValidationError
from email_validator import EmailNotValidError
from services.authentication import normalize_email, password_error


class LoginForm(FlaskForm):
    email = EmailField('Email address', validators=[InputRequired(), Length(max=254)])
    password = PasswordField('Password', validators=[InputRequired(), Length(max=128)])


class RegistrationForm(FlaskForm):
    display_name = StringField('Display name', validators=[InputRequired(), Length(min=1, max=80)])
    email = EmailField('Email address', validators=[InputRequired(), Length(max=254)])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=15, max=128, message='Use 15–128 characters.')])
    confirm_password = PasswordField('Confirm password', validators=[InputRequired(), EqualTo('password', message='The passwords must match.')])

    def validate_display_name(self, field):
        field.data = field.data.strip()
        if not field.data:
            raise ValidationError('Enter a display name.')

    def validate_email(self, field):
        try:
            field.data = normalize_email(field.data)
        except EmailNotValidError:
            raise ValidationError('Enter a valid email address.') from None

    def validate_password(self, field):
        message = password_error(field.data)
        if message:
            raise ValidationError(message)


class EmailRequestForm(FlaskForm):
    email = EmailField('Email address', validators=[InputRequired(), Length(max=254)])


class LinkForm(FlaskForm):
    recovery_code = StringField('Recovery code', validators=[InputRequired(), Length(min=43, max=43, message='Paste the complete code from your email.')])


class ResetPasswordForm(LinkForm):
    password = PasswordField('New password', validators=[InputRequired(), Length(min=15, max=128)])
    confirm_password = PasswordField('Confirm new password', validators=[InputRequired(), EqualTo('password', message='The passwords must match.')])

    def validate_password(self, field):
        message = password_error(field.data)
        if message:
            raise ValidationError(message)


class ProfileForm(FlaskForm):
    display_name = StringField('Display name', validators=[InputRequired(), Length(min=1, max=80)])

    def validate_display_name(self, field):
        field.data = field.data.strip()
        if not field.data:
            raise ValidationError('Enter a display name.')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current password', validators=[InputRequired(), Length(max=128)])
    password = PasswordField('New password', validators=[InputRequired(), Length(min=15, max=128)])
    confirm_password = PasswordField('Confirm new password', validators=[InputRequired(), EqualTo('password', message='The passwords must match.')])

    def validate_password(self, field):
        message = password_error(field.data)
        if message:
            raise ValidationError(message)


class ChangeEmailForm(FlaskForm):
    email = EmailField('New email address', validators=[InputRequired(), Length(max=254)])
    current_password = PasswordField('Current password', validators=[InputRequired(), Length(max=128)])

    def validate_email(self, field):
        try:
            field.data = normalize_email(field.data)
        except EmailNotValidError:
            raise ValidationError('Enter a valid email address.') from None


class ConfirmPasswordForm(FlaskForm):
    current_password = PasswordField('Current password', validators=[InputRequired(), Length(max=128)])


class ContactForm(FlaskForm):
    """Bounded validation even while delivery is explicitly unavailable."""
    name = StringField('Name', validators=[InputRequired(), Length(max=80)])
    email = EmailField('Email', validators=[InputRequired(), Length(max=254)])
    inquiry = SelectField('Inquiry type', choices=[('general', 'General question'), ('beta', 'Beta interest'), ('feedback', 'Product feedback'), ('support', 'Technical support'), ('other', 'Other')])
    message = TextAreaField('Message', validators=[InputRequired(), Length(max=2000)])
    website = StringField('Leave this field empty', validators=[Length(max=0)])

    def validate_email(self, field):
        try:
            field.data = normalize_email(field.data)
        except EmailNotValidError:
            raise ValidationError('Enter a valid email address.') from None

    def validate_name(self, field):
        if not field.data.strip():
            raise ValidationError('Enter a name.')

    def validate_message(self, field):
        if not field.data.strip():
            raise ValidationError('Enter a message.')
