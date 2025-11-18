import json
import os
from typing import Any
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities import parameters
from botocore.exceptions import ClientError

logger = Logger(
    service="gmail-retrieve-payload", level=os.getenv("LOG_LEVEL", "INFO").upper()
)
secret_name = os.getenv("SECRET_NAME")
tracer = Tracer(service="gmail-retrieve-payload")
secret_name = os.environ.get("SECRET_NAME", None)


def handler(event: dict[str, Any], context: Any) -> None:
    get_secret(event=event, context=context)


def get_secret(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        if not secret_name:
            logger.error("SECRET_NAME environment variable not set")
        secret_value = parameters.get_secret(secret_name)
        logger.info("Successfully retrieved secret from Secrets Manager")
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Successfully retrieved secret.",
                    "secret": secret_name,
                    "secret_value": secret_value,
                }
            ),
        }

    except ClientError as e:
        response = e.response or {}
        error_info = response.get("Error", {})
        error_code = error_info.get("Code", "UnknownError")
        error_message = error_info.get("Message")

        meta_data = response.get("ResponseMetadata", {})
        status_code = meta_data.get("HTTPStatusCode", "UnknownStatusCode")
        logger.error(
            f"Failed to retrieve the secret {secret_name}: {status_code} - {error_message}"
        )
        return {
            "statusCode": status_code,
            "body": json.dumps(
                {
                    "error": error_code,
                    "message": error_message,
                }
            ),
        }
    except Exception as e:
        # Catch-all for unexpected issues
        logger.exception("Unhandled exception in Lambda")
        return {
            "statusCode": 500,
            "body": json.dumps({"message": str(e)}),
        }
