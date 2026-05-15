FROM python:3.11-slim

# Ishchi papkani belgilash
WORKDIR /app

# Tizim paketlarini yangilash (docx parsing uchun kerak bo'lishi mumkin)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Kutubxonalar ro'yxatini nusxalash va o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Hamma kodlarni konteynerga nusxalash
COPY . .

# Botni ishga tushirish
CMD ["python", "bot.py"]