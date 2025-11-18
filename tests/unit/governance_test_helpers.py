from enum import Enum


def resource_governance_doc_url(resource: str) -> str:
    governance_doc_url = f"https://moments-internal-docs/{resource}-governance"
    return governance_doc_url


class AWSService(str, Enum):
    Lambda = "lambda"
    Log_Group = "log-group"
    S3 = "s3"
    IAM_Role = "iam"
    Api_GatewayV2 = "api-gateway-v2"
    SQS = "sqs"
    DynamoDB = "dynamodb"
