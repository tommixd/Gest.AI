Gest.AI

An AI-powered document automation and management system designed to streamline the generation and processing of academic and contractual documents.

Developed as a final-year university project, it leverages local Large Language Models (LLMs) and a Retrieval-Augmented Generation (RAG) architecture to automate the drafting of complex administrative contracts, ensuring relational data integrity and secure, local processing.

## Key Features

* **Automated Document Generation:** Dynamically generates populated `.docx` contractual templates based on user input and institutional rules.
* **Relational Data Integrity:** Robust MySQL database architecture enforcing strict relationships between faculty members, course loads, templates, and generated contracts.
* **Local AI Processing:** Utilizes a locally hosted Qwen LLM via LangChain, ensuring that sensitive institutional data never leaves the server.
* **RAG Implementation:** Features a custom document loader and vector store to allow the AI agent to accurately query and reference previously generated contracts.
* **Web Interface:** Built with Flask for a lightweight, efficient backend and user-friendly interaction.

## Tech Stack

* **Backend:** Python 3, Flask
* **Database:** MySQL, `mysql-connector-python`
* **AI & NLP:** LangChain, Local LLM (Qwen GGUF)
* **Document Processing:** `python-docx`

## Prerequisites

To run this project locally, you will need:
* Python 3.8+ (3.11 recommended)
* MySQL Server (local or remote)
* A local copy of the Qwen model in `.gguf` format (placed in the appropriate directory).

## Installation & Setup

**1. Clone the repository**
```bash
git clone [https://github.com/tommixd/Gest.AI.git](https://github.com/tommixd/Gest.AI.git)
cd Gest.AI

**2. Create and activate a virtual environment** *(recommended)*

```bash
python3 -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

**3. Install the Python dependencies**

```bash
pip install -r requirements.txt
```

**4. Set up the MySQL database**

Create a database and import the provided SQL schema:

```bash
mysql -u root -p -e "CREATE DATABASE basedadosgestai;"
mysql -u root -p gestai < path/to/BaseDadosGestAI.sql
```

**5. Configure environment variables**

Create a `.env` file in the project root with your database credentials and any other required settings:

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=BaseDadosGestAI
```

**6. Download the local LLM (Qwen GGUF)**

Download the model file and place it in the **same directory as `app.py`**:

```bash
wget https://huggingface.co/bartowski/Qwen2.5.1-Coder-7B-Instruct-GGUF/resolve/main/Qwen2.5.1-Coder-7B-Instruct-Q4_K_M.gguf
```

**7. Run the application**

```bash
python app.py
```

The app should now be running locally — check your terminal output for the address (typically `http://localhost:5000`).
