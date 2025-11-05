import os
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, TypedDict

import boto3
from attrs import asdict, define, field
from attrs.validators import instance_of
from aws_lambda_powertools.logging.logger import Logger
from aws_lambda_powertools.tracing import Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

logger: Logger = Logger(
    service="gmail-ingestor", level=os.getenv("LOG_LEVEL", "INFO").upper()
)
tracer: Tracer = Tracer(service="gmail-ingestor")

moments_table = os.environ.get("MOMENTS_TABLE")
dynamodb_endpoint = os.getenv("DYNAMODB_ENDPOINT", None)
dynamodb_resource = boto3.resource("dynamodb", endpoint_url=dynamodb_endpoint)


class GmailHeader(TypedDict):
    name: str
    value: str


class GmailPayload(TypedDict):
    headers: list[GmailHeader]


class GmailMessage(TypedDict):
    id: str
    labelIds: list[str]
    payload: GmailPayload


class ResponseMetadataBody(TypedDict):
    http_status_code: int


class ErrorBody(TypedDict):
    code: str
    message: str
    response_metadata: ResponseMetadataBody


class StatusBody(TypedDict):
    status_code: int
    message: str


@define(slots=True, kw_only=True, frozen=True)
class EmailRecord:
    from_address: str = field(validator=instance_of(str))  # Partition Key
    message_id: str = field(validator=instance_of(str))  # Sort Key
    subject: str = field(validator=instance_of(str))
    date: str = field(validator=instance_of(str))
    time: str = field(validator=instance_of(str))
    labels: list[str] = field(factory=list, validator=instance_of(list))
    ingested_at: str = field(factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = field(default="NEW", validator=instance_of(str))
    action: str = field(default="apply_label", validator=instance_of(str))


def _response(e: ClientError) -> dict[str, Any]:
    response = e.response
    error_info = response.get("Error", {})
    code = error_info.get("Code", "Unknown")
    message = error_info.get("Message", "Unknown")
    meta_data = response.get("ResponseMetadata", {})
    status = meta_data.get("HTTPStatusCode", 500)
    return {
        "code": code,
        "message": message,
        "response_metadata": {"http_status_code": status},
    }


@tracer.capture_method
def build_ddb_item_from_gmail_dict(message: GmailMessage) -> EmailRecord:
    headers = message["payload"]["headers"]

    header_map = {header["name"].lower(): header["value"] for header in headers}

    from_raw = header_map["from"]
    subject = header_map["subject"]
    date_sent = header_map["date"]

    _, from_address = parseaddr(from_raw)
    parse_date = parsedate_to_datetime(date_sent)
    date_dd_mm_yyyy = parse_date.strftime("%d/%m/%Y")
    date_h_m_s = parse_date.strftime("%H:%M:%S")

    return EmailRecord(
        message_id=message["id"],
        from_address=from_address,
        subject=subject,
        date=date_dd_mm_yyyy,
        time=date_h_m_s,
    )


@tracer.capture_method
def _put_item(table_name: str, message: GmailMessage) -> None:
    table = dynamodb_resource.Table(table_name)
    ddb_item = asdict(build_ddb_item_from_gmail_dict(message))
    table.put_item(Item=ddb_item)


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: GmailMessage, context: LambdaContext) -> None:
    put_item_into_dynamodb(event=event, context=context)


def put_item_into_dynamodb(event: GmailMessage, context: LambdaContext) -> dict[str, Any]:
    try:

        if not moments_table:
            logger.error("MOMENTS_TABLE environment variable missing — cannot continue.")
            return {
                "status_code": 200,
                "message": "Configuration environment variable missing",
            }

        logger.info("Putting item into DynamoDB", table=moments_table)

        _put_item(table_name=moments_table, message=event)
        logger.info("Successfully put item into DynamoDB", table=moments_table)
        return {"status_code": 200, "message": "Item successfully written to DynamoDB"}

    except ClientError as e:
        logger.exception("Put item failed on DynamoDB", table=moments_table)
        return _response(e)
    except Exception as e:
        logger.exception("An unknown error occurred during put_item_into_dynamodb")
        return {"status_code": 500, "message": str(e)}
