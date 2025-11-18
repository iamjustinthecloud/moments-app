FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task
ENV DYNAMODB_ENDPOINT=http://host.docker.internal:8000
# Copy dependency manifests
COPY pyproject.toml poetry.lock ./

# Install Poetry and then install all dependencies into the global environment
RUN pip install --no-cache-dir "poetry==1.8.4" && \
    poetry config virtualenvs.create false && \
    poetry install --no-root --no-interaction --no-ansi && \
    pip install aws-xray-sdk

# Copy your Lambda function code
COPY lambdas/gmail_ingestor.py .

# Optional: cleaner output
ENV PYTHONUNBUFFERED=1

# Entry point for AWS Lambda runtime
CMD ["gmail_ingestor.handler"]
