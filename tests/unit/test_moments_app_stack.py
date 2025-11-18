from typing import Mapping, Any, Optional
import pytest
from aws_cdk.assertions import Template, Match
from stack_test_helpers import (
    LambdaTestCase,
    LogGroupTestCase,
    find_resources_by_type,
    get_single_resource_id,
    template,
    expected_lambda_props,
    json_template,
)
from governance_checks import assert_s3_compliance
from tests.unit.stack_test_helpers import UpdateDeletePolicyTestCase

# ----------------------------- Resource count smoke test ------------------------

RESOURCES = [
    ("AWS::ApiGatewayV2::Api", 1),
    ("AWS::ApiGatewayV2::Integration", 1),
    ("AWS::ApiGatewayV2::Route", 1),
    ("AWS::ApiGatewayV2::Stage", 1),
    ("AWS::DynamoDB::Table", 1),
    ("AWS::IAM::Policy", 2),
    ("AWS::IAM::Role", 3),
    ("AWS::Lambda::Function", 3),
    ("AWS::Lambda::Permission", 1),
    ("AWS::Logs::LogGroup", 2),
    ("AWS::S3::Bucket", 1),
    ("AWS::S3::BucketPolicy", 1),
    ("AWS::SQS::Queue", 2),
]

LAMBDA_LAYER = [
    (r".*processor.*", r".*AWSLambdaPowertoolsPythonV3.*"),
    (r".*retriever.*", r".*AWSLambdaPowertoolsPythonV3.*"),
]


@pytest.mark.parametrize("resource_type,expected", RESOURCES)
def test_resource_count(template: Template, resource_type: str, expected: int):
    template.resource_count_is(resource_type, expected)


# -------------------------- Lambda configuration tests ------------------------


@pytest.mark.parametrize("function_name,expected", LAMBDA_LAYER)
def test_lambda_has_powertools_layer(
    template: Template, function_name: str, expected: str
):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        Match.object_like(
            {
                "FunctionName": Match.string_like_regexp(function_name),
                # CDK synthesizes the layer ARN using Fn::Join, so we match the
                # presence of a layer built via Fn::Join rather than a literal string.
                "Layers": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Fn::Join": [
                                    "",
                                    Match.array_with(
                                        [
                                            "arn:aws:lambda:",
                                            Match.object_like({"Ref": "AWS::Region"}),
                                            Match.string_like_regexp(expected),
                                        ]
                                    ),
                                ]
                            }
                        )
                    ]
                ),
            }
        ),
    )


# ------------------- DynamoDB table tests -------------------
def test_table_has_expected_properties(template: Template):
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "AttributeDefinitions": [
                {"AttributeName": "from_address", "AttributeType": "S"},
                {"AttributeName": "subject", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
            ],
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": "StatusIndex",
                    "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            "KeySchema": [
                {"AttributeName": "from_address", "KeyType": "HASH"},
                {"AttributeName": "subject", "KeyType": "RANGE"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
    )


# ------------------- Update/Delete Policy tests -------------------
UPDATE_DELETE_POLICY_CASE = [
    UpdateDeletePolicyTestCase(
        id="AWS::DynamoDB::Table", update_policy="Delete", delete_policy="Delete"
    ),
    UpdateDeletePolicyTestCase(
        id="AWS::S3::Bucket", update_policy="Delete", delete_policy="Delete"
    ),
]


@pytest.mark.parametrize("case", UPDATE_DELETE_POLICY_CASE, ids=lambda test: test.id)
def test_table_resource_level_properties(
    template: Template,
    json_template: Mapping[str, Any],
    case: UpdateDeletePolicyTestCase,
):
    resource_type = find_resources_by_type(template, case.id)
    logical_id = get_single_resource_id(resource_type, case.id)

    assert json_template["Resources"][logical_id]["DeletionPolicy"] == case.delete_policy
    assert (
        json_template["Resources"][logical_id]["UpdateReplacePolicy"]
        == case.update_policy
    )


# ------------------- S3 Bucket tests -------------------
def test_bucket_enforces_strict_access(template: Template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
        },
    )
    assert_s3_compliance(template)


# -------------------- Lambda Function Retriever tests ----------------------------


LAMBDA_TEST_CASES = (
    LambdaTestCase(
        id="gmail_retriever_function",
        handler="gmail_retriever.handler",
        function_name=r".*moments-gmail-ingestion-retriever-function.*",
        memory_size=256,
        timeout=30,
        extra_env={"LOG_LEVEL": "INFO"},
    ),
    LambdaTestCase(
        id="gmail_processor_function",
        handler="gmail_processor.handler",
        function_name=r".*moments-gmail-ingestion-processor-function.*",
        memory_size=256,
        timeout=60,
        extra_env={
            "GMAIL_QUEUE_URL": Match.object_like(
                {"Ref": Match.string_like_regexp(r".*MomentsGmailIngestionQueue.*")}
            ),
            "MOMENTS_TABLE": Match.object_like(
                {"Ref": Match.string_like_regexp(r".*MomentsGmailIngestionTable.*")}
            ),
            "POWERTOOLS_IDEMPOTENCY_TABLE_NAME": "place_holder_table_name",
        },
    ),
)


