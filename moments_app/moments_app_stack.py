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
    aws_logs as logs,
)
from constructs import Construct
import common.constants as constants
from common.stack_context import StackContext


class MomentsAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.context = StackContext(scope=self)
        self.aws_region = self.context.aws_region

        # Configure Lambda code and layers
        self.code = _lambda.Code.from_asset("lambdas")
        self.layers = [
            _lambda.LayerVersion.from_layer_version_arn(
                self,
                self.context.build_resource_id("LambdaPowerToolsLayer"),
                layer_version_arn=self.context.build_power_tools_layer_arn(),
            ),
        ]

        # S3 bucket for static site hosting
        self.static_site_bucket = self._build_s3_static_site_bucket()

        # SQS dead letter queues for messages that were failed to be proccessed
        self.gmail_processor_dlq = self._build_gmail_processor_dlq()

        # SQS queues for asynchronous message processing
        self.gmail_queue = self._build_gmail_retriever_queue(self.gmail_processor_dlq)

        # DynamoDB table for storing processed emails
        self.moments_table = self._build_dynamodb()

        self.gmail_processor_log_group = self.context.build_log_group(
            "Function", action=constants.ACTION_PROCESSOR
        )
        self.gmail_retriever_log_group = self.context.build_log_group(
            "Function", action=constants.ACTION_RETRIEVER
        )

        # Lambda function for processing emails from SQS and writing to DynamoDB table
        self.gmail_processor_lambda = self._build_gmail_processor_lambda(
            table=self.moments_table,
            queue=self.gmail_queue,
            dlq=self.gmail_processor_dlq,
            log_group=self.gmail_processor_log_group,
        )
        # Lambda function consuming emails from gmail
        self.gmail_retriever_lambda = self._build_gmail_retriever_lambda(
            queue=self.gmail_queue, log_group=self.gmail_retriever_log_group
        )

        # API Gateway
        self._build_api_gateway_http_api(
            gmail_retriever_lambda=self.gmail_retriever_lambda
        )

        # Permissions
        # retriever Lambda permissions
        self.gmail_queue.grant_send_messages(self.gmail_retriever_lambda)
        self.moments_table.grant_read_write_data(self.gmail_retriever_lambda)

        # Processor Lambda permissions
        self.gmail_queue.grant_consume_messages(self.gmail_processor_lambda)
        self.moments_table.grant_read_write_data(self.gmail_processor_lambda)

    # Resource creation

    def _build_gmail_processor_lambda(
        self,
        table: dynamodb.ITable,
        queue: sqs.IQueue,
        dlq: sqs.IQueue,
        log_group: logs.ILogGroup,
    ) -> _lambda.Function:
        gmail_processor_function = _lambda.Function(
            self,
            id=self.context.build_resource_id(
                "Function", action=constants.ACTION_PROCESSOR
            ),
            runtime=constants.PYTHON_RUNTIME,
            handler="gmail_processor.handler",
            code=self.code,
            function_name=self.context.build_resource_name(
                "Function", action=constants.ACTION_PROCESSOR
            ),
            architecture=constants.DEFAULT_ARCHITECTURE,
            description=f"Processes messages from SQS {queue.queue_name} and writes to DynamoDB {table.table_name} with idempotency",
            dead_letter_queue=dlq,
            dead_letter_queue_enabled=True,
            layers=self.layers,
            environment={
                "GMAIL_QUEUE_URL": queue.queue_url,
                "MOMENTS_TABLE": self.moments_table.table_name,
                "SECRET_NAME": constants.GMAIL_RETRIEVER_SECRET_NAME,
                "POWERTOOLS_IDEMPOTENCY_TABLE_NAME": "place_holder_table_name",
            },
            timeout=Duration.seconds(60),
            memory_size=256,
            tracing=_lambda.Tracing.ACTIVE,
            log_group=log_group,
            retry_attempts=2,
            reserved_concurrent_executions=6,
        )
        gmail_processor_function.add_event_source(
            lambda_event_sources.SqsEventSource(
                queue,
                batch_size=4,
                max_concurrency=4,
                max_batching_window=Duration.seconds(30),
                report_batch_item_failures=True,
            )
        )
        return gmail_processor_function

    def _build_gmail_processor_dlq(self) -> sqs.Queue:
        """Build the Gmail processor DLQ."""
        return sqs.Queue(
            self,
            self.context.build_resource_id("DLQ", action=constants.ACTION_PROCESSOR),
            queue_name=self.context.build_resource_name(
                "DLQ", action=constants.ACTION_PROCESSOR
            ),
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

    def _build_dynamodb(self):
        moments_table = dynamodb.Table(
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
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
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
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

    def _build_api_gateway_http_api(self, gmail_retriever_lambda: _lambda.Function):
        """Create HTTP API and integrate it with the Gmail retriever Lambda."""
        http_api = apigwv2.HttpApi(
            self,
            self.context.build_resource_id("API"),
            api_name=self.context.build_resource_name("API"),
            create_default_stage=True,
        )

        # Define Lambda integration
        integration = apigwv2_integrations.HttpLambdaIntegration(
            self.context.build_resource_id("Integration"),
            handler=cast(_lambda.IFunction, gmail_retriever_lambda),
        )

        # Add route
        http_api.add_routes(
            path="/gmail/retriever",
            methods=[apigwv2.HttpMethod.GET],
            integration=integration,
        )

        return http_api

    def _build_gmail_retriever_queue(self, gmail_processor_dlq: sqs.IQueue) -> sqs.Queue:
        """Create the main queue with a DLQ."""
        return sqs.Queue(
            self,
            self.context.build_resource_id("Queue"),
            queue_name=self.context.build_resource_name("Queue"),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            visibility_timeout=Duration.seconds(90),
            retention_period=Duration.days(14),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=gmail_processor_dlq,
            ),
        )

    def _build_gmail_retriever_lambda(
        self, queue: sqs.IQueue, log_group: logs.ILogGroup
    ) -> _lambda.Function:
        """Define Gmail retriever Lambda function and connect it to SQS."""
        gmail_retriever_lambda = _lambda.Function(
            self,
            self.context.build_resource_id("Function", action=constants.ACTION_RETRIEVER),
            function_name=self.context.build_resource_name(
                "Function", action=constants.ACTION_RETRIEVER
            ),
            runtime=constants.PYTHON_RUNTIME,
            handler="gmail_retriever.handler",
            code=self.code,
            timeout=Duration.seconds(30),
            architecture=constants.DEFAULT_ARCHITECTURE,
            memory_size=512,
            tracing=_lambda.Tracing.ACTIVE,
            log_group=log_group,
            layers=self.layers,
            reserved_concurrent_executions=6,
            environment={
                "LOG_LEVEL": "INFO",
                "GMAIL_QUEUE_URL": queue.queue_url,
                "SECRET_NAME": constants.GMAIL_RETRIEVER_SECRET_NAME,
            },
        )
        return gmail_retriever_lambda
