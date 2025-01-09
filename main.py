from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base, User, City, DefaultCity
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime
import csv
import aiohttp

# Database setup
DATABASE_URL = "sqlite:///./cities.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

# FastAPI setup
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Session
SECRET_KEY = "123456"
SESSION_NAME = "user_session"
serializer = URLSafeTimedSerializer(SECRET_KEY)

# Utility functions
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_session(user_id: int) -> str:
    return serializer.dumps(user_id, salt=SESSION_NAME)

def verify_session(session_token: str) -> int:
    try:
        return serializer.loads(session_token, salt=SESSION_NAME, max_age=3600)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

async def get_current_user(request: Request):
    session_token = request.cookies.get(SESSION_NAME)
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = verify_session(session_token)
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

async def fetch_weather(latitude: float, longitude: float):
    async with aiohttp.ClientSession() as session:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current_weather=true"
        async with session.get(url) as response:
            data = await response.json()
            return data["current_weather"]["temperature"]

# Routes
@app.post("/cities/add")
async def add_city(name: str = Form(...), latitude: float = Form(...), longitude: float = Form(...), db: SessionLocal = Depends(get_db), user: User = Depends(get_current_user)):
    city = City(name=name, latitude=latitude, longitude=longitude, user_id=user.id)
    db.add(city)
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/cities/remove/{city_id}")
async def remove_city(city_id: int, db: SessionLocal = Depends(get_db)):
    city = db.query(City).filter(City.id == city_id).first()
    if city:
        db.delete(city)
        db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/cities/reset")
async def reset_cities(db: SessionLocal = Depends(get_db)):
    db.query(City).delete()
    default_cities = db.query(DefaultCity).all()
    for default in default_cities:
        db.add(City(name=default.name, latitude=default.latitude, longitude=default.longitude))
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/cities/update")
async def update_weather(db: SessionLocal = Depends(get_db)):
    cities = db.query(City).all()
    for city in cities:
        city.temperature = await fetch_weather(city.latitude, city.longitude)
        city.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/", status_code=303)

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

@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...), db: SessionLocal = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed_password = hash_password(password)
    user = User(username=username, password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    print("New user: ", user)
    default_cities = db.query(DefaultCity).all()
    for city in default_cities:
        city = City(name=city.name, latitude=city.latitude, longitude=city.longitude, user_id=user.id)
        print("City: ", city)
        db.add(city)
    db.commit()
    session_token = create_session(user.id)
    print("Token:", session_token)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(key="user_session", value=session_token, httponly=True, max_age=3600)
    return response

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username.ilike(form_data.username)).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    session_token = create_session(user.id)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(key="user_session", value=session_token, httponly=True, max_age=3600)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(key="user_session")
    return response

@app.get("/")
async def read_root(request: Request, db: SessionLocal = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    cities = db.query(City).filter(City.user_id == user.id).all()
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "cities": cities})

@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})