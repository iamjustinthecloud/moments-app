import os
from typing import Mapping, Any, Optional
import pytest
from aws_cdk.assertions import Template, Match
from aws_cdk import App
from moments_app.moments_app_stack import MomentsAppStack


def find_resources_by_type(
    template: Template, resource_type: str, props: Optional[dict] = None
) -> Mapping[str, Any]:

    return template.find_resources(resource_type, props=props)


def get_single_resource_id(
    resources: Mapping[str, Any], resource_type: str = "resource"
) -> str:

    assert (
        len(resources) == 1
    ), f"Expected exactly 1 {resource_type}, found {len(resources)}:{list(resources.keys())}"
    return next(iter(resources))


def build_template(stack_id: str = "TestMomentsAppStack"):
    app = App()
    stack = MomentsAppStack(app, stack_id)
    return Template.from_stack(stack)


@pytest.fixture
def template(monkeypatch) -> Template:
    monkeypatch.setenv("SKIP_BUNDLING", "1")
    monkeypatch.setenv("CDK_DISABLE_ASSET_STAGING", "1")
    return build_template()


@pytest.fixture
def json_template(template: Template) -> Mapping[str, Any]:
    return template.to_json()


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
        },
    )


def test_table_billing_mode_is_pay_per_request(template: Template):
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "BillingMode": "PAY_PER_REQUEST",
        },
    )


def test_table_resource_level_properties(
    template: Template,
    json_template: Mapping[str, Any],
    resource_type: str = "AWS::DynamoDB::Table",
):
    table = find_resources_by_type(template, resource_type)
    logical_id = get_single_resource_id(table, resource_type)

    assert json_template["Resources"][logical_id]["DeletionPolicy"] == "Delete"
    assert json_template["Resources"][logical_id]["UpdateReplacePolicy"] == "Delete"


# ------------------- S3 Bucket tests -------------------
def test_bucket_has_public_access_block_properties(template: Template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
        },
    )


def test_bucket_has_server_side_encryption(template: Template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            }
        },
    )


def test_bucket_has_auto_delete_object_properties(template: Template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {"Tags": [{"Key": "aws-cdk:auto-delete-objects", "Value": "true"}]},
    )


def test_bucket_resource_level_properties(
    template: Template,
    json_template: Mapping[str, Any],
    resource_type: str = "AWS::S3::Bucket",
):
    bucket = find_resources_by_type(template, resource_type)
    logical_id = get_single_resource_id(bucket, resource_type)

    assert json_template["Resources"][logical_id]["UpdateReplacePolicy"] == "Delete"
    assert json_template["Resources"][logical_id]["DeletionPolicy"] == "Delete"


# -------------------- Lambda Function tests ----------------------------


def test_gmail_ingestor_runtime(template: Template):
    # Match only the Gmail Ingestor function and allow CDK Refs for env vars
    template.has_resource_properties(
        "AWS::Lambda::Function",
        Match.object_like(
            {
                "Handler": "gmail_ingestor.handler",
                "Runtime": "python3.12",
                "MemorySize": 128,
                "Timeout": 10,
                "TracingConfig": {"Mode": "Active"},
                "Environment": {
                    "Variables": {
                        "LOG_LEVEL": "INFO",
                        "DEAD_LETTER_QUEUE_URL": Match.any_value(),
                        "MOMENTS_TABLE": Match.any_value(),
                        "SECRET_NAME": "moments_gmail_ingestor_oauth_client_id",
                        "REGION_NAME": Match.any_value(),
                    }
                },
            }
        ),
    )


def test_lambda_uses_asset_code(template: Template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        Match.object_like(
            {
                "Handler": "gmail_ingestor.handler",
                "Code": {"ZipFile": Match.any_value()},
            }
        ),
    )

@pytest.mark.parametrize("skip", ["1", None])
def test_gmail_layers_and_code_paths(monkeypatch, skip):
    if skip is None:
        monkeypatch.delenv("SKIP_BUNDLING", raising=False)
    else:
        monkeypatch.setenv("SKIP_BUNDLING", skip)
    monkeypatch.setenv("CDK_DISABLE_ASSET_STAGING", "1")
    template = build_template()

    if skip == "1":
        template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "Handler": "gmail_ingestor.handler",
                "Code": {"ZipFile": Match.any_value()},
            }),
        )
    else:
        template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "Handler": "gmail_ingestor.handler",
                "Code": {"S3Bucket": Match.any_value(), "S3Key": Match.any_value()},
            }),
        )
        layer_resources = template.find_resources("AWS::Lambda::LayerVersion")
        assert len(layer_resources) >= 1
        common_layer_id = next(iter(layer_resources))
        template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "FunctionName": "moments-gmail-ingestor-function-dev",
                "Layers": Match.array_with([Match.object_like({"Ref": common_layer_id})]),
            }),
        )
