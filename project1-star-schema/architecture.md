# FinMart Star Schema — Architecture

This document provides a high-level overview of the project structure and execution flow. Detailed modelling decisions are documented separately in `decisions.md`.

---

# Overview

Project 1 demonstrates a simple ETL pipeline that generates synthetic retail data, transforms it into a star schema, and performs analytical queries using DuckDB.

The project separates SQL transformations from Python orchestration, allowing warehouse logic to remain easy to review, modify, and maintain.

---

# Project Structure

```text
project1-star-schema/
│
├── architecture.md
├── decisions.md
├── analysis.py
├── analysis.sql
├── build_schema.py
├── build_schema.sql
├── generate_data.py
└── generate_data.sql

data/
│
└── project1_finmart.duckdb
```

The project source code and generated database are intentionally stored separately. Source files remain version-controlled, while the DuckDB database acts as the project's generated output.

---

# Execution Flow

```text
generate_data.py
        │
        ▼
project1_finmart.duckdb
        │
        ▼
build_schema.py
        │
        ▼
build_schema.sql
        │
        ▼
Star Schema
        │
        ▼
analysis.sql
        │
        ▼
analysis.py
        │
        ▼
Query Results
```

The database is created once during data generation and then reused throughout the remainder of the workflow.

---

# Component Responsibilities

| File                      | Responsibility                                            |
| ------------------------- | --------------------------------------------------------- |
| `generate_data.py`        | Generates synthetic retail data.                          |
| `generate_data.sql`       | SQL used during data generation.                          |
| `build_schema.py`         | Executes warehouse creation.                              |
| `build_schema.sql`        | Creates and populates the star schema.                    |
| `analysis.py`             | Executes analytical queries.                              |
| `analysis.sql`            | Analytical SQL used to demonstrate the warehouse.         |
| `project1_finmart.duckdb` | Stores the generated source data and completed warehouse. |

---

# Design Principles

## SQL as the source of truth

Business logic is implemented in SQL rather than embedded within Python. Python is responsible for orchestration, while SQL defines the warehouse schema and transformations.

This separation makes transformation logic easier to review and keeps SQL portable across database platforms.

---

## Separation of concerns

Each file has a single responsibility.

Python manages execution.

SQL performs transformations.

DuckDB stores the data.

Keeping these responsibilities separate makes the project easier to maintain and extend.

---

# Future Development

As additional portfolio projects are added, shared functionality may be extracted into a common `utils` package where it provides value across multiple projects.

Project 1 intentionally remains self-contained, with shared utilities introduced only when they eliminate duplication between projects.
