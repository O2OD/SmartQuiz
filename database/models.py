import datetime
from sqlalchemy import Column, BigInteger, String, Integer, JSON, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# O'zbekiston vaqtini olish uchun yordamchi funksiya (UTC+5)
def get_uzb_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5)))

class User(Base):
    __tablename__ = 'users'
    user_id = Column(BigInteger, primary_key=True)
    full_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    created_at = Column(DateTime, default=get_uzb_time)

class Quiz(Base):
    __tablename__ = 'quizzes'
    id = Column(String, primary_key=True)
    owner_id = Column(BigInteger)
    subject = Column(String)
    time_limit = Column(Integer)
    questions = Column(JSON)
    play_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_uzb_time)

class Result(Base):
    __tablename__ = 'results'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    quiz_id = Column(String)
    score = Column(Integer)
    total = Column(Integer)
    time_spent = Column(Integer)
    created_at = Column(DateTime, default=get_uzb_time)