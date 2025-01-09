from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    cities = relationship("City", back_populates="user")

class City(Base):
    __tablename__ = "cities"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    temperature = Column(Float, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="cities")

class DefaultCity(Base):
    __tablename__ = "default_cities"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)