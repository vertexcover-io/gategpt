# custom-gpts-paywall

**custom-gpts-paywall** is an experimental Python service designed to provide various authentication, verification, and paywall functionalities for OpenAI's custom-gpts. Currently, it includes the following implemented actions:

- Email Verification

## Installation

This project utilizes the [Rye package manager](https://github.com/ryelabs/rye) for dependency management. Ensure that you have Rye installed before proceeding.

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/custom-gpts-paywall.git
   cd custom-gpts-paywall
   ```

2. Install project dependencies using Rye:

   ```bash
   rye sync
   ```

3. Create a copy of the environment variable template file:

   ```bash
   cp .env.template .env
   ```

4. Edit the `.env` file and set the required environment variables according to your configuration.

## How to Run

You can run the project both with and without Docker.

### Without Docker

1. Set the database URL in the `.env` file to point to your PostgreSQL instance.

2. Start the development server:

   ```bash
   rye run dev
   ```

### With Docker

1. Build and start the Docker containers:

   ```bash
   rye run docker-run
   ```
<hr/>

** Note: You might need to run migrations before able to use this project

## Migrations

### With Docker

- To upgrade the database to the latest version:

  ```bash
  rye run docker-upgrade head
  ```

- To downgrade the database:

  ```bash
  rye run docker-downgrade base
  ```

- To create a new migration revision:

  ```bash
  rye run docker-revision
  ```

### Without Docker

- To upgrade the database to the latest version:

  ```bash
  rye run upgrade head
  ```

- To downgrade the database:

  ```bash
  rye run downgrade base
  ```

- To create a new migration revision:

  ```bash
  rye run revision
  ```

## Pre-Commit

Set up pre-commit hooks to automatically check your code for linting and formatting issues. Run the following command to install pre-commit hooks:

```bash
rye run pre-commit install
```

## Format and Lint

This project uses [Ruff](https://github.com/ryelabs/ruff) for code formatting and linting. Use the following commands to format and lint your code:

- Format code:

  ```bash
  rye run format
  ```

- Check for linting issues:

  ```bash
  rye run lint
  ```

For more information, refer to the [Ruff documentation](https://github.com/ryelabs/ruff).

## OpenAPI Specifications

You can access the OpenAPI specifications for this project using the following endpoints:

- Swagger UI: [/docs]
- ReDoc: [/redoc]
- OpenAPI JSON: [/openapi.json]
