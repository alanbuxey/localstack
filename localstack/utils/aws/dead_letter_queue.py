import json
import uuid
import logging
from localstack.utils.aws import aws_stack

LOG = logging.getLogger(__name__)


def sqs_error_to_dead_letter_queue(queue_arn, event, error):
    client = aws_stack.connect_to_service('sqs')
    queue_url = aws_stack.get_sqs_queue_url(queue_arn)
    attrs = client.get_queue_attributes(QueueUrl=queue_url, AttributeNames=['RedrivePolicy'])
    attrs = attrs.get('Attributes', {})
    policy = json.loads(attrs.get('RedrivePolicy') or '{}')
    target_arn = policy.get('deadLetterTargetArn')
    if not target_arn:
        return
    return _send_to_dead_letter_queue('SQS', queue_arn, target_arn, event, error)


def lambda_error_to_dead_letter_queue(func_details, event, error):
    dlq_arn = (func_details.dead_letter_config or {}).get('TargetArn')
    source_arn = func_details.id
    return _send_to_dead_letter_queue('Lambda', source_arn, dlq_arn, event, error)


def _send_to_dead_letter_queue(source_type, source_arn, dlq_arn, event, error):
    if not dlq_arn:
        return
    LOG.info('Sending failed execution %s to dead letter queue %s' % (source_arn, dlq_arn))
    message = json.dumps(event)
    message_attrs = {
        'RequestID': {'DataType': 'String', 'StringValue': str(uuid.uuid4())},
        'ErrorCode': {'DataType': 'String', 'StringValue': '200'},
        'ErrorMessage': {'DataType': 'String', 'StringValue': str(error)}
    }
    if ':sqs:' in dlq_arn:
        queue_url = aws_stack.get_sqs_queue_url(dlq_arn)
        sqs_client = aws_stack.connect_to_service('sqs')
        sqs_client.send_message(QueueUrl=queue_url, MessageBody=message, MessageAttributes=message_attrs)
    elif ':sns:' in dlq_arn:
        sns_client = aws_stack.connect_to_service('sns')
        sns_client.publish(TopicArn=dlq_arn, Message=message, MessageAttributes=message_attrs)
    else:
        LOG.warning('Unsupported dead letter queue type: %s' % dlq_arn)
