import json
import boto3
import uuid
import os

S3_PRESIGNED_URL_EXPIRY_S = os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600) # Default 1 hour 
VIDEO_UPLOAD_S3_BUCKET = os.environ.get("VIDEO_UPLOAD_S3_BUCKET")
VIDEO_UPLOAD_S3_PREFIX = os.environ.get("VIDEO_UPLOAD_S3_PREFIX")

s3 = boto3.client('s3')

def lambda_handler(event, context):
    
    action = event.get("Action", "create")
    task_id = event.get("TaskId", str(uuid.uuid4()))
    file_name = event.get("FileName", task_id)
    
    key = f'tasks/{task_id}/{VIDEO_UPLOAD_S3_PREFIX}/{file_name}'
    
    if action == "create":
        num_parts = event.get("NumParts", 5)
        upload_id = None
        
        try:
            response = s3.create_multipart_upload(Bucket=VIDEO_UPLOAD_S3_BUCKET, Key=key)
            upload_id = response['UploadId']
            
            part_urls = []
        
            # Generate pre-signed URLs for each part
            for part_number in range(1, num_parts + 1):
                params = {
                    'Bucket': VIDEO_UPLOAD_S3_BUCKET,
                    'Key': key,
                    'UploadId': upload_id,
                    'PartNumber': part_number,
                }
                # Generate pre-signed URL with expiration time (e.g., 1 hour)
                url = s3.generate_presigned_url('upload_part', Params=params, ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S)
                part_urls.append(url)
        
            url = s3.generate_presigned_url(
                'put_object',
                Params={'Bucket': VIDEO_UPLOAD_S3_BUCKET, 'Key': key},
                ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
            )
        except Exception as ex:
            return {
                'statusCode': 500,
                'body': f'Failed to create multi parts upload urls: {ex}'
            }
        
        return {
            'statusCode': 200,
            'body': {
                "TaskId": task_id,
                "FileName": file_name,
                "UploadUrl": url,
                "S3Bucket":VIDEO_UPLOAD_S3_BUCKET,
                "S3Key": key,
                "UploadId": upload_id,
                "UploadPartUrls": part_urls
            }
        }
    elif action == 'complete':
        upload_id = event.get("UploadId")
        multi_parts_upload = event.get("MultipartUpload")
        
        try:
            response = s3.complete_multipart_upload(
                Bucket = VIDEO_UPLOAD_S3_BUCKET,
                Key = key,
                MultipartUpload = {'Parts': multi_parts_upload},
                UploadId= upload_id
            )
        except Exception as ex:
            return {
                'statusCode': 500,
                'body': f'Failed to complete the uploading task: {ex}'
            }
        return {
                'statusCode': 200,
                'body': f'Uploading task completed.'
            }
            
    elif action == "abort": 
        upload_id = event.get("UploadId")
        response = s3.abort_multipart_upload(
            Bucket = VIDEO_UPLOAD_S3_BUCKET,
            Key = key,
            UploadId = upload_id
        )
        return {
                'statusCode': 200,
                'body': f'Uploading task aborted.'
            }

    return {
            'statusCode': 400,
            'body': 'Invalid request'
        }