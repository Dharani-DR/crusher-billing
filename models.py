from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from flask_login import UserMixin

Base = declarative_base()

class User(UserMixin, Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default='user')
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    bills = relationship('Bill', back_populates='user')

class Customer(Base):
    __tablename__ = 'customers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    gst_number = Column(String(50), nullable=True)
    phone = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    bills = relationship('Bill', back_populates='customer')

class Vehicle(Base):
    __tablename__ = 'vehicles'
    
    id = Column(Integer, primary_key=True)
    vehicle_number = Column(String(50), unique=True, nullable=False)
    vehicle_type = Column(String(50), nullable=True)  # e.g., "Truck", "Lorry"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    bills = relationship('Bill', back_populates='vehicle')

class Item(Base):
    __tablename__ = 'items'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    rate = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    bills = relationship('Bill', back_populates='item')

class Bill(Base):
    __tablename__ = 'bills'
    
    id = Column(Integer, primary_key=True)
    bill_no = Column(String(50), unique=True, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'), nullable=True)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False)
    quantity = Column(Float, nullable=False)
    rate = Column(Float, nullable=False)
    total = Column(Float, nullable=False)  # quantity * rate
    gst = Column(Float, nullable=False, default=0.0)  # GST amount
    grand_total = Column(Float, nullable=False)  # total + gst
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    customer = relationship('Customer', back_populates='bills')
    vehicle = relationship('Vehicle', back_populates='bills')
    item = relationship('Item', back_populates='bills')
    user = relationship('User', back_populates='bills')

class CompanySettings(Base):
    __tablename__ = 'company_settings'
    
    id = Column(Integer, primary_key=True)
    company_name_tamil = Column(Text, nullable=True)
    company_name_english = Column(String(200), nullable=True)
    address_tamil = Column(Text, nullable=True)
    address_english = Column(Text, nullable=True)
    gstin = Column(String(50), nullable=True)
    phone_numbers = Column(String(200), nullable=True)  # Comma-separated
    footer_message = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

