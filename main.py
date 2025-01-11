from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import create_engine, or_, desc
from sqlalchemy.orm import sessionmaker, Session
from models import Base, User, City, DefaultCity
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime, timedelta
import csv
import aiohttp

"""
This file contains the main backend code for the web app which allows users to register
and load weather data for their particular list of cities.

Main app functionality:
* Register using username and password
* Login using username and password
* Logout
* View the list of cities and their temperatures
* Be able to add a new city by its name and coordinates
* Update the list of temperatures

The app uses FastAPI for handling HTTP requests, SQLite as a database, 
and SQLAlchemy ORM for mapping between database and the app.

User authentication and session handling is done using JWT tokens.
"""

# Database setup
DATABASE_URL = "sqlite:///./cities.db"
# SQLite, by default, does not allow connections to be shared across threads.
# So "check_same_thread": False allows to do it.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
# This disables automatic committing of transactions and flushing of changes to the database
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Create tables
Base.metadata.create_all(bind=engine)

# Setup FastAPI app
app = FastAPI()
# This allows us to use /static folder where CSS file is stored
app.mount("/static", StaticFiles(directory="static"), name="static")
# This defines the folder where HTML templates are stored
templates = Jinja2Templates(directory="templates")

# Create foundation for signed user token
COOKIE_NAME = "user_session"
SECRET_KEY = "123456"
serializer = URLSafeTimedSerializer(SECRET_KEY)

# Utility functions

# This establishes a connection to the database
# yield is used instead of return
# to make it a generator function, returning db to the caller for use
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# This creates a signed token using salt
def create_token(user_id: int):
    return serializer.dumps({"user_id": user_id}, salt="salt_registration")

# This deserializes and verifies the token
def validate_token(session_token: str):
    try:
        return serializer.loads(session_token, salt="salt_registration", max_age=3600)
    except SignatureExpired:
        return None
    except BadSignature:
        return None

# This gets information about the current user
# based on the data stored in the token (if token exists)
async def get_current_user(request: Request):
    session_token = request.cookies.get(COOKIE_NAME)
    if not session_token:
        return None
    data = validate_token(session_token)
    if not data:
        return None
    db = SessionLocal()
    user = db.query(User).filter(User.id == data["user_id"]).first()
    db.close()
    if not user:
        return None
    return user

# This sets the cryptographic context for hashing and verifying passwords
# using bscrupt algorithm
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# This hashes the givebn password
def hash_password(password: str):
    return pwd_context.hash(password)

# This verifies the given plain and hashed passwords
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

# This gets the city temperature by its coordinates
# via open-meteo.com API
async def fetch_weather(latitude: float, longitude: float):
    async with aiohttp.ClientSession() as session:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current_weather=true"
        async with session.get(url) as response:
            data = await response.json()
            return data["current_weather"]["temperature"]

# Routes

# This adds a new city for a user via POST /cities/add
@app.post("/cities/add")
async def add_city(name: str = Form(...), latitude: float = Form(...), longitude: float = Form(...), db: SessionLocal = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    city = City(name=name, latitude=latitude, longitude=longitude, user_id=user.id)
    db.add(city)
    db.commit()
    return RedirectResponse("/", status_code=303)

# This removes a city for a user via POST /cities/remove/{city_id}
@app.post("/cities/remove/{city_id}")
async def remove_city(city_id: int, db: SessionLocal = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    city = db.query(City).filter(City.id == city_id, City.user_id == user.id).first()
    if city:
        db.delete(city)
        db.commit()
    return RedirectResponse("/", status_code=303)

# This resets the list of cities for a user via POST /cities/reset
# by copying it from the default list
@app.post("/cities/reset")
async def reset_cities(db: SessionLocal = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db.query(City).filter(City.user_id == user.id).delete()
    default_cities = db.query(DefaultCity).all()
    for city in default_cities:
        db.add(City(name=city.name, latitude=city.latitude, longitude=city.longitude, user_id=user.id))
        db.commit()
    return RedirectResponse("/", status_code=303)

# This updates city temperatures for a user via POST /cities/update
# for empty cities or those cities that were updated more than 1 min ago
@app.post("/cities/update")
async def update_weather(db: SessionLocal = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    delta = datetime.utcnow() - timedelta(minutes=1)
    cities = db.query(City).filter(City.user_id == user.id, or_(City.temperature == None, City.updated_at < delta)).all()
    for city in cities:
        city.temperature = await fetch_weather(city.latitude, city.longitude)
        city.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/", status_code=303)

# This populates the default list of cities on the app startup
@app.on_event("startup")
def populate_default_cities():
    db = SessionLocal()
    if not db.query(DefaultCity).first():
        with open("europe.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                db.add(DefaultCity(name=row["name"], latitude=float(row["latitude"]), longitude=float(row["longitude"])))
        db.commit()
    db.close()

# This handles user registration via POST /register (checks whether this is a new user,
# adds user to the database, populates cities from the default list, sets session cookie)
@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...), db: SessionLocal = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed_password = hash_password(password)
    user = User(username=username, password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    default_cities = db.query(DefaultCity).all()
    for city in default_cities:
        city = City(name=city.name, latitude=city.latitude, longitude=city.longitude, user_id=user.id)
        db.add(city)
    db.commit()
    session_token = create_token(user.id)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(key=COOKIE_NAME)
    response.set_cookie(key=COOKIE_NAME, value=session_token, httponly=True, max_age=3600)
    return response

# This handles user login via POST /login (checks the credentials, sets session cookie)
@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username.ilike(form_data.username)).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    session_token = create_token(user.id)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(key=COOKIE_NAME)
    response.set_cookie(key=COOKIE_NAME, value=session_token, httponly=True, max_age=3600)
    return response

# This handles user logout via POST /logout
@app.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(key=COOKIE_NAME)
    return response

# This handles request to main page via GET /index.html and returns the user and cities 
# to be used on the UI (also redirects to login if there is no session token or user doesn't exist)
@app.get("/")
async def read_root(request: Request, db: SessionLocal = Depends(get_db)):
    session_token = request.cookies.get(COOKIE_NAME)
    if not session_token:
        return RedirectResponse("/login", status_code=303)
    data = validate_token(session_token)
    if not data:
        return RedirectResponse("/login", status_code=303)
    user = db.query(User).filter(User.id == data["user_id"]).first()
    if not user:
        return RedirectResponse("/login", status_code=303)
    cities = db.query(City).filter(City.user_id == user.id).order_by(desc(City.temperature)).all()
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "cities": cities})

# This handles request to the registration form via GET /register.html 
@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

# This handles request to the login form via GET /login.html 
@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})