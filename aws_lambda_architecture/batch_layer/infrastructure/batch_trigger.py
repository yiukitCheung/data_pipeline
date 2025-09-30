import json
import boto3
import os

def lambda_handler(event, context):
    batch = boto3.client('batch')
    
    job_name = event.get('jobName', 'daily-resampling-job')
    job_definition = event.get('jobDefinition')
    job_queue = event.get('jobQueue')
    
    response = batch.submit_job(
        jobName=job_name,
        jobQueue=job_queue,
        jobDefinition=job_definition
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }
