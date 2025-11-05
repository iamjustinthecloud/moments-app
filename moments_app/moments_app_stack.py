from typing import cast

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_event_sources,
    aws_s3 as s3,
    aws_sqs as sqs,
)
from aws_cdk.aws_lambda_python_alpha import PythonLayerVersion
from constructs import Construct

import common.constants as constants
from common.stack_context import StackContext


class MomentsAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.context = StackContext(scope=self)
        self.aws_region = self.context.aws_region

        # Queues
        gmail_ingestor_dlq = self._build_gmail_ingestor_dlq()
        self.gmail_queue = self._build_gmail_ingestor_queue(gmail_ingestor_dlq)
        # DynamoDB Table
        self.moments_table = self._build_dynamodb()

        self.common_layer = self._build_common_layer()

        # Lambda function
        self.gmail_ingestor_lambda = self._build_gmail_ingestor_lambda(
            gmail_queue=self.gmail_queue,
            gmail_ingestor_dlq=gmail_ingestor_dlq,
            moments_table=self.moments_table,
        )
        # API Gateway
        self._build_api_gateway_http_api(gmail_ingestor_lambda=self.gmail_ingestor_lambda)
        self.moments_table.grant_read_write_data(self.gmail_ingestor_lambda)

    # Resource creation

    def _build_dynamodb(self):
        moments_table = dynamodb.TableV2(
            self,
            id=self.context.build_resource_id("Table"),
            table_name=self.context.build_resource_name("Table"),
            partition_key=dynamodb.Attribute(
                name="from_address",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="subject",
                type=dynamodb.AttributeType.STRING,
            ),
            removal_policy=RemovalPolicy.DESTROY,
            billing=dynamodb.Billing.on_demand(),
        )
        moments_table.add_global_secondary_index(
            index_name="StatusIndex",
            partition_key=dynamodb.Attribute(
                name="status",
                type=dynamodb.AttributeType.STRING,
            ),
        )
        return moments_table

    def _build_s3_static_site_bucket(self):
        """Create the S3 Bucket with web assets."""
        return s3.Bucket(
            self,
            self.context.build_resource_id("WebAssets"),
            removal_policy=RemovalPolicy.DESTROY,
            bucket_name=self.context.build_resource_name("WebAssets"),
            auto_delete_objects=True,
        )

    def _build_api_gateway_http_api(self, gmail_ingestor_lambda: _lambda.Function):
        """Create HTTP API and integrate it with the Gmail Ingestor Lambda."""
        http_api = apigwv2.HttpApi(
            self,
            self.context.build_resource_id("API"),
            api_name=self.context.build_resource_name("API"),
            create_default_stage=True,
        )

        # Define Lambda integration
        integration = apigwv2_integrations.HttpLambdaIntegration(
            self.context.build_resource_id("Integration"),
            handler=cast(_lambda.IFunction, gmail_ingestor_lambda),
        )

        # Add route
        http_api.add_routes(
            path="/gmail/ingestor",
            methods=[apigwv2.HttpMethod.GET],
            integration=integration,
        )

        return http_api

    def _build_gmail_ingestor_queue(self, gmail_ingestor_dlq: sqs.IQueue) -> sqs.Queue:
        """Create the main queue with a DLQ."""
        return sqs.Queue(
            self,
            self.context.build_resource_id("Queue"),
            queue_name=self.context.build_resource_name("Queue"),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=gmail_ingestor_dlq,
            ),
        )

    def _build_gmail_ingestor_dlq(self) -> sqs.Queue:
        """Create the dead-letter queue for the Gmail Ingestor Lambda."""
        return sqs.Queue(
            self,
            self.context.build_resource_id("DLQ"),
            queue_name=self.context.build_resource_name("DLQ"),
            retention_period=Duration.days(14),
        )

    def _build_common_layer(self) -> PythonLayerVersion:
        """Create and return a shared Python layer for AWS Lambda Powertools."""
        return PythonLayerVersion(
            self,
            self.context.build_resource_id("CommonLayer"),
            entry=constants.COMMON_LAYER_SRC,
            compatible_architectures=[constants.DEFAULT_ARCHITECTURE],
            compatible_runtimes=[constants.PYTHON_RUNTIME],
        )

    def _build_gmail_ingestor_lambda(
        self,
        gmail_queue: sqs.IQueue,
        gmail_ingestor_dlq: sqs.IQueue,
        moments_table: dynamodb.ITableV2,
    ) -> _lambda.Function:
        """Define Gmail ingestor Lambda function and connect it to SQS."""

        self.context.build_log_group("Function")

        gmail_ingestor_lambda = _lambda.Function(
            self,
            self.context.build_resource_id("Function"),
            function_name=self.context.build_resource_name("Function"),
            runtime=constants.PYTHON_RUNTIME,
            handler="gmail_ingestor.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(10),
            memory_size=128,
            tracing=_lambda.Tracing.ACTIVE,
            layers=[
                self.common_layer,
                _lambda.LayerVersion.from_layer_version_arn(
                    self,
                    self.context.build_resource_id("LambdaPowerToolsLayer"),
                    layer_version_arn=self.context.build_power_tools_layer_arn(),
                ),
            ],
            environment={
                "LOG_LEVEL": "INFO",
                "DEAD_LETTER_QUEUE_URL": gmail_ingestor_dlq.queue_url,
                "MOMENTS_TABLE": moments_table.table_name,
                "SECRET_NAME": constants.GMAIL_SECRET_NAME,
                "REGION_NAME": self.aws_region,
            },
        )
        gmail_ingestor_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                gmail_queue,
                batch_size=10,
                max_batching_window=Duration.seconds(30),
                report_batch_item_failures=True,
            )
        )
        return gmail_ingestor_lambda
