from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

"""
This file contains definitions of future database tables and corresponding objects
that will be created using SQLAlchemy ORM.

We'll have 3 tables in the DB:
* users -- contains list of users (User object)
* cities -- contains list of cities for a particular user (City object)
* default_cities -- contains the default list of cities copied to each new user (DefaultCity object)
"""

# This constructs a base class for object definitions
Base = declarative_base()

class User(Base):
    """
    User class defines the users table which will contain usernames and hashed passwords
    for each user. This table is related to cities.
    """
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    cities = relationship("City", back_populates="user")

class City(Base):
    """
    City class defines the cities table which will contain cities for a particular user.
    This table will related to users via users.id foreign key.
    """
    __tablename__ = "cities"
    id = Column(Integer, primary_key=True, index=True)
    # City name shouldn't be unique in this table as several users can have the same city
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    temperature = Column(Float, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="cities")

class DefaultCity(Base):
    __tablename__ = "default_cities"
    id = Column(Integer, primary_key=True, index=True)
    # Here the city name should be unique
    name = Column(String, unique=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)