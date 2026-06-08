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
