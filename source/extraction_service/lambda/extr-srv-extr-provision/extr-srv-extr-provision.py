import os
import json
import boto3
import subprocess, shutil, sys, zipfile

iam = boto3.client('iam')
s3 = boto3.client('s3')

def on_event(event, context):
  print(event)
  request_type = event['RequestType']
  if request_type == 'Create': return on_create(event)
  if request_type == 'Post': return on_post(event)
  if request_type == 'Delete': return on_delete(event)
  raise Exception("Invalid request type: %s" % request_type)

def on_create(event):
    create_service_linked_role()
    
    layers = event.get("Layers")
    for layer in layers:
        layer_name = layer.get("name")
        layer_packages = layer.get("packages")
        s3_bucket = layer.get("s3_bucket")
        s3_key = layer.get("s3_key")
        create_layer_zip(layer_name, layer_packages, s3_bucket, s3_key)

def create_layer_zip(name, packages, s3_bucket, s3_key):
    folder_name = f'{name.replace("-","")}_layer'
    zip_file_name = s3_key.split('/')[-1]
    print("!!!",folder_name, zip_file_name)

    os.makedirs(f'/tmp/{folder_name}/python', exist_ok=True)
    shutil.rmtree(f'/tmp/{folder_name}/')
    for p in packages:
        subprocess.call(f'pip install {p["name"]}=={p["version"]} -t /tmp/{folder_name}/python/ --no-cache-dir'.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.chdir(f'/tmp/{folder_name}/')

    subprocess.call('touch ./python/__init__.py'.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    zip_folder(f'/tmp/{folder_name}',f'/tmp/{folder_name}/{zip_file_name}')

    s3.upload_file(f'/tmp/{folder_name}/{zip_file_name}', s3_bucket, s3_key)
    print("!!! to S3",f'/tmp/{folder_name}/{zip_file_name}', s3_bucket, s3_key)
    
def zip_folder(folder_path, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, folder_path)
                zipf.write(file_path, rel_path)
                
def create_service_linked_role():
    try:
        iam.create_service_linked_role(AWSServiceName='es.amazonaws.com')
    except Exception as ex:
        print("Failed to create the service linked role:", ex)
