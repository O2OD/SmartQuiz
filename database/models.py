import datetime
from sqlalchemy import BigInteger, String, Integer, JSON, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, mapped_column, Mapped

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String, nullable=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class Quiz(Base):
    __tablename__ = 'quizzes'
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'))
    subject: Mapped[str] = mapped_column(String)
    time_limit: Mapped[int] = mapped_column(Integer)
    questions: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class Result(Base):
    __tablename__ = 'results'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'))
    quiz_id: Mapped[str] = mapped_column(String, ForeignKey('quizzes.id', ondelete='CASCADE'))
    score: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    time_spent: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)