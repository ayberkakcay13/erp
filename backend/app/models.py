from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class Customer(Base):
    __tablename__ = 'customers'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    sales = relationship('Sale', back_populates='customer', cascade='all, delete-orphan')

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    sku = Column(String(50), unique=True, nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    sales_items = relationship('SalesItem', back_populates='product')

class Sale(Base):
    __tablename__ = 'sales'
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    sale_date = Column(Date, nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)
    customer = relationship('Customer', back_populates='sales')
    items = relationship('SalesItem', back_populates='sale', cascade='all, delete-orphan')

class SalesItem(Base):
    __tablename__ = 'sales_items'
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey('sales.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    sale = relationship('Sale', back_populates='items')
    product = relationship('Product', back_populates='sales_items')

class Invoice(Base):
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey('sales.id'), unique=True)
    invoice_number = Column(String(50), unique=True)
    customer_id = Column(Integer, ForeignKey('customers.id'))
    issued_date = Column(Date)
    total_amount = Column(Float)
    status = Column(String(20), default='draft')
    created_at = Column(DateTime, default=datetime.utcnow)
