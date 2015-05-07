from flask import Flask, g, request, render_template, redirect, abort, url_for
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import current_user, UserMixin, LoginManager
from flask.ext.admin import Admin
from flask.ext.admin.contrib.sqla import ModelView
from flask.ext.bootstrap import Bootstrap
from flask_wtf import Form
from wtforms.validators import DataRequired, Required, ValidationError
from wtforms import StringField, SubmitField
from sqlalchemy import Column, Unicode, Integer, ForeignKey, DateTime, Float, \
    Boolean, func, UnicodeText
from sqlalchemy.orm import relationship, backref
import crypt
import base64
import os
import datetime
import markdown
from markupsafe import Markup

db = SQLAlchemy()

class Location(db.Model):
    __tablename__ = "location"

    id = Column(Integer, primary_key=True)
    name = Column(Unicode)
    address = Column(UnicodeText)
    lat = Column(Float)
    lng = Column(Float)
    url = Column(Unicode)

    def __str__(self):
        return self.name


class Event(db.Model):
    __tablename__ = "event"
    
    id = Column(Integer, primary_key=True)
    slug = Column(Unicode, unique=True, index=True)
    name = Column(Unicode)
    location_id = Column(Integer, ForeignKey('location.id'))
    location = relationship('Location')

    text = Column(UnicodeText)

    date = Column(DateTime, index=True)

    @property
    def editable(self):
        return self.date > datetime.datetime.now()

class Attendee(db.Model):
    __tablename__ = "attendee"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('event.id'))
    user_id = Column(Integer, ForeignKey('user.id'))
    name = Column(Unicode)
    timestamp = Column(DateTime, default=func.now())
    event = relationship('Event', backref=backref('attendees',
                                                  order_by=timestamp))
    user = relationship('User', backref=backref('attended',
                                                order_by=timestamp))
    client_id = Column(Unicode)

    @property
    def display_name(self):
        if self.user:
            return self.user.name
        else:
            return self.name

    def __init__(self, event, user=None, name=None):
        if user is None:
            self.client_id = g.client_id
        
        self.user = user
        self.event = event
        self.name = name
        

class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    login = Column(Unicode, unique=True, index=True)
    password = Column(Unicode)
    name = Column(Unicode)
    email = Column(Unicode)
    is_admin = Column(Boolean)

    def check_password(self, password):
        if self.password == password or \
           self.password == crypt.crypt(password, self.password):
            return True
        else:
            return False
        
    def change_password(self, new_password):
        salt = '$1$' + base64.b64encode(os.urandom(6)) + '$'
        self.password = crypt.crypt(new_password, salt)

    @classmethod
    def load_user(cls, user_id):
        u = cls.query.get(user_id)
        if not u:
            return None
        if not u.enabled:
            return None
        return u

    @classmethod
    def authenticate(cls, login, password):
        u = cls.query.filter_by(login=login).first()
        if not u:
            return None
        if not u.enabled:
            return None
        if u.check_password(password):
            return u
        else:
            return None



app = Flask(__name__)
app.config.from_object('default_config')
app.config.from_envvar('PATEK_CONFIG')

Bootstrap(app)

l = LoginManager(app)
db.init_app(app)
admin = Admin(app)

@app.template_filter()
def asmarkdown(s):
    return Markup(markdown.markdown(s))

admin.add_view(ModelView(Location, db.session))
admin.add_view(ModelView(Event, db.session))
admin.add_view(ModelView(User, db.session))

class MyModelView(ModelView):
    def is_accessible(self):
        return login.current_user.is_authenticated()

@app.before_request
def get_client_id():
    client_id = request.cookies.get('client_id')
    if client_id is None:
        client_id = base64.b64encode(os.urandom(18))
    g.client_id = client_id

@app.after_request
def set_client_id(response):
    response.set_cookie('client_id', g.client_id)
    return response

class AttendForm(Form):
    name = StringField('Jmeno:', [Required()])
    captcha = StringField('5+3 = (slovy)')
    ok = SubmitField('Prihlasit')
    def validate_captcha(form, field):
        if field.data.lower() != 'osm':
            raise ValidationError('Ne, neni')


@app.route('/', methods=['GET', 'POST'])
@app.route('/<slug>', methods=['GET', 'POST'])
def event(slug=None):
    if slug is None:
        e = Event.query.order_by(Event.date.desc()).first()
    else:
        e = Event.query.filter_by(slug=slug).one()

    f = AttendForm()

    if f.validate_on_submit():
        a = Attendee(e, name=f.name.data)
        db.session.add(a)
        db.session.commit()
        return redirect(request.url)

    return render_template('event.html', e=e, attend_form=f)

@app.route('/attendee/<atid>/delete', methods=['POST'])
def delete_attendee(atid):
    a = Attendee.query.get(atid)
    if current_user != a.user and g.client_id != a.client_id:
        abort(403)
        
    slug = a.event.slug
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for('event', slug=slug))


@app.before_first_request
def init_db():
    db.create_all()

if __name__ == '__main__':
    app.debug = True
    app.run(port=5090, host="0.0.0.0")
