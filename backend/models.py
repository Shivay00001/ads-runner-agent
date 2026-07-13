from sqlalchemy import Column, Integer, String, Text, DateTime
from database import Base
import datetime

class Setting(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(Text)

class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, index=True)
    product_url = Column(Text)
    description = Column(Text)
    budget = Column(String)
    model_provider = Column(String) 
    
    status = Column(String) # pending, running, success, error
    
    campaign_json = Column(Text, nullable=True) 
    csv_output = Column(Text, nullable=True) 
    
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
