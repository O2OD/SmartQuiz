# 🧠 SmartQuiz Bot - Advanced Telegram Quiz Generation System

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Aiogram](https://img.shields.io/badge/Aiogram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Clean Architecture](https://img.shields.io/badge/Architecture-Repository_Pattern-005571?style=for-the-badge)

**SmartQuiz Bot** is an advanced, production-ready Telegram bot designed to automate the process of taking and managing quizzes. 

Unlike standard quiz bots where admins must manually input each question and its four options one by one, SmartQuiz introduces a **Bulk Upload Feature**. The admin simply uploads a structured `.docx` document, and the bot parses it instantly to generate a fully functioning quiz.

---

## 🚀 Key Features

*   **📄 Instant `.docx` Parsing (Killer Feature):** Admins can upload a Word document containing structured questions and marked correct answers. The bot parses the file in seconds and automatically converts it into a playable interactive quiz.
*   **⏸ Pause & Resume:** Users are not forced to complete a test in one sitting. They can pause their ongoing quiz and resume from the exact question they left off at any time.
*   **📚 Subject Categorization:** Quizzes are organized by subjects. Users can easily browse and select which subject they want to be tested on.
*   **📊 Real-time Statistics:** Users can see the total number of questions before starting and track their score as they progress.
*   **🔐 Admin Exclusivity:** Only authorized administrators have the rights to upload `.docx` files and manage quiz data.
*   **🏗 Clean Architecture:** Built using **Service** and **Repository** patterns, ensuring the codebase is scalable, maintainable, and highly decoupled.

---

## 🛠 Tech Stack

*   **Language:** Python 3.10+
*   **Framework:** Aiogram 3.x (Asynchronous Telegram Bot API)
*   **Database:** PostgreSQL
*   **ORM:** SQLAlchemy (for complex queries and database interactions)
*   **Document Parsing:** `python-docx`
*   **Containerization:** Docker & Docker Compose

---

## 📂 Project Structure

This project strictly follows best practices for scalable bot architecture:

    SmartQuiz/
    │
    ├── core/                # Core configurations, settings, and constants
    ├── database/            # SQLAlchemy models, migrations, and DB connection
    ├── handlers/            # Telegram message and callback query handlers
    ├── keyboards/           # Inline and Reply keyboard markups
    ├── repositories/        # Data access layer (Repository Pattern)
    ├── services/            # Business logic (e.g., .docx parsing, quiz logic)
    ├── bot.py               # Main entry point to run the bot
    ├── docker-compose.yml   # Multi-container Docker configuration
    ├── Dockerfile           # Docker image instructions for the bot
    ├── requirements.txt     # Python dependencies
    └── .env.sample          # Environment variables template

---

## ⚙️ Deployment & Setup (Docker)

The easiest and recommended way to run this bot is using Docker Compose.

**1. Clone the repository:**
```bash
git clone [https://github.com/YOUR_USERNAME/SmartQuiz.git](https://github.com/YOUR_USERNAME/SmartQuiz.git)
cd SmartQuiz