@pytest.mark.parametrize("case", LAMBDA_TEST_CASES, ids=lambda test: test.id)
def test_lambda_function_configuration(template: Template, case: LambdaTestCase):
    expected_props = expected_lambda_props(case)
    template.has_resource_properties(
        "AWS::Lambda::Function",
        Match.object_like(expected_props),
    )


def test_lambda_has_target_dlq_properties(template: Template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": Match.string_like_regexp(
                r".*moments-gmail-ingestion-processor-function.*"
            ),
            "DeadLetterConfig": {
                "TargetArn": {
                    "Fn::GetAtt": [
                        Match.string_like_regexp(
                            r".*MomentsGmailIngestionProcessorDlq.*"
                        ),
                        "Arn",
                    ]
                }
            },
        },
    )


def test_lambda_has_sqs_event_source_properties(template: Template):
    template.has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {
            "BatchSize": 4,
            "EventSourceArn": {
                "Fn::GetAtt": [
                    Match.string_like_regexp(r".*MomentsGmailIngestionQueue.*"),
                    "Arn",
                ],
            },
            "FunctionName": {
                "Ref": Match.string_like_regexp(
                    r".*MomentsGmailIngestionProcessorFunction.*"
                )
            },
            "FunctionResponseTypes": ["ReportBatchItemFailures"],
            "MaximumBatchingWindowInSeconds": 30,
        },
    )


# -------------------- SQS tests ----------------------------


def test_sqs_processor_dlq_properties(template: Template):
    template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": Match.string_like_regexp(
                r".*moments-gmail-ingestion-processor-dlq-.*"
            ),
            "MessageRetentionPeriod": 1209600,
            "SqsManagedSseEnabled": True,
        },
    )


def test_sqs_queue_properties(template: Template):
    template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": Match.string_like_regexp(r".*moments-gmail-ingestion-queue-.*"),
            "RedrivePolicy": {
                "deadLetterTargetArn": Match.any_value(),
                "maxReceiveCount": 3,
            },
            "SqsManagedSseEnabled": True,
        },
    )


def test_sqs_queue_has_dlq_target(template: Template):
    template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "RedrivePolicy": {
                "deadLetterTargetArn": {
                    "Fn::GetAtt": [
                        Match.string_like_regexp(
                            r".*MomentsGmailIngestionProcessorDlq.*"
                        ),
                        "Arn",
                    ]
                },
            }
        },
    )


# -------------------- Log Group tests ----------------------------


LOG_GROUP_TEST_CASES = (
    LogGroupTestCase(
        id="gmail_processor_log_group",
        log_group_name=r".*aws/lambda/moments-gmail-ingestion-processor-function.*",
        retention_days=365,
    ),
    LogGroupTestCase(
        id="gmail_receiver_log_group",
        log_group_name=r".*aws/lambda/moments-gmail-ingestion-retriever-function.*",
        retention_days=365,
    ),
)


@pytest.mark.parametrize("case", LOG_GROUP_TEST_CASES, ids=lambda test: test.id)
def test_processor_log_group_properties(template: Template, case: LogGroupTestCase):
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": Match.string_like_regexp(case.log_group_name),
            "RetentionInDays": case.retention_days,
        },
    )


# -------------------- API Gateway tests ----------------------------


def test_api_gateway_integration_properties(template: Template):
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Integration",
        {
            "ApiId": {"Ref": Match.string_like_regexp(r".*MomentsGmailIngestionApi.*")},
            "IntegrationUri": {
                "Fn::GetAtt": [
                    Match.string_like_regexp(
                        r".*MomentsGmailIngestionRetrieverFunction.*"
                    ),
                    "Arn",
                ]
            },
            "IntegrationType": "AWS_PROXY",
        },
    )


def test_api_gateway_stage_properties(template: Template):
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Stage",
        {
            "ApiId": {"Ref": Match.string_like_regexp(r".*MomentsGmailIngestionApi.*")},
            "AutoDeploy": True,
            "StageName": "$default",
        },
    )


def test_api_gateway_properties(template: Template):
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Api",
        {
            "Name": Match.string_like_regexp(r".*moments-gmail-ingestion-api.*"),
            "ProtocolType": "HTTP",
        },
    )


def test_api_gateway_route_properties(template: Template):
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Route", {"RouteKey": "GET /gmail/retriever"}
    )
